package main

import (
	"reflect"
	"testing"

	"seatwatch/amc"
)

func seat(name string, row, col int, available bool) amc.Seat {
	return amc.Seat{Name: name, Row: row, Column: col, Available: available, Type: "CanReserve", ShouldDisplay: true}
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
		{"overlapping runs", []string{"C4", "C3", "C2", "D2", "D1"}, 2, [][]string{{"C4", "C3"}, {"D2", "D1"}}, 5},
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
