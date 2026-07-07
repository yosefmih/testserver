package amc

import (
	"os"
	"testing"
)

func TestParseShowtimes(t *testing.T) {
	html, err := os.ReadFile("testdata/showtimes.html")
	if err != nil {
		t.Fatal(err)
	}
	showtimes, err := ParseShowtimes(string(html))
	if err != nil {
		t.Fatal(err)
	}
	if len(showtimes) != 56 {
		t.Fatalf("expected 56 showtimes, got %d", len(showtimes))
	}
	var supergirl *Showtime
	for i := range showtimes {
		if showtimes[i].ID == 144791990 {
			supergirl = &showtimes[i]
		}
	}
	if supergirl == nil {
		t.Fatal("showtime 144791990 not found")
	}
	if supergirl.MovieTitle != "Supergirl" {
		t.Errorf("title = %q", supergirl.MovieTitle)
	}
	if supergirl.MovieSlug != "supergirl-77031" {
		t.Errorf("slug = %q", supergirl.MovieSlug)
	}
	if supergirl.Format != "Open Caption (On-screen Subtitles)" {
		t.Errorf("format = %q", supergirl.Format)
	}
	if got := supergirl.ShowAt.UTC().Format("2006-01-02T15:04"); got != "2026-07-08T23:15" {
		t.Errorf("showAt = %s", got)
	}
	for _, st := range showtimes {
		if st.MovieTitle == "" {
			t.Errorf("showtime %d has no title (slug %s)", st.ID, st.MovieSlug)
		}
	}
}

func TestParseSeatingLayout(t *testing.T) {
	html, err := os.ReadFile("testdata/seats.html")
	if err != nil {
		t.Fatal(err)
	}
	layout, err := ParseSeatingLayout(string(html))
	if err != nil {
		t.Fatal(err)
	}
	if layout.Columns != 42 || layout.Rows != 12 {
		t.Errorf("grid = %dx%d", layout.Columns, layout.Rows)
	}
	if len(layout.Seats) != 504 {
		t.Errorf("seats = %d", len(layout.Seats))
	}
	byName := map[string]Seat{}
	displayable := 0
	for _, s := range layout.Seats {
		if s.ShouldDisplay {
			displayable++
			byName[s.Name] = s
		}
	}
	if displayable != 480 {
		t.Errorf("displayable = %d", displayable)
	}
	f10, ok := byName["F10"]
	if !ok {
		t.Fatal("seat F10 not found")
	}
	if !f10.Available || f10.Row != 6 || f10.Column != 33 || f10.Type != "CanReserve" {
		t.Errorf("F10 = %+v", f10)
	}
}
