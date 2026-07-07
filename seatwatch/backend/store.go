package main

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

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
	Matches    []ScreeningResult `json:"matches,omitempty"`
}

func (s *Store) CreateWatch(ctx context.Context, req createWatchRequest) (Watch, error) {
	watch := Watch{
		Email:      req.Email,
		MovieSlug:  req.MovieSlug,
		MovieTitle: req.MovieTitle,
		Format:     req.Format,
		NumSeats:   req.NumSeats,
		Seats:      req.Seats,
		DateFrom:   req.DateFrom,
		DateTo:     req.DateTo,
	}
	err := s.pool.QueryRow(ctx,
		`INSERT INTO watches (email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id, created_at`,
		req.Email, req.MovieSlug, req.MovieTitle, req.Format, req.NumSeats, req.Seats, req.DateFrom, req.DateTo,
	).Scan(&watch.ID, &watch.CreatedAt)
	return watch, err
}

func (s *Store) ActiveWatches(ctx context.Context) ([]Watch, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to, created_at
		 FROM watches WHERE active ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanWatches(rows)
}

func (s *Store) ListWatches(ctx context.Context, email string) ([]Watch, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, email, movie_slug, movie_title, format, num_seats, seats, date_from, date_to, created_at
		 FROM watches WHERE active AND email = $1 ORDER BY id DESC`, email)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	watches, err := scanWatches(rows)
	if err != nil {
		return nil, err
	}
	for i := range watches {
		matches, err := s.matchesForWatch(ctx, watches[i].ID)
		if err != nil {
			return nil, err
		}
		watches[i].Matches = matches
	}
	return watches, nil
}

func (s *Store) DeleteWatch(ctx context.Context, id int64) error {
	_, err := s.pool.Exec(ctx, `UPDATE watches SET active = FALSE WHERE id = $1`, id)
	return err
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

func scanWatches(rows pgx.Rows) ([]Watch, error) {
	var watches []Watch
	for rows.Next() {
		var w Watch
		if err := rows.Scan(&w.ID, &w.Email, &w.MovieSlug, &w.MovieTitle, &w.Format, &w.NumSeats, &w.Seats, &w.DateFrom, &w.DateTo, &w.CreatedAt); err != nil {
			return nil, err
		}
		watches = append(watches, w)
	}
	return watches, rows.Err()
}
