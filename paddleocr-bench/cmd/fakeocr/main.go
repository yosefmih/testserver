// fakeocr imitates the PaddleOCR-VL pipeline service's /layout-parsing endpoint
// so paddleocr-bench can be exercised end to end without a GPU. It accepts the
// real request shape (URL or base64 PDF), sleeps a configurable time per page,
// and returns per-page markdown with one image reference.
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/pdfcpu/pdfcpu/pkg/api"
	"github.com/pdfcpu/pdfcpu/pkg/pdfcpu/model"
)

func main() {
	model.ConfigPath = "disable"
	port := envOr("PORT", "8118")
	secondsPerPage, _ := strconv.ParseFloat(envOr("FAKE_SECONDS_PER_PAGE", "0.3"), 64)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { io.WriteString(w, "ok") })
	mux.HandleFunc("POST /layout-parsing", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			File                 string `json:"file"`
			ReturnMarkdownImages bool   `json:"returnMarkdownImages"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		pdf, err := loadFile(req.File)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		pages, err := api.PageCount(bytes.NewReader(pdf), model.NewDefaultConfiguration())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		time.Sleep(time.Duration(float64(pages) * secondsPerPage * float64(time.Second)))

		var results []map[string]any
		for i := 1; i <= pages; i++ {
			markdown := map[string]any{"text": fakeMarkdown(i, req.ReturnMarkdownImages)}
			if req.ReturnMarkdownImages {
				markdown["images"] = map[string]string{fmt.Sprintf("imgs/page_%d.png", i): onePixelPNG}
			}
			results = append(results, map[string]any{
				"prunedResult": map[string]any{"page": i, "fake": true},
				"markdown":     markdown,
			})
		}
		json.NewEncoder(w).Encode(map[string]any{
			"logId":     "fake",
			"errorCode": 0,
			"errorMsg":  "Success",
			"result":    map[string]any{"layoutParsingResults": results},
		})
	})
	log.Printf("fakeocr listening on :%s (%.2fs per page)", port, secondsPerPage)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func loadFile(file string) ([]byte, error) {
	if strings.HasPrefix(file, "http://") || strings.HasPrefix(file, "https://") {
		resp, err := http.Get(file)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("fetch %s: %s", file, resp.Status)
		}
		return io.ReadAll(resp.Body)
	}
	return base64.StdEncoding.DecodeString(file)
}

func fakeMarkdown(page int, withImage bool) string {
	var b strings.Builder
	fmt.Fprintf(&b, "# Page %d\n\nLorem ipsum dolor sit amet, consectetur adipiscing elit.\n\n", page)
	fmt.Fprintf(&b, "<table><tr><td>row</td><td>%d</td></tr></table>\n\n", page)
	if withImage {
		fmt.Fprintf(&b, "![figure](imgs/page_%d.png)\n", page)
	}
	return b.String()
}

const onePixelPNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
