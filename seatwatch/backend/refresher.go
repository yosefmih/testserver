package main

import (
	"context"
	"log"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"

	"seatwatch/amc"
)

const layoutFetchConcurrency = 4

// Refresher is the background controller that keeps the Cache warm: in a loop
// it scans all showtimes, fetches every upcoming screening's seat map, then
// evaluates watches and sends alerts. HTTP handlers never fetch from AMC; they
// read the cache.
type Refresher struct {
	cache            *Cache
	client           *amc.Client
	store            *Store
	mailer           *Mailer
	theatreTZ        *time.Location
	alertsEnabled    bool
	interval         time.Duration
	staleAfter       time.Duration
	maxLookaheadDays int
}

// RestoreFromDB loads the last persisted sweep so a fresh pod serves
// immediately instead of starting with an empty cache.
func (r *Refresher) RestoreFromDB(ctx context.Context) {
	showtimes, refreshedAt, err := r.store.LoadShowtimes(ctx)
	if err != nil {
		log.Printf("restoring showtimes from db: %v", err)
	} else if len(showtimes) > 0 {
		r.cache.RestoreShowtimes(showtimes, refreshedAt)
	}
	layouts, fetchedAt, err := r.store.LoadLayouts(ctx)
	if err != nil {
		log.Printf("restoring seat maps from db: %v", err)
	} else {
		for id, layout := range layouts {
			r.cache.RestoreLayout(id, layout, fetchedAt[id])
		}
	}
	if len(showtimes) > 0 || len(layouts) > 0 {
		log.Printf("restored %d screenings and %d seat maps from db (as of %s ago)",
			len(showtimes), len(layouts), time.Since(refreshedAt).Round(time.Second))
	}
}

func (r *Refresher) Run(ctx context.Context) {
	for {
		start := time.Now()
		if err := r.Sweep(ctx); err != nil {
			log.Printf("sweep failed: %v", err)
		} else {
			log.Printf("sweep done in %s (%d screenings cached)", time.Since(start).Round(time.Second), r.cache.LayoutCount())
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(r.interval):
		}
	}
}

// Sweep runs under its own root span so the hundreds of AMC fetches per cycle
// nest into one sweep trace instead of appearing as orphan roots.
func (r *Refresher) Sweep(ctx context.Context) error {
	ctx, span := otel.Tracer("seatwatch").Start(ctx, "sweep")
	defer span.End()
	log.Printf("sweep: scanning showtimes (up to %d days ahead)", r.maxLookaheadDays)
	scanStart := time.Now()
	showtimes, err := r.scanShowtimes(ctx)
	if err != nil {
		return err
	}
	r.cache.SetShowtimes(showtimes)
	if err := r.store.SaveShowtimes(ctx, showtimes, time.Now()); err != nil {
		log.Printf("persisting showtimes: %v", err)
	}
	lastDay := ""
	if len(showtimes) > 0 {
		lastDay = showtimes[len(showtimes)-1].ShowAt.In(r.theatreTZ).Format("2006-01-02")
	}
	log.Printf("sweep: %d screenings listed through %s (%s)", len(showtimes), lastDay, time.Since(scanStart).Round(time.Second))

	watched, err := r.store.ActiveWatches(ctx)
	if err != nil {
		return err
	}
	watchedSlugs := map[string]bool{}
	for _, w := range watched {
		watchedSlugs[w.MovieSlug] = true
	}

	// Watched movies refresh every sweep (alerts depend on them, and they go
	// first so their data is freshest). Everything else only refreshes once
	// its cached seat map is older than staleAfter, keeping per-sweep volume
	// low enough that Cloudflare doesn't slow-walk us.
	var ids []int64
	upcoming := map[int64]bool{}
	skippedFresh := 0
	for pass := 0; pass < 2; pass++ {
		for _, st := range showtimes {
			if st.ShowAt.Before(time.Now()) {
				continue
			}
			watchedPass := pass == 0
			if watchedSlugs[st.MovieSlug] != watchedPass {
				continue
			}
			upcoming[st.ID] = true
			if !watchedPass {
				if at, ok := r.cache.LayoutFetchedAt(st.ID); ok && time.Since(at) < r.staleAfter {
					skippedFresh++
					continue
				}
			}
			ids = append(ids, st.ID)
		}
	}

	if err := r.fetchLayouts(ctx, ids, skippedFresh); err != nil {
		return err
	}
	r.cache.Prune(upcoming)
	keep := make([]int64, 0, len(upcoming))
	for id := range upcoming {
		keep = append(keep, id)
	}
	if err := r.store.PruneLayouts(ctx, keep); err != nil {
		log.Printf("pruning persisted seat maps: %v", err)
	}

	if len(watched) > 0 {
		log.Printf("sweep: evaluating %d watches", len(watched))
	}
	for _, watch := range watched {
		if _, err := r.EvaluateWatch(ctx, watch); err != nil {
			log.Printf("evaluating watch %d (%s / %s): %v", watch.ID, watch.MovieTitle, watch.Email, err)
		}
	}
	return nil
}

