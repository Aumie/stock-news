package poller

import (
	"context"
	"time"
)

// NewsSource abstracts Finnhub — polled per-symbol.
type NewsSource interface {
	CompanyNews(symbol string, from, to time.Time) ([]NewsItem, error)
}

// BatchNewsSource abstracts Marketaux — polled with a batch of symbols at
// once; a single response can contain articles for multiple symbols within
// (or beyond) the batch, distinguished via NewsItem.MatchedSymbols.
type BatchNewsSource interface {
	News(symbols []string) ([]NewsItem, error)
}

type Publisher interface {
	Publish(ctx context.Context, source, symbol string, item NewsItem) error
}

type Deps struct {
	Watchlist  WatchlistReader
	Finnhub    NewsSource
	Marketaux  BatchNewsSource // nil is valid: overflow symbols are then tracked but not polled
	Publisher  Publisher
	FinnhubCap int
}

type CycleResult struct {
	PolledSymbols     int
	OverflowSymbols   int
	PublishedArticles int
	Errors            []error
	HardFailure       error // set only on a failure before any polling started (api-spec.md)
}

// RunCycle is one poll cycle: re-read the distinct watched symbols, assign
// sources, poll Finnhub for the fast-lane symbols and Marketaux for overflow,
// publish results. If deps.Marketaux is nil, overflow symbols are counted but
// not polled (matches this project's state before the Marketaux live check
// was done — §4.2, docs/milestone.md §3).
func RunCycle(ctx context.Context, deps Deps) CycleResult {
	symbols, err := deps.Watchlist.DistinctWatchedSymbols(ctx)
	if err != nil {
		return CycleResult{HardFailure: err}
	}

	assignment := AssignSources(symbols, deps.FinnhubCap)

	result := CycleResult{OverflowSymbols: len(assignment.Marketaux)}

	now := time.Now().UTC()
	from := now.Add(-24 * time.Hour) // one day's lookback per cycle; §4.2 doesn't specify a window explicitly

	for _, symbol := range assignment.Finnhub {
		result.PolledSymbols++

		items, err := deps.Finnhub.CompanyNews(symbol, from, now)
		if err != nil {
			result.Errors = append(result.Errors, err)
			continue
		}

		for _, item := range items {
			if err := deps.Publisher.Publish(ctx, "finnhub", symbol, item); err != nil {
				result.Errors = append(result.Errors, err)
				continue
			}
			result.PublishedArticles++
		}
	}

	if deps.Marketaux != nil && len(assignment.Marketaux) > 0 {
		result.PolledSymbols += len(assignment.Marketaux)

		items, err := deps.Marketaux.News(assignment.Marketaux)
		if err != nil {
			result.Errors = append(result.Errors, err)
		} else {
			overflowSet := make(map[string]bool, len(assignment.Marketaux))
			for _, s := range assignment.Marketaux {
				overflowSet[s] = true
			}

			for _, item := range items {
				for _, matchedSymbol := range item.MatchedSymbols {
					// Only publish for symbols actually on the overflow
					// list — a Marketaux response can include entities for
					// symbols nobody is watching (confirmed live, see
					// marketaux.go), which would otherwise mean ingesting
					// news for untracked tickers.
					if !overflowSet[matchedSymbol] {
						continue
					}
					if err := deps.Publisher.Publish(ctx, "marketaux", matchedSymbol, item); err != nil {
						result.Errors = append(result.Errors, err)
						continue
					}
					result.PublishedArticles++
				}
			}
		}
	}

	return result
}
