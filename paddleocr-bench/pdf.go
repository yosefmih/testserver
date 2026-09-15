package main

import (
	"bytes"
	"fmt"

	"github.com/pdfcpu/pdfcpu/pkg/api"
	"github.com/pdfcpu/pdfcpu/pkg/pdfcpu/model"
)

// pdfcpu wants to create ~/.config/pdfcpu on first use, which fails on a
// read-only container filesystem. Disabling it keeps the library in-memory only.
func init() {
	model.ConfigPath = "disable"
}

func pdfConfiguration() *model.Configuration {
	conf := model.NewDefaultConfiguration()
	conf.ValidationMode = model.ValidationRelaxed
	return conf
}

func pdfPageCount(pdf []byte) (int, error) {
	return api.PageCount(bytes.NewReader(pdf), pdfConfiguration())
}

func pdfExtractPages(pdf []byte, firstPage, lastPage int) ([]byte, error) {
	var out bytes.Buffer
	pageRange := fmt.Sprintf("%d-%d", firstPage, lastPage)
	if err := api.Trim(bytes.NewReader(pdf), &out, []string{pageRange}, pdfConfiguration()); err != nil {
		return nil, fmt.Errorf("extract pages %s: %w", pageRange, err)
	}
	return out.Bytes(), nil
}

func planChunks(pages, chunkPages int) []Chunk {
	var chunks []Chunk
	for first := 1; first <= pages; first += chunkPages {
		last := min(first+chunkPages-1, pages)
		chunks = append(chunks, Chunk{
			Index:     len(chunks),
			FirstPage: first,
			LastPage:  last,
			Status:    JobQueued,
		})
	}
	return chunks
}
