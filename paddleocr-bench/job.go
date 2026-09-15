package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

type JobStatus string

const (
	JobQueued  JobStatus = "queued"
	JobRunning JobStatus = "running"
	JobDone    JobStatus = "done"
	JobFailed  JobStatus = "failed"
)

// Delivery is how a chunk reaches the PaddleOCR server: a presigned S3 URL the
// server fetches itself, or the PDF bytes base64-encoded inside the request body.
type Delivery string

const (
	DeliveryURL    Delivery = "url"
	DeliveryBase64 Delivery = "base64"
)

// Job is one uploaded PDF, split into page chunks that are OCRed concurrently.
type Job struct {
	ID          string    `json:"id"`
	FileName    string    `json:"fileName"`
	InputKey    string    `json:"inputKey"`
	InputBytes  int64     `json:"inputBytes"`
	Pages       int       `json:"pages"`
	ChunkPages  int       `json:"chunkPages"`
	Concurrency int       `json:"concurrency"`
	Delivery    Delivery  `json:"delivery"`
	KeepImages  bool      `json:"keepImages"`
	Status      JobStatus `json:"status"`
	Error       string    `json:"error,omitempty"`
	CreatedAt   time.Time `json:"createdAt"`
	StartedAt   time.Time `json:"startedAt,omitzero"`
	SplitMillis int64     `json:"splitMillis"`
	FinishedAt  time.Time `json:"finishedAt,omitzero"`
	Chunks      []Chunk   `json:"chunks"`
}

type Chunk struct {
	Index         int       `json:"index"`
	FirstPage     int       `json:"firstPage"`
	LastPage      int       `json:"lastPage"`
	Key           string    `json:"key"`
	Status        JobStatus `json:"status"`
	Error         string    `json:"error,omitempty"`
	StartedAt     time.Time `json:"startedAt,omitzero"`
	FinishedAt    time.Time `json:"finishedAt,omitzero"`
	OCRMillis     int64     `json:"ocrMillis"`
	RequestBytes  int64     `json:"requestBytes"`
	ResponseBytes int64     `json:"responseBytes"`
	MarkdownChars int       `json:"markdownChars"`
	ImageCount    int       `json:"imageCount"`
}

func (c Chunk) Pages() int { return c.LastPage - c.FirstPage + 1 }

func (c Chunk) Dir() string { return fmt.Sprintf("chunks/%d", c.Index) }

func (c Chunk) SecondsPerPage() float64 {
	if c.Status != JobDone || c.Pages() == 0 {
		return 0
	}
	return float64(c.OCRMillis) / 1000 / float64(c.Pages())
}

func (j Job) Dir() string { return "jobs/" + j.ID }

func (j Job) ManifestKey() string { return j.Dir() + "/job.json" }

func (j Job) IsActive() bool { return j.Status == JobQueued || j.Status == JobRunning }

// JobMetrics is what the benchmark is after: how many pages per second the OCR
// service sustained for this job, and how long individual chunk requests took.
type JobMetrics struct {
	PagesDone      int
	ChunksDone     int
	ChunksFailed   int
	Elapsed        time.Duration
	OCRElapsed     time.Duration
	PagesPerSecond float64
	SecondsPerPage float64
	LatencyMean    time.Duration
	LatencyP50     time.Duration
	LatencyP95     time.Duration
	LatencyMax     time.Duration
	Images         int
	MarkdownChars  int
}

