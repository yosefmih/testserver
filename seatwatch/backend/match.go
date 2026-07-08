package main

import (
	"sort"

	"seatwatch/amc"
)

// The best seats in a house are dead center, roughly two-thirds back — the
// THX/SMPTE calibration point that sound mixes are tuned for — shifted a bit
// further back for giant IMAX screens. Groups are scored against that ideal:
// horizontal centering within their own row (weighted heavier) plus row depth,
// so the first groups returned are the most attractive seats.
const (
	idealRowFraction = 0.72
	horizontalWeight = 0.55
	verticalWeight   = 0.45
	accessiblePenalty = 0.15
)

// FindAdjacentSeatGroups returns every run of partySize seats that is
// currently available, adjacent in the same row (consecutive grid columns),
// and entirely within the tolerable set — best seats first — plus how many
// tolerable seats are available at all.
func FindAdjacentSeatGroups(layout amc.SeatingLayout, tolerable []string, partySize int) (groups [][]string, openSeats int) {
	tolerableSet := map[string]bool{}
	for _, name := range tolerable {
		tolerableSet[name] = true
	}

	rows := map[int][]amc.Seat{}
	maxRow := 0
	for _, seat := range layout.Seats {
		if seat.ShouldDisplay && seat.Name != "" {
			rows[seat.Row] = append(rows[seat.Row], seat)
			if seat.Row > maxRow {
				maxRow = seat.Row
			}
			if seat.Available && tolerableSet[seat.Name] {
				openSeats++
			}
		}
	}

	type scoredGroup struct {
		names []string
		score float64
	}
	var scored []scoredGroup

	rowNums := make([]int, 0, len(rows))
	for r := range rows {
		rowNums = append(rowNums, r)
	}
	sort.Ints(rowNums)

	for _, r := range rowNums {
		seats := rows[r]
		sort.Slice(seats, func(i, j int) bool { return seats[i].Column < seats[j].Column })
		rowMin := seats[0].Column
		rowMax := seats[len(seats)-1].Column

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
				group := run[len(run)-partySize:]
				names := make([]string, partySize)
				for i, s := range group {
					names[i] = s.Name
				}
				scored = append(scored, scoredGroup{names, scoreGroup(group, rowMin, rowMax, maxRow)})
			}
		}
	}

	if len(scored) == 0 {
		return nil, openSeats
	}
	sort.SliceStable(scored, func(i, j int) bool { return scored[i].score > scored[j].score })
	groups = make([][]string, len(scored))
	for i, g := range scored {
		groups[i] = g.names
	}
	return groups, openSeats
}

func scoreGroup(group []amc.Seat, rowMin, rowMax, maxRow int) float64 {
	groupCenter := float64(group[0].Column+group[len(group)-1].Column) / 2
	rowCenter := float64(rowMin+rowMax) / 2
	halfWidth := float64(rowMax-rowMin) / 2
	if halfWidth < 1 {
		halfWidth = 1
	}
	horizontal := 1 - abs(groupCenter-rowCenter)/halfWidth

	rowFraction := float64(group[0].Row) / float64(maxRow)
	vertical := 1 - abs(rowFraction-idealRowFraction)/idealRowFraction
	if vertical < 0 {
		vertical = 0
	}

	score := horizontalWeight*horizontal + verticalWeight*vertical
	for _, s := range group {
		if s.Type == "Wheelchair" || s.Type == "Companion" {
			score -= accessiblePenalty
			break
		}
	}
	return score
}

func abs(v float64) float64 {
	if v < 0 {
		return -v
	}
	return v
}
