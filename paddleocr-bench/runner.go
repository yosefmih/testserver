package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"path"
	"strings"
	"sync"
	"time"
)

// runner processes jobs one at a time so each benchmark run has the OCR service
// to itself; within a job, chunks are OCRed with the job's concurrency.
type runner struct {
	jobs       *jobRegistry
	store      Store
	ocr        ocrClient
	presignTTL time.Duration
	queue      chan string
}

func newRunner(jobs *jobRegistry, store Store, ocr ocrClient, presignTTL time.Duration) *runner {
	return &runner{
		jobs:       jobs,
		store:      store,
		ocr:        ocr,
		presignTTL: presignTTL,
		queue:      make(chan string, 256),
	}
}

func (r *runner) Enqueue(id string) { r.queue <- id }

func (r *runner) loop(ctx context.Context) {
	for id := range r.queue {
		if err := r.run(ctx, id); err != nil {
			log.Printf("job %s: %v", id, err)
			r.jobs.Update(ctx, id, func(j *Job) {
				j.Status = JobFailed
				j.Error = err.Error()
				j.FinishedAt = time.Now()
			})
		}
	}
}

func (r *runner) run(ctx context.Context, id string) error {
	job, ok := r.jobs.Get(id)
	if !ok {
		return errNotFound
	}
	input, err := r.store.Get(ctx, job.InputKey)
	if err != nil {
		return fmt.Errorf("read input: %w", err)
	}

	job, err = r.jobs.Update(ctx, id, func(j *Job) {
		j.Status = JobRunning
		j.StartedAt = time.Now()
		j.Chunks = planChunks(j.Pages, j.ChunkPages)
	})
	if err != nil {
		return err
	}

	splitStart := time.Now()
	for i, chunk := range job.Chunks {
		chunkPDF, err := pdfExtractPages(input, chunk.FirstPage, chunk.LastPage)
		if err != nil {
			return err
		}
		key := path.Join(job.Dir(), chunk.Dir(), "input.pdf")
		if err := r.store.Put(ctx, key, chunkPDF, "application/pdf"); err != nil {
			return fmt.Errorf("store chunk %d: %w", i, err)
		}
		job.Chunks[i].Key = key
	}
	job, err = r.jobs.Update(ctx, id, func(j *Job) {
		j.Chunks = job.Chunks
		j.SplitMillis = time.Since(splitStart).Milliseconds()
	})
	if err != nil {
		return err
	}

	var wg sync.WaitGroup
	pending := make(chan Chunk)
	for range job.Concurrency {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for chunk := range pending {
				r.processChunk(ctx, job, chunk)
			}
		}()
	}
	for _, chunk := range job.Chunks {
		pending <- chunk
	}
	close(pending)
	wg.Wait()

	_, err = r.jobs.Update(ctx, id, func(j *Job) {
		j.FinishedAt = time.Now()
		failed := j.Metrics().ChunksFailed
		if failed > 0 {
			j.Status = JobFailed
			j.Error = fmt.Sprintf("%d of %d chunks failed", failed, len(j.Chunks))
			return
		}
		j.Status = JobDone
	})
	return err
}

func (r *runner) processChunk(ctx context.Context, job Job, chunk Chunk) {
	r.jobs.Update(ctx, job.ID, func(j *Job) {
		j.Chunks[chunk.Index].Status = JobRunning
		j.Chunks[chunk.Index].StartedAt = time.Now()
	})

	result, stats, err := r.ocrChunk(ctx, job, chunk)
	if err == nil {
		err = r.saveChunkResult(ctx, job, chunk, result)
	}

	r.jobs.Update(ctx, job.ID, func(j *Job) {
		c := &j.Chunks[chunk.Index]
		c.FinishedAt = time.Now()
		c.OCRMillis = stats.Latency.Milliseconds()
		c.RequestBytes = stats.RequestBytes
		c.ResponseBytes = stats.ResponseBytes
		if err != nil {
			c.Status = JobFailed
			c.Error = err.Error()
			return
		}
		c.Status = JobDone
		c.MarkdownChars = result.markdownChars
		c.ImageCount = result.imageCount
	})
}

func (r *runner) ocrChunk(ctx context.Context, job Job, chunk Chunk) (chunkResult, ocrCallStats, error) {
	file, err := r.chunkPayload(ctx, job, chunk)
	if err != nil {
		return chunkResult{}, ocrCallStats{}, err
	}
	resp, stats, err := r.ocr.LayoutParsing(ctx, layoutParsingRequest{
		File:                 file,
		FileType:             fileTypePDF,
		ReturnMarkdownImages: job.KeepImages,
	})
	if err != nil {
		return chunkResult{}, stats, err
	}
	return newChunkResult(resp.Result.LayoutParsingResults), stats, nil
}

func (r *runner) chunkPayload(ctx context.Context, job Job, chunk Chunk) (string, error) {
	if job.Delivery == DeliveryURL {
		return r.store.PresignedURL(ctx, chunk.Key, r.presignTTL)
	}
	chunkPDF, err := r.store.Get(ctx, chunk.Key)
	if err != nil {
		return "", fmt.Errorf("read chunk: %w", err)
	}
	return base64.StdEncoding.EncodeToString(chunkPDF), nil
}

// chunkResult is the OCR output of one chunk flattened for storage: one markdown
// document for all its pages, the pruned per-page JSON, and the referenced images.
type chunkResult struct {
	markdown      string
	markdownChars int
	prunedPages   []json.RawMessage
	images        map[string]string
	imageCount    int
}

func newChunkResult(pages []pageResult) chunkResult {
	var sections []string
	result := chunkResult{images: map[string]string{}}
	for i, page := range pages {
		sections = append(sections, fmt.Sprintf("<!-- page %d -->\n\n%s", i+1, page.Markdown.Text))
		result.prunedPages = append(result.prunedPages, page.PrunedResult)
		for relPath, data := range page.Markdown.Images {
			result.images[relPath] = data
		}
	}
	result.markdown = strings.Join(sections, "\n\n")
	result.markdownChars = len(result.markdown)
	result.imageCount = len(result.images)
	return result
}

func (r *runner) saveChunkResult(ctx context.Context, job Job, chunk Chunk, result chunkResult) error {
	dir := path.Join(job.Dir(), chunk.Dir())
	if err := r.store.Put(ctx, dir+"/result.md", []byte(result.markdown), "text/markdown"); err != nil {
		return err
	}
	pruned, err := json.Marshal(result.prunedPages)
	if err != nil {
		return err
	}
	if err := r.store.Put(ctx, dir+"/result.json", pruned, "application/json"); err != nil {
		return err
	}
	for relPath, data := range result.images {
		image, err := base64.StdEncoding.DecodeString(data)
		if err != nil {
			return fmt.Errorf("decode image %s: %w", relPath, err)
		}
		if err := r.store.Put(ctx, path.Join(dir, relPath), image, "image/jpeg"); err != nil {
			return err
		}
	}
	return nil
}
