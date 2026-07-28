package main

import (
	"sync"
	"time"

	"seatwatch/amc"
)

// Cache is the in-memory snapshot of AMC state that the Refresher maintains
// and HTTP handlers read.
type Cache struct {
	mu           sync.RWMutex
	showtimes    []amc.Showtime
	showtimesAt  time.Time
	layouts      map[int64]amc.SeatingLayout
	layoutsAt    map[int64]time.Time
}

func NewCache() *Cache {
	return &Cache{
		layouts:   map[int64]amc.SeatingLayout{},
		layoutsAt: map[int64]time.Time{},
	}
}

func (c *Cache) Showtimes() []amc.Showtime {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.showtimes
}

func (c *Cache) ShowtimesRefreshedAt() time.Time {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.showtimesAt
}

func (c *Cache) SetShowtimes(showtimes []amc.Showtime) {
	c.RestoreShowtimes(showtimes, time.Now())
}

func (c *Cache) RestoreShowtimes(showtimes []amc.Showtime, refreshedAt time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.showtimes = showtimes
	c.showtimesAt = refreshedAt
}

func (c *Cache) Layout(showtimeID int64) (amc.SeatingLayout, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	layout, ok := c.layouts[showtimeID]
	return layout, ok
}

func (c *Cache) SetLayout(showtimeID int64, layout amc.SeatingLayout) {
	c.RestoreLayout(showtimeID, layout, time.Now())
}

func (c *Cache) RestoreLayout(showtimeID int64, layout amc.SeatingLayout, fetchedAt time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.layouts[showtimeID] = layout
	c.layoutsAt[showtimeID] = fetchedAt
}

func (c *Cache) LayoutCount() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.layouts)
}

func (c *Cache) LayoutFetchedAt(showtimeID int64) (time.Time, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	at, ok := c.layoutsAt[showtimeID]
	return at, ok
}

// ForceSeatAvailable overrides a single seat's availability in the cached
// layout for a showtime, in memory only (never persisted). It exists so the
// alert path can be exercised end-to-end against a real watch without
// waiting for AMC to actually free up a seat. Returns false if the showtime
// or seat isn't cached.
func (c *Cache) ForceSeatAvailable(showtimeID int64, seatName string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	layout, ok := c.layouts[showtimeID]
	if !ok {
		return false
	}
	for i, seat := range layout.Seats {
		if seat.Name == seatName {
			layout.Seats[i].Available = true
			return true
		}
	}
	return false
}

// Prune drops layouts for showtimes that are no longer upcoming.
func (c *Cache) Prune(keep map[int64]bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for id := range c.layouts {
		if !keep[id] {
			delete(c.layouts, id)
			delete(c.layoutsAt, id)
		}
	}
}
