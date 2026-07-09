package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"seatwatch/amc"
)

// generateWatchToken returns an unguessable per-watch secret. Watches are
// looked up and managed by this token, never by email — an email address is
// often known or guessable, so using it as a lookup key would let anyone view
// or delete someone else's watch.
func generateWatchToken() (string, error) {
	buf := make([]byte, 24)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

type Store struct {
	pool *pgxpool.Pool
}

const schema = `
CREATE TABLE IF NOT EXISTS watches (
	id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	email TEXT NOT NULL,
	movie_slug TEXT NOT NULL,
	movie_title TEXT NOT NULL,
	format TEXT NOT NULL DEFAULT '',
	num_seats INT NOT NULL,
	seats TEXT[] NOT NULL,
	active BOOLEAN NOT NULL DEFAULT TRUE,
	created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS screening_matches (
	watch_id BIGINT NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
	showtime_id BIGINT NOT NULL,
	show_at TIMESTAMPTZ NOT NULL,
	matched BOOLEAN NOT NULL,
	seat_groups JSONB NOT NULL DEFAULT '[]',
	alerted_at TIMESTAMPTZ,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	PRIMARY KEY (watch_id, showtime_id)
);

ALTER TABLE screening_matches ADD COLUMN IF NOT EXISTS open_seats INT NOT NULL DEFAULT 0;
ALTER TABLE screening_matches ADD COLUMN IF NOT EXISTS group_count INT NOT NULL DEFAULT 0;
ALTER TABLE watches ADD COLUMN IF NOT EXISTS date_from TEXT NOT NULL DEFAULT '';
ALTER TABLE watches ADD COLUMN IF NOT EXISTS date_to TEXT NOT NULL DEFAULT '';
ALTER TABLE watches ADD COLUMN IF NOT EXISTS token TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS watches_token_idx ON watches (token) WHERE token != '';

CREATE TABLE IF NOT EXISTS scraped_showtimes (
	id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
	data JSONB NOT NULL,
	refreshed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scraped_layouts (
	showtime_id BIGINT PRIMARY KEY,
	data JSONB NOT NULL,
	fetched_at TIMESTAMPTZ NOT NULL
);
`

func (s *Store) InitSchema(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, schema)
	return err
}

type Watch struct {
	ID         int64             `json:"id"`
	Email      string            `json:"email"`
	MovieSlug  string            `json:"movieSlug"`
	MovieTitle string            `json:"movieTitle"`
	Format     string            `json:"format"`
	NumSeats   int               `json:"numSeats"`
	Seats      []string          `json:"seats"`
	DateFrom   string            `json:"dateFrom"`
	DateTo     string            `json:"dateTo"`
	CreatedAt  time.Time         `json:"createdAt"`
	Token      string            `json:"token"`
	Matches    []ScreeningResult `json:"matches,omitempty"`
}

func (s *Store) CreateWatch(ctx context.Context, req createWatchRequest) (Watch, error) {
	token, err := generateWatchToken()
	if err != nil {
		return Watch{}, err
	}
	watch := Watch{
		Email:      req.Email,
		MovieSlug:  req.MovieSlug,
		MovieTitle: req.MovieTitle,
		Format:     req.Format,
		NumSeats:   req.NumSeats,
		Seats:      req.Seats,
		DateFrom:   req.DateFrom,
		DateTo:     req.DateTo,
		Token:      token,
	}
	err = s.pool.QueryRow(ctx,
		`INSERT INTO watches (email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to, token)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id, created_at`,
		req.Email, req.MovieSlug, req.MovieTitle, req.Format, req.NumSeats, req.Seats, req.DateFrom, req.DateTo, token,
	).Scan(&watch.ID, &watch.CreatedAt)
	return watch, err
}

func (s *Store) ActiveWatches(ctx context.Context) ([]Watch, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to, created_at, token
		 FROM watches WHERE active ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanWatches(rows)
}

// GetWatchByToken looks up exactly one watch by its unguessable token — the
// only supported way to read back a watch after creation.
func (s *Store) GetWatchByToken(ctx context.Context, token string) (Watch, error) {
	if token == "" {
		return Watch{}, pgx.ErrNoRows
	}
	rows, err := s.pool.Query(ctx,
		`SELECT id, email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to, created_at, token
		 FROM watches WHERE active AND token = $1`, token)
	if err != nil {
		return Watch{}, err
	}
	defer rows.Close()
	watches, err := scanWatches(rows)
	if err != nil {
		return Watch{}, err
	}
	if len(watches) == 0 {
		return Watch{}, pgx.ErrNoRows
	}
	watch := watches[0]
	watch.Matches, err = s.matchesForWatch(ctx, watch.ID)
	return watch, err
}

