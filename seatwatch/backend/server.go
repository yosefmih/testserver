package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type Server struct {
	store         *Store
	cache         *Cache
	refresher     *Refresher
	alertsEnabled bool
	staticDir     string
}

func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("GET /api/config", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]bool{"alertsEnabled": s.alertsEnabled})
	})
	mux.HandleFunc("GET /api/showtimes", s.handleShowtimes)
	mux.HandleFunc("GET /api/seatmap/{showtimeID}", s.handleSeatMap)
	mux.HandleFunc("POST /api/evaluate", s.handleEvaluate)
	mux.HandleFunc("POST /api/watches", s.handleCreateWatch)
	mux.HandleFunc("GET /api/watches", s.handleListWatches)
	mux.HandleFunc("DELETE /api/watches/{id}", s.handleDeleteWatch)
	if s.staticDir != "" {
		mux.Handle("/", spaHandler(s.staticDir))
	}
	handler := otelhttp.NewHandler(cors(tagRequestID(logAPIRequests(mux))), "http.server",
		otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
			return r.Method + " " + r.URL.Path
		}))
	return handler
}

// tagRequestID records ingress-nginx's request id on the active span so
// traces are searchable by the request_id that appears in access logs.
func tagRequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if id := r.Header.Get("X-Request-Id"); id != "" {
			trace.SpanFromContext(r.Context()).SetAttributes(attribute.String("request.id", id))
		}
		next.ServeHTTP(w, r)
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func logAPIRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/") {
			next.ServeHTTP(w, r)
			return
		}
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		ids := ""
		if reqID := r.Header.Get("X-Request-Id"); reqID != "" {
			ids = " request_id=" + reqID
		}
		if sc := trace.SpanFromContext(r.Context()).SpanContext(); sc.HasTraceID() {
			ids += " trace_id=" + sc.TraceID().String()
		}
		log.Printf("%s %s -> %d (%s)%s", r.Method, r.URL.Path, rec.status, time.Since(start).Round(time.Millisecond), ids)
	})
}

func (s *Server) handleShowtimes(w http.ResponseWriter, r *http.Request) {
	showtimes := s.cache.Showtimes()
	if showtimes == nil {
		httpError(w, http.StatusServiceUnavailable, "warming up — first AMC scan is still running, try again shortly")
		return
	}
	writeJSON(w, showtimes)
}

func (s *Server) handleSeatMap(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("showtimeID"), 10, 64)
	if err != nil {
		httpError(w, http.StatusBadRequest, "invalid showtime id")
		return
	}
	layout, err := s.refresher.FetchLayoutNow(r.Context(), id)
	if err != nil {
		httpError(w, http.StatusBadGateway, "fetching seat map: "+err.Error())
		return
	}
	writeJSON(w, layout)
}

type evaluateRequest struct {
	MovieSlug string   `json:"movieSlug"`
	Format    string   `json:"format"`
	NumSeats  int      `json:"numSeats"`
	Seats     []string `json:"seats"`
	DateFrom  string   `json:"dateFrom"`
	DateTo    string   `json:"dateTo"`
}

func (s *Server) handleEvaluate(w http.ResponseWriter, r *http.Request) {
	var req evaluateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if req.MovieSlug == "" || req.NumSeats < 1 || len(req.Seats) == 0 {
		httpError(w, http.StatusBadRequest, "movieSlug, numSeats and seats are required")
		return
	}
	if err := validDateRange(req.DateFrom, req.DateTo); err != nil {
		httpError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, s.refresher.EvaluateSelection(r.Context(), Selection{
		MovieSlug: req.MovieSlug,
		Format:    req.Format,
		Seats:     req.Seats,
		NumSeats:  req.NumSeats,
		DateFrom:  req.DateFrom,
		DateTo:    req.DateTo,
	}))
}

func validDateRange(from, to string) error {
	for _, d := range []string{from, to} {
		if d == "" {
			continue
		}
		if _, err := time.Parse("2006-01-02", d); err != nil {
			return fmt.Errorf("invalid date %q, expected YYYY-MM-DD", d)
		}
	}
	if from != "" && to != "" && from > to {
		return fmt.Errorf("dateFrom is after dateTo")
	}
	return nil
}

type createWatchRequest struct {
	Email      string   `json:"email"`
	MovieSlug  string   `json:"movieSlug"`
	MovieTitle string   `json:"movieTitle"`
	Format     string   `json:"format"`
	NumSeats   int      `json:"numSeats"`
	Seats      []string `json:"seats"`
	DateFrom   string   `json:"dateFrom"`
	DateTo     string   `json:"dateTo"`
}

func (s *Server) handleCreateWatch(w http.ResponseWriter, r *http.Request) {
	if !s.alertsEnabled {
		httpError(w, http.StatusForbidden, "alerts are not enabled on this deployment")
		return
	}
	var req createWatchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if req.Email == "" || !strings.Contains(req.Email, "@") {
		httpError(w, http.StatusBadRequest, "a valid email is required")
		return
	}
	if req.MovieSlug == "" || req.MovieTitle == "" {
		httpError(w, http.StatusBadRequest, "movie is required")
		return
	}
	if req.NumSeats < 1 || req.NumSeats > 10 {
		httpError(w, http.StatusBadRequest, "numSeats must be between 1 and 10")
		return
	}
	if len(req.Seats) < req.NumSeats {
		httpError(w, http.StatusBadRequest, "select at least as many tolerable seats as tickets")
		return
	}
	if err := validDateRange(req.DateFrom, req.DateTo); err != nil {
		httpError(w, http.StatusBadRequest, err.Error())
		return
	}

	watch, err := s.store.CreateWatch(r.Context(), req)
	if err != nil {
		httpError(w, http.StatusInternalServerError, err.Error())
		return
	}

	resp, err := s.refresher.EvaluateWatch(r.Context(), watch)
	if err != nil {
		log.Printf("initial evaluation of watch %d failed: %v", watch.ID, err)
	}
	writeJSON(w, map[string]any{"watch": watch, "evaluation": resp})
}

func (s *Server) handleListWatches(w http.ResponseWriter, r *http.Request) {
	email := r.URL.Query().Get("email")
	if email == "" {
		httpError(w, http.StatusBadRequest, "email query param is required")
		return
	}
	watches, err := s.store.ListWatches(r.Context(), email)
	if err != nil {
		httpError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, watches)
}

func (s *Server) handleDeleteWatch(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		httpError(w, http.StatusBadRequest, "invalid watch id")
		return
	}
	if err := s.store.DeleteWatch(r.Context(), id); err != nil {
		httpError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("writing response: %v", err)
	}
}

func httpError(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func spaHandler(dir string) http.Handler {
	fileServer := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := filepath.Join(dir, filepath.Clean(r.URL.Path))
		if info, err := os.Stat(path); err != nil || info.IsDir() {
			http.ServeFile(w, r, filepath.Join(dir, "index.html"))
			return
		}
		fileServer.ServeHTTP(w, r)
	})
}
