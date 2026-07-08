package main

import (
	"reflect"
	"testing"

	"seatwatch/amc"
)

func seat(name string, row, col int, available bool) amc.Seat {
	return amc.Seat{Name: name, Row: row, Column: col, Available: available, Type: "CanReserve", ShouldDisplay: true}
}

func TestSeatGroupRanking(t *testing.T) {
	var seats []amc.Seat
	rowLetters := []string{"A", "B", "C"}
	for r := 1; r <= 3; r++ {
		for c := 1; c <= 9; c++ {
			seats = append(seats, seat(rowLetters[r-1]+string(rune('0'+c)), r, c, true))
		}
	}
	layout := amc.SeatingLayout{Columns: 9, Rows: 3, Seats: seats}
	all := make([]string, len(seats))
	for i, s := range seats {
		all[i] = s.Name
	}

	groups, open := FindAdjacentSeatGroups(layout, all, 2)
	if open != 27 {
		t.Fatalf("openSeats = %d", open)
	}
	best := groups[0]
	// ideal is dead center (~col 5) about two-thirds back (row B of 3)
	if best[0][0] != 'B' {
		t.Errorf("best group %v not in the two-thirds-back row", best)
	}
	for _, name := range best {
		col := int(name[1] - '0')
		if col < 4 || col > 6 {
			t.Errorf("best group %v not centered", best)
		}
	}
	worst := groups[len(groups)-1]
	if c := int(worst[0][1] - '0'); c > 2 && c < 8 {
		t.Errorf("worst group %v unexpectedly central", worst)
	}
}

func TestFindAdjacentSeatGroups(t *testing.T) {
	layout := amc.SeatingLayout{
		Columns: 10,
		Rows:    2,
		Seats: []amc.Seat{
			seat("C4", 1, 2, true),
			seat("C3", 1, 3, true),
			// aisle gap at column 4
			seat("C2", 1, 5, true),
			seat("C1", 1, 6, false),
			seat("D2", 2, 2, true),
			seat("D1", 2, 3, true),
		},
	}

	tests := []struct {
		name      string
		tolerable []string
		partySize int
		want      [][]string
		wantOpen  int
	}{
		{"pair in same row", []string{"C4", "C3", "D2"}, 2, [][]string{{"C4", "C3"}}, 3},
		{"gap breaks adjacency", []string{"C3", "C2"}, 2, nil, 2},
		{"unavailable seat breaks run", []string{"C2", "C1"}, 2, nil, 1},
		{"single seat", []string{"C2"}, 1, [][]string{{"C2"}}, 1},
		{"seats outside tolerable set ignored", []string{"D1"}, 2, nil, 1},
		{"overlapping runs, best seats first", []string{"C4", "C3", "C2", "D2", "D1"}, 2, [][]string{{"D2", "D1"}, {"C4", "C3"}}, 5},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, open := FindAdjacentSeatGroups(layout, tt.tolerable, tt.partySize)
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("groups = %v, want %v", got, tt.want)
			}
			if open != tt.wantOpen {
				t.Errorf("openSeats = %d, want %d", open, tt.wantOpen)
			}
		})
	}
}
