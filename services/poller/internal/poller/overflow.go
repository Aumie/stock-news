package poller

import (
	"sort"
	"time"
)

// WatchedSymbol is one distinct symbol from `SELECT DISTINCT symbol FROM
// watchlist` plus the aggregate info the overflow-assignment rule needs.
type WatchedSymbol struct {
	Symbol       string
	WatcherCount int
	AddedAt      time.Time // earliest added_at across all watchers of this symbol
}

// SourceAssignment is the deterministic split decided once per poll cycle.
type SourceAssignment struct {
	Finnhub   []string
	Marketaux []string
}

// AssignSources ranks symbols by distinct watcher count (most-watched first),
// tie-broken by earliest AddedAt, and assigns the top `finnhubCap` to
// Finnhub's fast lane — the rest overflow to Marketaux (§4.2). Deterministic:
// the same input always produces the same assignment, never dependent on map
// iteration order or an unstable sort.
func AssignSources(symbols []WatchedSymbol, finnhubCap int) SourceAssignment {
	ranked := make([]WatchedSymbol, len(symbols))
	copy(ranked, symbols)

	sort.SliceStable(ranked, func(i, j int) bool {
		if ranked[i].WatcherCount != ranked[j].WatcherCount {
			return ranked[i].WatcherCount > ranked[j].WatcherCount
		}
		return ranked[i].AddedAt.Before(ranked[j].AddedAt)
	})

	assignment := SourceAssignment{Finnhub: []string{}, Marketaux: []string{}}
	for i, s := range ranked {
		if i < finnhubCap {
			assignment.Finnhub = append(assignment.Finnhub, s.Symbol)
		} else {
			assignment.Marketaux = append(assignment.Marketaux, s.Symbol)
		}
	}
	return assignment
}
