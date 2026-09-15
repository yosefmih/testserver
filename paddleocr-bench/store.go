package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// Store holds input PDFs, page chunks, OCR results, and job manifests. Keys are
// slash-separated paths such as "jobs/<id>/chunks/3/result.md".
type Store interface {
	Put(ctx context.Context, key string, body []byte, contentType string) error
	Get(ctx context.Context, key string) ([]byte, error)
	ListKeys(ctx context.Context, prefix string) ([]string, error)
	// PresignedURL returns a URL the PaddleOCR server can fetch the object from.
	PresignedURL(ctx context.Context, key string, ttl time.Duration) (string, error)
	CanPresign() bool
	Describe() string
}

var errNotFound = errors.New("not found")

func newStore(ctx context.Context, cfg config) (Store, error) {
	if cfg.S3Bucket != "" {
		return newS3Store(ctx, cfg.S3Bucket, cfg.S3Prefix)
	}
	return newLocalStore(cfg.LocalDataDir)
}

type s3Store struct {
	client  *s3.Client
	presign *s3.PresignClient
	bucket  string
	prefix  string
}

func newS3Store(ctx context.Context, bucket, prefix string) (s3Store, error) {
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx)
	if err != nil {
		return s3Store{}, fmt.Errorf("aws config: %w", err)
	}
	client := s3.NewFromConfig(awsCfg)
	return s3Store{
		client:  client,
		presign: s3.NewPresignClient(client),
		bucket:  bucket,
		prefix:  strings.Trim(prefix, "/"),
	}, nil
}

func (s s3Store) fullKey(key string) string {
	if s.prefix == "" {
		return key
	}
	return s.prefix + "/" + key
}

func (s s3Store) Put(ctx context.Context, key string, body []byte, contentType string) error {
	_, err := s.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      &s.bucket,
		Key:         stringPtr(s.fullKey(key)),
		Body:        bytes.NewReader(body),
		ContentType: &contentType,
	})
	return err
}

func (s s3Store) Get(ctx context.Context, key string) ([]byte, error) {
	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: &s.bucket,
		Key:    stringPtr(s.fullKey(key)),
	})
	if err != nil {
		if strings.Contains(err.Error(), "NoSuchKey") || strings.Contains(err.Error(), "NotFound") {
			return nil, errNotFound
		}
		return nil, err
	}
	defer out.Body.Close()
	return io.ReadAll(out.Body)
}

func (s s3Store) ListKeys(ctx context.Context, prefix string) ([]string, error) {
	var keys []string
	full := s.fullKey(prefix)
	paginator := s3.NewListObjectsV2Paginator(s.client, &s3.ListObjectsV2Input{
		Bucket: &s.bucket,
		Prefix: &full,
	})
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, obj := range page.Contents {
			keys = append(keys, strings.TrimPrefix(*obj.Key, s.prefix+"/"))
		}
	}
	return keys, nil
}

func (s s3Store) PresignedURL(ctx context.Context, key string, ttl time.Duration) (string, error) {
	req, err := s.presign.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: &s.bucket,
		Key:    stringPtr(s.fullKey(key)),
	}, s3.WithPresignExpires(ttl))
	if err != nil {
		return "", err
	}
	return req.URL, nil
}

func (s s3Store) CanPresign() bool { return true }

func (s s3Store) Describe() string { return "s3://" + s.bucket + "/" + s.prefix }

func stringPtr(s string) *string { return &s }

// localStore is a filesystem store for running the app without AWS credentials.
// It cannot presign, so jobs must use base64 delivery.
type localStore struct {
	root string
}

func newLocalStore(root string) (localStore, error) {
	if err := os.MkdirAll(root, 0o755); err != nil {
		return localStore{}, err
	}
	return localStore{root: root}, nil
}

func (l localStore) path(key string) string {
	return filepath.Join(l.root, filepath.FromSlash(key))
}

func (l localStore) Put(_ context.Context, key string, body []byte, _ string) error {
	path := l.path(key)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, body, 0o644)
}

func (l localStore) Get(_ context.Context, key string) ([]byte, error) {
	body, err := os.ReadFile(l.path(key))
	if errors.Is(err, fs.ErrNotExist) {
		return nil, errNotFound
	}
	return body, err
}

func (l localStore) ListKeys(_ context.Context, prefix string) ([]string, error) {
	var keys []string
	err := filepath.WalkDir(l.root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		rel, err := filepath.Rel(l.root, path)
		if err != nil {
			return err
		}
		key := filepath.ToSlash(rel)
		if strings.HasPrefix(key, prefix) {
			keys = append(keys, key)
		}
		return nil
	})
	return keys, err
}

func (l localStore) PresignedURL(context.Context, string, time.Duration) (string, error) {
	return "", errors.New("local store cannot presign URLs; use base64 delivery")
}

func (l localStore) CanPresign() bool { return false }

func (l localStore) Describe() string { return "local:" + l.root }
