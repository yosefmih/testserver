# SeatWatch

Watch for specific seats at AMC Lincoln Square 13. Pick a movie, mark every seat
you'd tolerate on the real auditorium map, say how many tickets you need, and get
an email the moment a screening has that many of your seats free **next to each
other**.

Built because IMAX 70mm screenings sell out instantly and refunds free up seats
at random times.

## How it works

AMC's site has no public API, but every showtimes page and seat-picker page is a
Next.js app that server-renders its data into the HTML as RSC flight chunks
(`self.__next_f.push(...)`). The backend fetches those pages with plain GETs and
extracts:

- `/movie-theatres/.../showtimes?date=YYYY-MM-DD` → every screening (movie, format
  like "IMAX 70MM", time, sellable/soldout)
- `/showtimes/{id}/seats` → the full seat map (`seatingLayout`), including per-seat
  availability

A background refresher controller loops forever: scan all showtimes, fetch every
upcoming screening's seat map, store everything in an in-memory cache, evaluate
watches and send alerts, sleep `REFRESH_INTERVAL` (default 3m), repeat. The HTTP
API never talks to AMC — every endpoint is a cache read, so responses are
instant (during initial warmup, endpoints return 503 and the UI retries).

Lookahead is unbounded: showtimes are scanned forward in week batches until AMC
lists nothing for a whole week (120-day backstop), so far-future releases like
IMAX 70mm events are covered. All AMC requests go through a global rate limiter
(default 400ms spacing) with retry/backoff on 429s; watched movies' seat maps
are fetched first each sweep. A screening "matches" when it has N adjacent
available seats in the same row, all within your tolerable set. You get one
email per (watch, screening) the first time it matches.

## Run it

```bash
# 1. postgres (port 5434)
docker compose up -d

# 2. backend (port 8095)
cd backend && go build -o seatwatch . && ./seatwatch

# 3. frontend (port 5174, proxies /api to the backend)
cd frontend && npm install && npm run dev
```

Email alerts are OFF by default (`ALERTS_ENABLED` unset): the email step and
My Watches UI are hidden, watch creation is rejected, and nothing is sent. To
turn alerts on:

```bash
ALERTS_ENABLED=true SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
SMTP_USER=you@gmail.com SMTP_PASS=<app password> SMTP_FROM=you@gmail.com ./seatwatch
```

With `ALERTS_ENABLED=true` but no SMTP config, alert emails are logged to
stdout instead of sent (useful for testing).

Other knobs: `PORT`, `DATABASE_URL`, `REFRESH_INTERVAL` (pause between sweeps,
e.g. `2m`), `MAX_LOOKAHEAD_DAYS`, `AMC_REQUEST_INTERVAL` (rate-limit spacing),
`THEATRE_PATH` (any AMC theatre's site path), `STATIC_DIR` (serve the built
frontend from the backend).

## Docker / Porter

`Dockerfile` builds everything into one image (~25MB): SvelteKit static build +
Go binary serving both the API and the frontend on `PORT` (default 8095). The
database URL is read from `SEAT_WATCHER_DB_DB_URL` (falls back to
`DATABASE_URL`). Run a single replica — each instance runs its own AMC
refresher, so replicas would multiply scraping traffic.

Scraped data (showtimes + seat maps) is persisted to postgres as each sweep
lands (`scraped_showtimes`, `scraped_layouts`), so a fresh pod restores the
last sweep on boot and serves immediately instead of starting cold; the
background sweep then refreshes anything stale.

```bash
docker build -t seatwatch .
docker run -p 8095:8095 -e SEAT_WATCHER_DB_DB_URL=postgres://... seatwatch
```

## Notes

- The parsers live in `backend/amc/` with real captured pages as test fixtures
  (`go test ./...`).
- If AMC changes their page structure or starts bot-blocking plain HTTP clients,
  `amc/parse.go` regexes and `amc/client.go` headers are the places to look.