// DeleteWatchByToken deactivates a watch only if the token matches, so
// deleting requires the same secret the owner was given at creation.
func (s *Store) DeleteWatchByToken(ctx context.Context, token string) error {
	tag, err := s.pool.Exec(ctx, `UPDATE watches SET active = FALSE WHERE token = $1 AND token != ''`, token)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

// RecordMatchState upserts the match result for a (watch, showtime) pair and
// reports whether this is a new match that has not been alerted yet.
func (s *Store) RecordMatchState(ctx context.Context, watchID int64, result ScreeningResult) (bool, error) {
	groupsJSON, err := json.Marshal(result.SeatGroups)
	if err != nil {
		return false, err
	}
	var alertPending bool
	err = s.pool.QueryRow(ctx,
		`INSERT INTO screening_matches (watch_id, showtime_id, show_at, matched, seat_groups, open_seats, group_count)
		 VALUES ($1, $2, $3, $4, $5, $6, $7)
		 ON CONFLICT (watch_id, showtime_id) DO UPDATE
		 SET matched = $4, seat_groups = $5, open_seats = $6, group_count = $7, show_at = $3, updated_at = now()
		 RETURNING (matched AND alerted_at IS NULL)`,
		watchID, result.ShowtimeID, result.ShowAt, result.Matched, groupsJSON, result.OpenSeats, result.GroupCount,
	).Scan(&alertPending)
	return alertPending, err
}

func (s *Store) MarkAlerted(ctx context.Context, watchID int64, showtimeIDs []int64) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE screening_matches SET alerted_at = now()
		 WHERE watch_id = $1 AND showtime_id = ANY($2)`, watchID, showtimeIDs)
	return err
}

func (s *Store) matchesForWatch(ctx context.Context, watchID int64) ([]ScreeningResult, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT showtime_id, show_at, seat_groups, open_seats, group_count FROM screening_matches
		 WHERE watch_id = $1 AND matched AND show_at > now() ORDER BY show_at`, watchID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var matches []ScreeningResult
	for rows.Next() {
		m := ScreeningResult{Matched: true}
		var groupsJSON []byte
		if err := rows.Scan(&m.ShowtimeID, &m.ShowAt, &groupsJSON, &m.OpenSeats, &m.GroupCount); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(groupsJSON, &m.SeatGroups); err != nil {
			return nil, err
		}
		matches = append(matches, m)
	}
	return matches, rows.Err()
}

func (s *Store) SaveShowtimes(ctx context.Context, showtimes []amc.Showtime, refreshedAt time.Time) error {
	data, err := json.Marshal(showtimes)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx,
		`INSERT INTO scraped_showtimes (id, data, refreshed_at) VALUES (1, $1, $2)
		 ON CONFLICT (id) DO UPDATE SET data = $1, refreshed_at = $2`, data, refreshedAt)
	return err
}

func (s *Store) LoadShowtimes(ctx context.Context) ([]amc.Showtime, time.Time, error) {
	var data []byte
	var refreshedAt time.Time
	err := s.pool.QueryRow(ctx, `SELECT data, refreshed_at FROM scraped_showtimes WHERE id = 1`).Scan(&data, &refreshedAt)
	if err == pgx.ErrNoRows {
		return nil, time.Time{}, nil
	}
	if err != nil {
		return nil, time.Time{}, err
	}
	var showtimes []amc.Showtime
	if err := json.Unmarshal(data, &showtimes); err != nil {
		return nil, time.Time{}, err
	}
	return showtimes, refreshedAt, nil
}

func (s *Store) SaveLayout(ctx context.Context, showtimeID int64, layout amc.SeatingLayout, fetchedAt time.Time) error {
	data, err := json.Marshal(layout)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx,
		`INSERT INTO scraped_layouts (showtime_id, data, fetched_at) VALUES ($1, $2, $3)
		 ON CONFLICT (showtime_id) DO UPDATE SET data = $2, fetched_at = $3`, showtimeID, data, fetchedAt)
	return err
}

func (s *Store) LoadLayouts(ctx context.Context) (map[int64]amc.SeatingLayout, map[int64]time.Time, error) {
	rows, err := s.pool.Query(ctx, `SELECT showtime_id, data, fetched_at FROM scraped_layouts`)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()

	layouts := map[int64]amc.SeatingLayout{}
	fetchedAt := map[int64]time.Time{}
	for rows.Next() {
		var id int64
		var data []byte
		var at time.Time
		if err := rows.Scan(&id, &data, &at); err != nil {
			return nil, nil, err
		}
		var layout amc.SeatingLayout
		if err := json.Unmarshal(data, &layout); err != nil {
			return nil, nil, err
		}
		layouts[id] = layout
		fetchedAt[id] = at
	}
	return layouts, fetchedAt, rows.Err()
}

func (s *Store) PruneLayouts(ctx context.Context, keep []int64) error {
	_, err := s.pool.Exec(ctx, `DELETE FROM scraped_layouts WHERE NOT (showtime_id = ANY($1))`, keep)
	return err
}

func scanWatches(rows pgx.Rows) ([]Watch, error) {
	var watches []Watch
	for rows.Next() {
		var w Watch
		if err := rows.Scan(&w.ID, &w.Email, &w.MovieSlug, &w.MovieTitle, &w.Format, &w.NumSeats, &w.Seats, &w.DateFrom, &w.DateTo, &w.CreatedAt, &w.Token); err != nil {
			return nil, err
		}
		watches = append(watches, w)
	}
	return watches, rows.Err()
}