// fetchLayouts fetches every given showtime's seat map from AMC (bounded
// concurrency) and stores each into the cache and DB as it lands.
func (r *Refresher) fetchLayouts(ctx context.Context, ids []int64, skippedFresh int) error {
	ctx, span := NewSpan(ctx, "fetchLayouts")
	defer span.End()
	span.SetAttributes(attribute.Int("to_fetch", len(ids)), attribute.Int("skipped_fresh", skippedFresh))

	log.Printf("sweep: fetching %d seat maps (%d cached and still fresh; watched movies first)", len(ids), skippedFresh)
	sem := make(chan struct{}, layoutFetchConcurrency)
	var wg sync.WaitGroup
	var failed, done atomic.Int64
	for _, id := range ids {
		wg.Add(1)
		go func(id int64) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			layout, err := r.client.SeatingLayout(ctx, id)
			if err != nil {
				failed.Add(1)
				log.Printf("seat map for showtime %d: %v", id, err)
			} else {
				r.cache.SetLayout(id, layout)
				if err := r.store.SaveLayout(ctx, id, layout, time.Now()); err != nil {
					log.Printf("persisting seat map %d: %v", id, err)
				}
			}
			if n := done.Add(1); n%50 == 0 {
				log.Printf("sweep: seat maps %d/%d", n, len(ids))
			}
		}(id)
	}
	wg.Wait()
	span.SetAttributes(attribute.Int64("failed", failed.Load()))
	log.Printf("sweep: fetched %d seat maps (%d failed, %d skipped as fresh)", len(ids), failed.Load(), skippedFresh)
	return nil
}

// FetchLayoutNow serves a seat map from cache, or — during the warmup window
// before the sweep has reached this screening — fetches it from AMC on the
// spot so a user's first click never waits for the whole sweep.
func (r *Refresher) FetchLayoutNow(ctx context.Context, showtimeID int64) (amc.SeatingLayout, error) {
	ctx, span := NewSpan(ctx, "FetchLayoutNow")
	defer span.End()
	span.SetAttributes(attribute.Int64("showtime_id", showtimeID))

	if layout, ok := r.cache.Layout(showtimeID); ok {
		span.SetAttributes(attribute.Bool("cache_hit", true))
		return layout, nil
	}
	span.SetAttributes(attribute.Bool("cache_hit", false))
	log.Printf("seat map %d not swept yet, fetching on demand", showtimeID)
	layout, err := r.client.SeatingLayout(ctx, showtimeID)
	if err != nil {
		return amc.SeatingLayout{}, err
	}
	r.cache.SetLayout(showtimeID, layout)
	if err := r.store.SaveLayout(ctx, showtimeID, layout, time.Now()); err != nil {
		log.Printf("persisting seat map %d: %v", showtimeID, err)
	}
	return layout, nil
}

