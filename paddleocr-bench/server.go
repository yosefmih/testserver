package main

import (
	"bytes"
	"crypto/rand"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io"
	"log"
	"mime"
	"net/http"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/extension"
	goldmarkhtml "github.com/yuin/goldmark/renderer/html"
)

//go:embed templates/*.html
var templateFS embed.FS

type server struct {
	cfg       config
	jobs      *jobRegistry
	runner    *runner
	store     Store
	templates *template.Template
	markdown  goldmark.Markdown
	mux       *http.ServeMux
}

func newServer(cfg config, jobs *jobRegistry, runner *runner, store Store) http.Handler {
	s := &server{
		cfg:    cfg,
		jobs:   jobs,
		runner: runner,
		store:  store,
		templates: template.Must(template.New("").Funcs(template.FuncMap{
			"duration": formatDuration,
			"when":     formatTime,
			"bytes":    formatBytes,
			"rate":     func(f float64) string { return strconv.FormatFloat(f, 'f', 3, 64) },
		}).ParseFS(templateFS, "templates/*.html")),
		// PaddleOCR emits raw HTML tables inside its markdown, so unsafe rendering is required.
		markdown: goldmark.New(
			goldmark.WithExtensions(extension.GFM),
			goldmark.WithRendererOptions(goldmarkhtml.WithUnsafe()),
		),
		mux: http.NewServeMux(),
	}
	s.mux.HandleFunc("GET /{$}", s.index)
	s.mux.HandleFunc("POST /jobs", s.createJob)
	s.mux.HandleFunc("GET /jobs/{id}", s.showJob)
	s.mux.HandleFunc("GET /jobs/{id}/markdown", s.jobMarkdown)
	s.mux.HandleFunc("GET /jobs/{id}/chunks/{n}/{$}", s.showChunk)
	s.mux.HandleFunc("GET /jobs/{id}/chunks/{n}/{file...}", s.chunkFile)
	s.mux.HandleFunc("GET /api/jobs", s.apiJobs)
	s.mux.HandleFunc("GET /api/jobs/{id}", s.apiJob)
	s.mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { io.WriteString(w, "ok") })
	return s.mux
}

func (s *server) index(w http.ResponseWriter, r *http.Request) {
	s.render(w, "index.html", map[string]any{
		"Jobs":       s.jobs.List(),
		"Cfg":        s.cfg,
		"CanPresign": s.store.CanPresign(),
		"StoreName":  s.store.Describe(),
		"Error":      r.URL.Query().Get("error"),
	})
}

func (s *server) createJob(w http.ResponseWriter, r *http.Request) {
	job, pdf, err := s.parseJobForm(r)
	if err != nil {
		http.Redirect(w, r, "/?error="+template.URLQueryEscaper(err.Error()), http.StatusSeeOther)
		return
	}
	ctx := r.Context()
	if err := s.store.Put(ctx, job.InputKey, pdf, "application/pdf"); err != nil {
		s.fail(w, err)
		return
	}
	if err := s.jobs.Add(ctx, job); err != nil {
		s.fail(w, err)
		return
	}
	s.runner.Enqueue(job.ID)
	http.Redirect(w, r, "/jobs/"+job.ID, http.StatusSeeOther)
}

const maxUploadBytes = 512 << 20

func (s *server) parseJobForm(r *http.Request) (Job, []byte, error) {
	if err := r.ParseMultipartForm(maxUploadBytes); err != nil {
		return Job{}, nil, fmt.Errorf("parse upload: %w", err)
	}
	file, header, err := r.FormFile("pdf")
	if err != nil {
		return Job{}, nil, errors.New("choose a PDF file")
	}
	defer file.Close()
	pdf, err := io.ReadAll(file)
	if err != nil {
		return Job{}, nil, err
	}
	pages, err := pdfPageCount(pdf)
	if err != nil {
		return Job{}, nil, fmt.Errorf("not a readable PDF: %w", err)
	}

	chunkPages := formInt(r, "chunkPages", s.cfg.DefaultChunkPages)
	concurrency := formInt(r, "concurrency", s.cfg.DefaultConcurrency)
	if chunkPages < 1 || concurrency < 1 {
		return Job{}, nil, errors.New("chunk pages and concurrency must be at least 1")
	}
	delivery := Delivery(r.FormValue("delivery"))
	if delivery == "" {
		delivery = DeliveryBase64
	}
	if delivery == DeliveryURL && !s.store.CanPresign() {
		return Job{}, nil, errors.New("URL delivery needs the S3 store; set S3_BUCKET or use base64")
	}

	id := newJobID()
	job := Job{
		ID:          id,
		FileName:    header.Filename,
		InputKey:    "jobs/" + id + "/input.pdf",
		InputBytes:  int64(len(pdf)),
		Pages:       pages,
		ChunkPages:  chunkPages,
		Concurrency: concurrency,
		Delivery:    delivery,
		KeepImages:  r.FormValue("keepImages") == "on",
		Status:      JobQueued,
		CreatedAt:   time.Now(),
	}
	return job, pdf, nil
}

