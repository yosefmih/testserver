package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// ocrClient talks to the PaddleOCR-VL pipeline service (the paddlex --serve
// container), whose contract is documented under "Service Deployment" in
// docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md of the PaddleOCR repo.
type ocrClient struct {
	baseURL string
	http    *http.Client
}

func newOCRClient(baseURL string, timeout time.Duration) ocrClient {
	return ocrClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: timeout},
	}
}

const fileTypePDF = 0

type layoutParsingRequest struct {
	// File is either a URL the server fetches or the base64-encoded file bytes.
	File                      string `json:"file"`
	FileType                  int    `json:"fileType"`
	UseDocOrientationClassify bool   `json:"useDocOrientationClassify"`
	UseDocUnwarping           bool   `json:"useDocUnwarping"`
	Visualize                 bool   `json:"visualize"`
	ReturnMarkdownImages      bool   `json:"returnMarkdownImages"`
}

type layoutParsingResponse struct {
	LogID     string `json:"logId"`
	ErrorCode int    `json:"errorCode"`
	ErrorMsg  string `json:"errorMsg"`
	Result    struct {
		LayoutParsingResults []pageResult `json:"layoutParsingResults"`
	} `json:"result"`
}

type pageResult struct {
	PrunedResult json.RawMessage `json:"prunedResult"`
	Markdown     struct {
		Text string `json:"text"`
		// Images maps a relative path referenced from Text to base64 image bytes.
		Images map[string]string `json:"images"`
	} `json:"markdown"`
}

type ocrCallStats struct {
	RequestBytes  int64
	ResponseBytes int64
	Latency       time.Duration
}

func (c ocrClient) LayoutParsing(ctx context.Context, req layoutParsingRequest) (layoutParsingResponse, ocrCallStats, error) {
	var parsed layoutParsingResponse
	body, err := json.Marshal(req)
	if err != nil {
		return parsed, ocrCallStats{}, err
	}
	stats := ocrCallStats{RequestBytes: int64(len(body))}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/layout-parsing", bytes.NewReader(body))
	if err != nil {
		return parsed, stats, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	start := time.Now()
	resp, err := c.http.Do(httpReq)
	if err != nil {
		return parsed, stats, err
	}
	defer resp.Body.Close()
	respBody, err := io.ReadAll(resp.Body)
	stats.Latency = time.Since(start)
	stats.ResponseBytes = int64(len(respBody))
	if err != nil {
		return parsed, stats, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return parsed, stats, fmt.Errorf("layout-parsing returned %d: %s", resp.StatusCode, truncate(string(respBody), 500))
	}
	if err := json.Unmarshal(respBody, &parsed); err != nil {
		return parsed, stats, fmt.Errorf("decode response: %w", err)
	}
	if parsed.ErrorCode != 0 {
		return parsed, stats, fmt.Errorf("layout-parsing error %d: %s", parsed.ErrorCode, parsed.ErrorMsg)
	}
	return parsed, stats, nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