// scanShowtimes walks forward in week-sized parallel batches until AMC lists
// nothing for a whole week, so far-future releases (e.g. IMAX 70mm events that
// sell months ahead) are covered without a fixed horizon.
func (r *Refresher) scanShowtimes(ctx context.Context) ([]amc.Showtime, error) {
	ctx, span := NewSpan(ctx, "scanShowtimes")
	defer span.End()
	const batchDays = 7
	type dayResult struct {
		day       int
		showtimes []amc.Showtime
		err       error
	}
	var all []amc.Showtime
	today := time.Now()
	for start := 0; start < r.maxLookaheadDays; start += batchDays {
		end := min(start+batchDays, r.maxLookaheadDays)
		results := make([]dayResult, end-start)
		sem := make(chan struct{}, layoutFetchConcurrency)
		var wg sync.WaitGroup
		for day := start; day < end; day++ {
			wg.Add(1)
			go func(day int) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				showtimes, err := r.client.Showtimes(ctx, today.AddDate(0, 0, day))
				results[day-start] = dayResult{day, showtimes, err}
			}(day)
		}
		wg.Wait()

		batchTotal := 0
		for _, res := range results {
			if res.err != nil {
				if res.day == 0 {
					return nil, res.err
				}
				log.Printf("showtimes for day +%d: %v", res.day, res.err)
				continue
			}
			batchTotal += len(res.showtimes)
			all = append(all, res.showtimes...)
		}
		if batchTotal == 0 {
			break
		}
	}

	seen := map[int64]bool{}
	deduped := all[:0]
	for _, st := range all {
		if !seen[st.ID] {
			seen[st.ID] = true
			deduped = append(deduped, st)
		}
	}
	sort.Slice(deduped, func(i, j int) bool { return deduped[i].ShowAt.Before(deduped[j].ShowAt) })
	span.SetAttributes(attribute.Int("showtimes_found", len(deduped)))
	return deduped, nil
}

type ScreeningResult struct {
	ShowtimeID int64      `json:"showtimeId"`
	ShowAt     time.Time  `json:"showAt"`
	Format     string     `json:"format"`
	Status     string     `json:"status"`
	Matched    bool       `json:"matched"`
	OpenSeats  int        `json:"openSeats"`
	GroupCount int        `json:"groupCount"`
	SeatGroups [][]string `json:"seatGroups"`
}

const exampleGroups = 3

type EvaluateResponse struct {
	Results     []ScreeningResult `json:"results"`
	Pending     int               `json:"pending"`
	RefreshedAt time.Time         `json:"refreshedAt"`
}

// Selection is a set of watch criteria: which movie/format, which seats, how
// many tickets, and an optional theatre-local date range ("2006-01-02"; empty
// means unbounded).
type Selection struct {
	MovieSlug string
	Format    string
	Seats     []string
	NumSeats  int
	DateFrom  string
	DateTo    string
}

// EvaluateSelection computes, purely from cache, which upcoming screenings of
// a movie have NumSeats adjacent available seats within the tolerable set.
// Screenings whose seat map is not cached yet are counted as pending.
func (r *Refresher) EvaluateSelection(ctx context.Context, sel Selection) EvaluateResponse {
	ctx, span := NewSpan(ctx, "EvaluateSelection")
	defer span.End()
	span.SetAttributes(
		attribute.String("movie_slug", sel.MovieSlug),
		attribute.String("format", sel.Format),
		attribute.Int("num_seats", sel.NumSeats),
		attribute.Int("tolerable_seats", len(sel.Seats)),
	)

	candidates := r.filterShowtimes(ctx, sel)
	span.SetAttributes(attribute.Int("candidate_screenings", len(candidates)))

	resp := r.matchScreenings(ctx, candidates, sel)
	span.SetAttributes(
		attribute.Int("matched_screenings", countMatched(resp.Results)),
		attribute.Int("pending_screenings", resp.Pending),
	)
	return resp
}

// filterShowtimes narrows the full cached showtime list down to candidates
// for a selection: same movie/format, upcoming, inside the date window.
func (r *Refresher) filterShowtimes(ctx context.Context, sel Selection) []amc.Showtime {
	_, span := NewSpan(ctx, "filterShowtimes")
	defer span.End()

	var candidates []amc.Showtime
	for _, st := range r.cache.Showtimes() {
		if st.MovieSlug != sel.MovieSlug {
			continue
		}
		if sel.Format != "" && st.Format != sel.Format {
			continue
		}
		if st.ShowAt.Before(time.Now()) {
			continue
		}
		showDate := st.ShowAt.In(r.theatreTZ).Format("2006-01-02")
		if sel.DateFrom != "" && showDate < sel.DateFrom {
			continue
		}
		if sel.DateTo != "" && showDate > sel.DateTo {
			continue
		}
		candidates = append(candidates, st)
	}
	return candidates
}

