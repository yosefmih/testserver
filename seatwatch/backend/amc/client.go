package amc

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/cookiejar"
	"strconv"
	"sync"
	"time"
)

const DefaultTheatrePath = "/movie-theatres/new-york-city/amc-lincoln-square-13"

// Client fetches amctheatres.com pages politely: requests are globally spaced
// by minInterval regardless of caller concurrency, and 429 responses are
// retried with backoff.
type Client struct {
	httpClient  *http.Client
	baseURL     string
	theatrePath string
	minInterval time.Duration

	mu     sync.Mutex
	nextAt time.Time
}

func NewClient(theatrePath string, minInterval time.Duration) *Client {
	// The site sits behind Cloudflare bot management, which issues session
	// cookies (__cf_bm). Without a jar every request looks like a fresh
	// anonymous session and gets rate-limited almost immediately.
	jar, _ := cookiejar.New(nil)
	return &Client{
		httpClient:  &http.Client{Timeout: 30 * time.Second, Jar: jar},
		baseURL:     "https://www.amctheatres.com",
		theatrePath: theatrePath,
		minInterval: minInterval,
	}
}

func (c *Client) Showtimes(ctx context.Context, date time.Time) ([]Showtime, error) {
	url := fmt.Sprintf("%s%s/showtimes?date=%s", c.baseURL, c.theatrePath, date.Format("2006-01-02"))
	html, err := c.get(ctx, url)
	if err != nil {
		return nil, err
	}
	return ParseShowtimes(html)
}

func (c *Client) SeatingLayout(ctx context.Context, showtimeID int64) (SeatingLayout, error) {
	url := fmt.Sprintf("%s/showtimes/%d/seats", c.baseURL, showtimeID)
	html, err := c.get(ctx, url)
	if err != nil {
		return SeatingLayout{}, err
	}
	return ParseSeatingLayout(html)
}

func (c *Client) get(ctx context.Context, url string) (string, error) {
	backoffs := []time.Duration{3 * time.Second, 8 * time.Second, 20 * time.Second}
	const maxRetryAfter = 30 * time.Second
	for attempt := 0; ; attempt++ {
		if err := c.waitTurn(ctx); err != nil {
			return "", err
		}
		body, retryAfter, err := c.doGet(ctx, url)
		if err == nil {
			return body, nil
		}
		if retryAfter == 0 || attempt >= len(backoffs) {
			return "", err
		}
		delay := backoffs[attempt]
		if retryAfter > delay {
			delay = min(retryAfter, maxRetryAfter)
		}
		log.Printf("amc: throttled (attempt %d, retrying in %s): %s", attempt+1, delay, url)
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(delay):
		}
	}
}

// doGet performs one request. On 429 it returns a non-zero retryAfter hint.
func (c *Client) doGet(ctx context.Context, url string) (string, time.Duration, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", 0, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusTooManyRequests {
		retryAfter := time.Second
		if s, err := strconv.Atoi(resp.Header.Get("Retry-After")); err == nil && s > 0 {
			retryAfter = time.Duration(s) * time.Second
		}
		return "", retryAfter, fmt.Errorf("GET %s: status 429", url)
	}
	if resp.StatusCode != http.StatusOK {
		return "", 0, fmt.Errorf("GET %s: status %d", url, resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 20<<20))
	if err != nil {
		return "", 0, err
	}
	return string(body), 0, nil
}

func (c *Client) waitTurn(ctx context.Context) error {
	c.mu.Lock()
	now := time.Now()
	if c.nextAt.Before(now) {
		c.nextAt = now
	}
	wait := c.nextAt.Sub(now)
	c.nextAt = c.nextAt.Add(c.minInterval)
	c.mu.Unlock()

	if wait <= 0 {
		return nil
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(wait):
		return nil
	}
}
