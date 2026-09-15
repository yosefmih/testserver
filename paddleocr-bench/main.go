package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

func main() {
	cfg := loadConfig()
	ctx := context.Background()

	store, err := newStore(ctx, cfg)
	if err != nil {
		log.Fatalf("store: %v", err)
	}

	jobs, err := loadJobRegistry(ctx, store)
	if err != nil {
		log.Fatalf("load jobs: %v", err)
	}

	ocr := newOCRClient(cfg.PaddleOCRURL, cfg.OCRTimeout)
	runner := newRunner(jobs, store, ocr, cfg.PresignTTL)
	go runner.loop(ctx)

	server := newServer(cfg, jobs, runner, store)
	log.Printf("paddleocr-bench listening on :%s ocr=%s store=%s", cfg.Port, cfg.PaddleOCRURL, store.Describe())
	log.Fatal(http.ListenAndServe(":"+cfg.Port, server))
}

type config struct {
	Port               string
	PaddleOCRURL       string
	OCRTimeout         time.Duration
	S3Bucket           string
	S3Prefix           string
	LocalDataDir       string
	PresignTTL         time.Duration
	DefaultChunkPages  int
	DefaultConcurrency int
}

func loadConfig() config {
	return config{
		Port:               envString("PORT", "8096"),
		PaddleOCRURL:       envString("PADDLEOCR_URL", "http://localhost:8080"),
		OCRTimeout:         envDuration("OCR_TIMEOUT", 15*time.Minute),
		S3Bucket:           envString("S3_BUCKET", ""),
		S3Prefix:           envString("S3_PREFIX", "paddleocr-bench"),
		LocalDataDir:       envString("LOCAL_DATA_DIR", "./data"),
		PresignTTL:         envDuration("PRESIGN_TTL", time.Hour),
		DefaultChunkPages:  envInt("DEFAULT_CHUNK_PAGES", 10),
		DefaultConcurrency: envInt("DEFAULT_CONCURRENCY", 4),
	}
}

func envString(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	v, err := strconv.Atoi(os.Getenv(key))
	if err != nil {
		return fallback
	}
	return v
}

func envDuration(key string, fallback time.Duration) time.Duration {
	v, err := time.ParseDuration(os.Getenv(key))
	if err != nil {
		return fallback
	}
	return v
}