func newJobID() string {
	suffix := make([]byte, 3)
	rand.Read(suffix)
	return time.Now().UTC().Format("20060102-150405") + "-" + hex.EncodeToString(suffix)
}

func formInt(r *http.Request, key string, fallback int) int {
	v, err := strconv.Atoi(r.FormValue(key))
	if err != nil {
		return fallback
	}
	return v
}

func (s *server) showJob(w http.ResponseWriter, r *http.Request) {
	job, ok := s.jobs.Get(r.PathValue("id"))
	if !ok {
		http.NotFound(w, r)
		return
	}
	s.render(w, "job.html", map[string]any{
		"Job":     job,
		"Metrics": job.Metrics(),
	})
}

func (s *server) jobMarkdown(w http.ResponseWriter, r *http.Request) {
	job, ok := s.jobs.Get(r.PathValue("id"))
	if !ok {
		http.NotFound(w, r)
		return
	}
	var out bytes.Buffer
	for _, chunk := range job.Chunks {
		if chunk.Status != JobDone {
			continue
		}
		body, err := s.store.Get(r.Context(), path.Join(job.Dir(), chunk.Dir(), "result.md"))
		if err != nil {
			s.fail(w, err)
			return
		}
		fmt.Fprintf(&out, "<!-- chunk %d: pages %d-%d -->\n\n", chunk.Index, chunk.FirstPage, chunk.LastPage)
		out.Write(body)
		out.WriteString("\n\n")
	}
	w.Header().Set("Content-Type", "text/markdown; charset=utf-8")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.md"`, job.ID))
	w.Write(out.Bytes())
}

func (s *server) showChunk(w http.ResponseWriter, r *http.Request) {
	job, chunk, ok := s.lookupChunk(r)
	if !ok {
		http.NotFound(w, r)
		return
	}
	markdown, err := s.store.Get(r.Context(), path.Join(job.Dir(), chunk.Dir(), "result.md"))
	if err != nil {
		s.fail(w, err)
		return
	}
	var rendered bytes.Buffer
	if err := s.markdown.Convert(markdown, &rendered); err != nil {
		s.fail(w, err)
		return
	}
	s.render(w, "chunk.html", map[string]any{
		"Job":      job,
		"Chunk":    chunk,
		"Rendered": template.HTML(rendered.String()),
		"Raw":      string(markdown),
	})
}

// chunkFile serves anything stored under a chunk directory: the images the
// markdown references by relative path, result.json, and input.pdf.
func (s *server) chunkFile(w http.ResponseWriter, r *http.Request) {
	job, chunk, ok := s.lookupChunk(r)
	if !ok {
		http.NotFound(w, r)
		return
	}
	file := r.PathValue("file")
	if strings.Contains(file, "..") {
		http.NotFound(w, r)
		return
	}
	body, err := s.store.Get(r.Context(), path.Join(job.Dir(), chunk.Dir(), file))
	if errors.Is(err, errNotFound) {
		http.NotFound(w, r)
		return
	}
	if err != nil {
		s.fail(w, err)
		return
	}
	if contentType := mime.TypeByExtension(path.Ext(file)); contentType != "" {
		w.Header().Set("Content-Type", contentType)
	}
	w.Write(body)
}

func (s *server) lookupChunk(r *http.Request) (Job, Chunk, bool) {
	job, ok := s.jobs.Get(r.PathValue("id"))
	if !ok {
		return Job{}, Chunk{}, false
	}
	n, err := strconv.Atoi(r.PathValue("n"))
	if err != nil || n < 0 || n >= len(job.Chunks) {
		return Job{}, Chunk{}, false
	}
	return job, job.Chunks[n], true
}

func (s *server) apiJobs(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, s.jobs.List())
}

func (s *server) apiJob(w http.ResponseWriter, r *http.Request) {
	job, ok := s.jobs.Get(r.PathValue("id"))
	if !ok {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, struct {
		Job
		Metrics JobMetrics `json:"metrics"`
	}{job, job.Metrics()})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	enc.Encode(v)
}

func (s *server) render(w http.ResponseWriter, name string, data map[string]any) {
	var out bytes.Buffer
	if err := s.templates.ExecuteTemplate(&out, name, data); err != nil {
		s.fail(w, err)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write(out.Bytes())
}

func (s *server) fail(w http.ResponseWriter, err error) {
	log.Printf("request failed: %v", err)
	http.Error(w, err.Error(), http.StatusInternalServerError)
}

func formatDuration(d time.Duration) string {
	if d == 0 {
		return "-"
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs", d.Seconds())
	}
	return d.Truncate(time.Second).String()
}

func formatTime(t time.Time) string {
	if t.IsZero() {
		return "-"
	}
	return t.Local().Format("Jan 2 15:04:05")
}

func formatBytes(n int64) string {
	switch {
	case n >= 1<<20:
		return fmt.Sprintf("%.1f MB", float64(n)/(1<<20))
	case n >= 1<<10:
		return fmt.Sprintf("%.0f KB", float64(n)/(1<<10))
	}
	return fmt.Sprintf("%d B", n)
}
