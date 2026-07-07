package amc

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type Showtime struct {
	ID         int64     `json:"id"`
	MovieSlug  string    `json:"movieSlug"`
	MovieTitle string    `json:"movieTitle"`
	Format     string    `json:"format"`
	ShowAt     time.Time `json:"showAt"`
	Status     string    `json:"status"`
}

type SeatingLayout struct {
	Columns int    `json:"columns"`
	Rows    int    `json:"rows"`
	Seats   []Seat `json:"seats"`
}

type Seat struct {
	Available     bool   `json:"available"`
	Column        int    `json:"column"`
	Row           int    `json:"row"`
	Name          string `json:"name"`
	Type          string `json:"type"`
	SeatTier      string `json:"seatTier"`
	ShouldDisplay bool   `json:"shouldDisplay"`
}

// The AMC site is a Next.js app that streams its data into the HTML as React
// Server Component "flight" chunks: self.__next_f.push([1,"<escaped payload>"]).
// Decoding and concatenating those string chunks yields one big payload that
// embeds plain JSON objects we can extract.
var flightChunkRe = regexp.MustCompile(`self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)`)

func decodeFlightPayload(html string) (string, error) {
	var b strings.Builder
	matches := flightChunkRe.FindAllStringSubmatch(html, -1)
	if len(matches) == 0 {
		return "", fmt.Errorf("no flight payload chunks found in page")
	}
	for _, m := range matches {
		var chunk string
		if err := json.Unmarshal([]byte(`"`+m[1]+`"`), &chunk); err != nil {
			return "", fmt.Errorf("decoding flight chunk: %w", err)
		}
		b.WriteString(chunk)
	}
	return b.String(), nil
}

var (
	movieTitleRe = regexp.MustCompile(`\["\$","option","[^"]*",\{"value":"([a-z0-9-]+)","children":"([^"]+)"\}`)
	formatRe     = regexp.MustCompile(`"id":"([a-z0-9-]+)-\d+","children":\["\$","div",null,\{"className":"[^"]*","children":\[\["\$","span",null,\{"children":"([^"]+)"`)
	showtimeRe   = regexp.MustCompile(`"showtime":\{"showtimeId":(\d+),[^}]*"status":"([^"]+)","showDateTimeUtc":"([^"]+)"[^}]*\}[^}]*\},"aria-describedby":"([^"]+)"`)
	groupNumRe   = regexp.MustCompile(`-\d+$`)
)

func ParseShowtimes(html string) ([]Showtime, error) {
	payload, err := decodeFlightPayload(html)
	if err != nil {
		return nil, err
	}

	titles := map[string]string{}
	for _, m := range movieTitleRe.FindAllStringSubmatch(payload, -1) {
		titles[m[1]] = m[2]
	}

	formats := map[string]string{}
	for _, m := range formatRe.FindAllStringSubmatch(payload, -1) {
		formats[m[1]] = m[2]
	}

	var showtimes []Showtime
	for _, m := range showtimeRe.FindAllStringSubmatch(payload, -1) {
		id, err := strconv.ParseInt(m[1], 10, 64)
		if err != nil {
			continue
		}
		showAt, err := time.Parse(time.RFC3339, m[3])
		if err != nil {
			continue
		}
		ariaParts := strings.Fields(m[4])
		if len(ariaParts) < 4 {
			continue
		}
		slug := ariaParts[0]
		formatKey := groupNumRe.ReplaceAllString(ariaParts[3], "")
		showtimes = append(showtimes, Showtime{
			ID:         id,
			MovieSlug:  slug,
			MovieTitle: titles[slug],
			Format:     formats[formatKey],
			ShowAt:     showAt,
			Status:     m[2],
		})
	}
	return showtimes, nil
}

func ParseSeatingLayout(html string) (SeatingLayout, error) {
	payload, err := decodeFlightPayload(html)
	if err != nil {
		return SeatingLayout{}, err
	}
	const marker = `"seatingLayout":`
	i := strings.Index(payload, marker)
	if i < 0 {
		return SeatingLayout{}, fmt.Errorf("no seatingLayout found in page")
	}
	obj, err := extractJSONObject(payload[i+len(marker):])
	if err != nil {
		return SeatingLayout{}, fmt.Errorf("extracting seatingLayout: %w", err)
	}
	var layout SeatingLayout
	if err := json.Unmarshal([]byte(obj), &layout); err != nil {
		return SeatingLayout{}, fmt.Errorf("parsing seatingLayout: %w", err)
	}
	if len(layout.Seats) == 0 {
		return SeatingLayout{}, fmt.Errorf("seatingLayout has no seats")
	}
	return layout, nil
}

func extractJSONObject(s string) (string, error) {
	start := strings.IndexByte(s, '{')
	if start < 0 {
		return "", fmt.Errorf("no object start found")
	}
	depth := 0
	inString := false
	escaped := false
	for i := start; i < len(s); i++ {
		c := s[i]
		if inString {
			switch {
			case escaped:
				escaped = false
			case c == '\\':
				escaped = true
			case c == '"':
				inString = false
			}
			continue
		}
		switch c {
		case '"':
			inString = true
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return s[start : i+1], nil
			}
		}
	}
	return "", fmt.Errorf("unbalanced object")
}
