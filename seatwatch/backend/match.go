package main

import (
	"sort"

	"seatwatch/amc"
)

// FindAdjacentSeatGroups returns every run of partySize seats that is
// currently available, adjacent in the same row (consecutive grid columns),
// and entirely within the tolerable set, plus how many tolerable seats are
// available at all.
func FindAdjacentSeatGroups(layout amc.SeatingLayout, tolerable []string, partySize int) (groups [][]string, openSeats int) {
	tolerableSet := map[string]bool{}
	for _, name := range tolerable {
		tolerableSet[name] = true
	}

	rows := map[int][]amc.Seat{}
	for _, seat := range layout.Seats {
		if seat.ShouldDisplay && seat.Name != "" {
			rows[seat.Row] = append(rows[seat.Row], seat)
			if seat.Available && tolerableSet[seat.Name] {
				openSeats++
			}
		}
	}

	rowNums := make([]int, 0, len(rows))
	for r := range rows {
		rowNums = append(rowNums, r)
	}
	sort.Ints(rowNums)

	for _, r := range rowNums {
		seats := rows[r]
		sort.Slice(seats, func(i, j int) bool { return seats[i].Column < seats[j].Column })
		var run []amc.Seat
		for _, seat := range seats {
			usable := seat.Available && tolerableSet[seat.Name]
			contiguous := len(run) > 0 && seat.Column == run[len(run)-1].Column+1
			if !usable {
				run = nil
				continue
			}
			if !contiguous {
				run = nil
			}
			run = append(run, seat)
			if len(run) >= partySize {
				group := make([]string, partySize)
				for i, s := range run[len(run)-partySize:] {
					group[i] = s.Name
				}
				groups = append(groups, group)
			}
		}
	}
	return groups, openSeats
}