// matchScreenings runs the seat matcher for every candidate screening against
// a selection. One span covers the whole batch (rather than one per
// screening) since a popular movie can have hundreds of candidates.
func (r *Refresher) matchScreenings(ctx context.Context, candidates []amc.Showtime, sel Selection) EvaluateResponse {
	_, span := NewSpan(ctx, "matchScreenings")
	defer span.End()

	resp := EvaluateResponse{Results: []ScreeningResult{}, RefreshedAt: r.cache.ShowtimesRefreshedAt()}
	for _, st := range candidates {
		layout, ok := r.cache.Layout(st.ID)
		if !ok {
			resp.Pending++
			continue
		}
		groups, openSeats := FindAdjacentSeatGroups(layout, sel.Seats, sel.NumSeats)
		examples := groups
		if len(examples) > exampleGroups {
			examples = examples[:exampleGroups]
		}
		resp.Results = append(resp.Results, ScreeningResult{
			ShowtimeID: st.ID,
			ShowAt:     st.ShowAt,
			Format:     st.Format,
			Status:     st.Status,
			Matched:    len(groups) > 0,
			OpenSeats:  openSeats,
			GroupCount: len(groups),
			SeatGroups: examples,
		})
	}
	span.SetAttributes(attribute.Int("screenings_matched", len(resp.Results)))
	return resp
}

func countMatched(results []ScreeningResult) int {
	n := 0
	for _, r := range results {
		if r.Matched {
			n++
		}
	}
	return n
}

// EvaluateWatch runs EvaluateSelection for a stored watch, records results,
// and emails the watcher about newly matched screenings.
func (r *Refresher) EvaluateWatch(ctx context.Context, watch Watch) (EvaluateResponse, error) {
	ctx, span := NewSpan(ctx, "EvaluateWatch")
	defer span.End()
	span.SetAttributes(attribute.Int64("watch_id", watch.ID), attribute.String("email", watch.Email))

	resp := r.EvaluateSelection(ctx, Selection{
		MovieSlug: watch.MovieSlug,
		Format:    watch.Format,
		Seats:     watch.Seats,
		NumSeats:  watch.NumSeats,
		DateFrom:  watch.DateFrom,
		DateTo:    watch.DateTo,
	})

	newlyMatched, err := r.recordMatchStates(ctx, watch.ID, resp.Results)
	if err != nil {
		return resp, err
	}
	span.SetAttributes(attribute.Int("newly_matched", len(newlyMatched)))

	if len(newlyMatched) > 0 && r.alertsEnabled {
		if err := r.sendAlert(ctx, watch, newlyMatched); err != nil {
			return resp, err
		}
	}
	return resp, nil
}

// recordMatchStates persists each screening's match result for a watch and
// reports which ones newly matched (not yet alerted).
func (r *Refresher) recordMatchStates(ctx context.Context, watchID int64, results []ScreeningResult) ([]ScreeningResult, error) {
	ctx, span := NewSpan(ctx, "recordMatchStates")
	defer span.End()

	var newlyMatched []ScreeningResult
	for _, res := range results {
		firstMatch, err := r.store.RecordMatchState(ctx, watchID, res)
		if err != nil {
			return nil, err
		}
		if res.Matched && firstMatch {
			newlyMatched = append(newlyMatched, res)
		}
	}
	return newlyMatched, nil
}

func (r *Refresher) sendAlert(ctx context.Context, watch Watch, newlyMatched []ScreeningResult) error {
	_, span := NewSpan(ctx, "sendAlert")
	defer span.End()

	if err := r.mailer.SendMatchAlert(watch, newlyMatched); err != nil {
		log.Printf("sending alert for watch %d: %v", watch.ID, err)
		return nil
	}
	ids := make([]int64, len(newlyMatched))
	for i, m := range newlyMatched {
		ids[i] = m.ShowtimeID
	}
	return r.store.MarkAlerted(ctx, watch.ID, ids)
}
