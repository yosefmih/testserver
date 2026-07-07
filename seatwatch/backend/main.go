package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"seatwatch/amc"
)

func main() {
	ctx := context.Background()

	dbURL := envOr("SEAT_WATCHER_DB_DB_URL", envOr("DATABASE_URL", "postgres://seatwatch:seatwatch@localhost:5434/seatwatch"))
	pool, err := connectWithRetry(ctx, dbURL)
	if err != nil {
		log.Fatalf("connecting to postgres: %v", err)
	}
	store := &Store{pool: pool}
	if err := store.InitSchema(ctx); err != nil {
		log.Fatalf("initializing schema: %v", err)
	}

	client := amc.NewClient(envOr("THEATRE_PATH", amc.DefaultTheatrePath), envDurationOr("AMC_REQUEST_INTERVAL", 400*time.Millisecond))
	mailer := NewMailerFromEnv()
	theatreTZ, err := time.LoadLocation(envOr("THEATRE_TZ", "America/New_York"))
	if err != nil {
		log.Fatalf("loading theatre timezone: %v", err)
	}
	alertsEnabled := os.Getenv("ALERTS_ENABLED") == "true"
	cache := NewCache()
	refresher := &Refresher{
		cache:            cache,
		client:           client,
		store:            store,
		mailer:           mailer,
		theatreTZ:        theatreTZ,
		alertsEnabled:    alertsEnabled,
		interval:         envDurationOr("REFRESH_INTERVAL", 3*time.Minute),
		staleAfter:       envDurationOr("LAYOUT_STALE_AFTER", 30*time.Minute),
		maxLookaheadDays: envIntOr("MAX_LOOKAHEAD_DAYS", 120),
	}
	go refresher.Run(ctx)

	server := &Server{store: store, cache: cache, refresher: refresher, alertsEnabled: alertsEnabled, staticDir: os.Getenv("STATIC_DIR")}
	addr := ":" + envOr("PORT", "8095")
	log.Printf("seatwatch backend listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, server.Routes()))
}

func connectWithRetry(ctx context.Context, dbURL string) (*pgxpool.Pool, error) {
	var pool *pgxpool.Pool
	var err error
	for attempt := 0; attempt < 10; attempt++ {
		pool, err = pgxpool.New(ctx, dbURL)
		if err == nil {
			if err = pool.Ping(ctx); err == nil {
				return pool, nil
			}
			pool.Close()
		}
		log.Printf("postgres not ready (attempt %d): %v", attempt+1, err)
		time.Sleep(2 * time.Second)
	}
	return nil, err
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envIntOr(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func envDurationOr(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return fallback
}