func (j Job) Metrics() JobMetrics {
	var m JobMetrics
	var latencies []time.Duration
	var firstStart, lastFinish time.Time
	for _, c := range j.Chunks {
		if !c.StartedAt.IsZero() && (firstStart.IsZero() || c.StartedAt.Before(firstStart)) {
			firstStart = c.StartedAt
		}
		if c.FinishedAt.After(lastFinish) {
			lastFinish = c.FinishedAt
		}
		switch c.Status {
		case JobDone:
			m.PagesDone += c.Pages()
			m.ChunksDone++
			m.Images += c.ImageCount
			m.MarkdownChars += c.MarkdownChars
			latencies = append(latencies, time.Duration(c.OCRMillis)*time.Millisecond)
		case JobFailed:
			m.ChunksFailed++
		}
	}

	m.Elapsed = j.elapsedSince(j.StartedAt)
	if !firstStart.IsZero() {
		if j.IsActive() {
			m.OCRElapsed = time.Since(firstStart)
		} else {
			m.OCRElapsed = lastFinish.Sub(firstStart)
		}
	}
	if m.OCRElapsed > 0 && m.PagesDone > 0 {
		m.PagesPerSecond = float64(m.PagesDone) / m.OCRElapsed.Seconds()
		m.SecondsPerPage = 1 / m.PagesPerSecond
	}

	if len(latencies) > 0 {
		sort.Slice(latencies, func(a, b int) bool { return latencies[a] < latencies[b] })
		var total time.Duration
		for _, l := range latencies {
			total += l
		}
		m.LatencyMean = total / time.Duration(len(latencies))
		m.LatencyP50 = latencies[len(latencies)/2]
		m.LatencyP95 = latencies[(len(latencies)*95)/100]
		m.LatencyMax = latencies[len(latencies)-1]
	}
	return m
}

func (j Job) elapsedSince(start time.Time) time.Duration {
	if start.IsZero() {
		return 0
	}
	if j.IsActive() {
		return time.Since(start)
	}
	return j.FinishedAt.Sub(start)
}

// jobRegistry is the in-memory index of jobs, persisted as one manifest per job
// in the store so results survive restarts.
type jobRegistry struct {
	store Store
	mu    sync.Mutex
	jobs  map[string]*Job
}

func loadJobRegistry(ctx context.Context, store Store) (*jobRegistry, error) {
	r := &jobRegistry{store: store, jobs: map[string]*Job{}}
	keys, err := store.ListKeys(ctx, "jobs/")
	if err != nil {
		return nil, err
	}
	for _, key := range keys {
		if !strings.HasSuffix(key, "/job.json") {
			continue
		}
		body, err := store.Get(ctx, key)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", key, err)
		}
		var job Job
		if err := json.Unmarshal(body, &job); err != nil {
			return nil, fmt.Errorf("parse %s: %w", key, err)
		}
		if job.IsActive() {
			job.Status = JobFailed
			job.Error = "interrupted by restart"
			job.FinishedAt = time.Now()
		}
		r.jobs[job.ID] = &job
	}
	return r, nil
}

func (r *jobRegistry) Add(ctx context.Context, job Job) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.jobs[job.ID] = &job
	return r.persist(ctx, job)
}

func (r *jobRegistry) Get(id string) (Job, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	job, ok := r.jobs[id]
	if !ok {
		return Job{}, false
	}
	return job.snapshot(), true
}

func (r *jobRegistry) List() []Job {
	r.mu.Lock()
	defer r.mu.Unlock()
	jobs := make([]Job, 0, len(r.jobs))
	for _, job := range r.jobs {
		jobs = append(jobs, job.snapshot())
	}
	sort.Slice(jobs, func(a, b int) bool { return jobs[a].CreatedAt.After(jobs[b].CreatedAt) })
	return jobs
}

// Update applies mutate under the registry lock and persists the result.
func (r *jobRegistry) Update(ctx context.Context, id string, mutate func(*Job)) (Job, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	job, ok := r.jobs[id]
	if !ok {
		return Job{}, fmt.Errorf("job %s: %w", id, errNotFound)
	}
	mutate(job)
	return job.snapshot(), r.persist(ctx, *job)
}

func (r *jobRegistry) persist(ctx context.Context, job Job) error {
	body, err := json.MarshalIndent(job, "", "  ")
	if err != nil {
		return err
	}
	return r.store.Put(ctx, job.ManifestKey(), body, "application/json")
}

func (j *Job) snapshot() Job {
	copied := *j
	copied.Chunks = append([]Chunk(nil), j.Chunks...)
	return copied
}
