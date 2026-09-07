package poller

import (
	"testing"
	"time"
)

func t_(minute int) time.Time {
	return time.Date(2026, 9, 4, 12, minute, 0, 0, time.UTC)
}

func TestAssignSources_UnderCapAllGoToFinnhub(t *testing.T) {
	symbols := []WatchedSymbol{
		{Symbol: "AAPL", WatcherCount: 5, AddedAt: t_(0)},
		{Symbol: "MSFT", WatcherCount: 3, AddedAt: t_(1)},
	}

	assignment := AssignSources(symbols, 45)

	if len(assignment.Finnhub) != 2 {
		t.Fatalf("expected 2 symbols on Finnhub, got %d", len(assignment.Finnhub))
	}
	if len(assignment.Marketaux) != 0 {
		t.Fatalf("expected 0 symbols on Marketaux, got %d", len(assignment.Marketaux))
	}
}

func TestAssignSources_RanksByWatcherCountDescending(t *testing.T) {
	symbols := []WatchedSymbol{
		{Symbol: "LOW", WatcherCount: 1, AddedAt: t_(0)},
		{Symbol: "HIGH", WatcherCount: 10, AddedAt: t_(1)},
		{Symbol: "MID", WatcherCount: 5, AddedAt: t_(2)},
	}

	assignment := AssignSources(symbols, 2)

	if len(assignment.Finnhub) != 2 {
		t.Fatalf("expected 2 symbols on Finnhub (cap), got %d", len(assignment.Finnhub))
	}
	if assignment.Finnhub[0] != "HIGH" || assignment.Finnhub[1] != "MID" {
		t.Fatalf("expected [HIGH, MID] on Finnhub in that order, got %v", assignment.Finnhub)
	}
	if len(assignment.Marketaux) != 1 || assignment.Marketaux[0] != "LOW" {
		t.Fatalf("expected [LOW] on Marketaux, got %v", assignment.Marketaux)
	}
}

func TestAssignSources_TiesBrokenByEarliestAddedAt(t *testing.T) {
	symbols := []WatchedSymbol{
		{Symbol: "NEWER", WatcherCount: 5, AddedAt: t_(10)},
		{Symbol: "OLDER", WatcherCount: 5, AddedAt: t_(1)},
	}

	assignment := AssignSources(symbols, 1)

	if len(assignment.Finnhub) != 1 || assignment.Finnhub[0] != "OLDER" {
		t.Fatalf("expected [OLDER] to win the tie (earliest added_at), got %v", assignment.Finnhub)
	}
	if len(assignment.Marketaux) != 1 || assignment.Marketaux[0] != "NEWER" {
		t.Fatalf("expected [NEWER] on Marketaux, got %v", assignment.Marketaux)
	}
}

func TestAssignSources_DeterministicAcrossRepeatedCalls(t *testing.T) {
	// Same input must always produce the same assignment — no arbitrary
	// ordering from map iteration or unstable sort (§4.2: "explicit/
	// deterministic rather than arbitrary at runtime").
	symbols := []WatchedSymbol{
		{Symbol: "A", WatcherCount: 3, AddedAt: t_(5)},
		{Symbol: "B", WatcherCount: 3, AddedAt: t_(2)},
		{Symbol: "C", WatcherCount: 7, AddedAt: t_(1)},
		{Symbol: "D", WatcherCount: 1, AddedAt: t_(0)},
	}

	first := AssignSources(symbols, 2)
	for i := 0; i < 10; i++ {
		again := AssignSources(symbols, 2)
		if !equalAssignment(first, again) {
			t.Fatalf("AssignSources is not deterministic: got %v then %v", first, again)
		}
	}
}

func TestAssignSources_EmptyWatchlist(t *testing.T) {
	assignment := AssignSources(nil, 45)
	if len(assignment.Finnhub) != 0 || len(assignment.Marketaux) != 0 {
		t.Fatalf("expected empty assignment for empty watchlist, got %v", assignment)
	}
}

func equalAssignment(a, b SourceAssignment) bool {
	if len(a.Finnhub) != len(b.Finnhub) || len(a.Marketaux) != len(b.Marketaux) {
		return false
	}
	for i := range a.Finnhub {
		if a.Finnhub[i] != b.Finnhub[i] {
			return false
		}
	}
	for i := range a.Marketaux {
		if a.Marketaux[i] != b.Marketaux[i] {
			return false
		}
	}
	return true
}
