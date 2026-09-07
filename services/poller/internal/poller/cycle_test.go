package poller

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeWatchlistReader struct {
	symbols []WatchedSymbol
	err     error
}

func (f *fakeWatchlistReader) DistinctWatchedSymbols(ctx context.Context) ([]WatchedSymbol, error) {
	return f.symbols, f.err
}

type fakeNewsSource struct {
	itemsBySymbol map[string][]NewsItem
	errBySymbol   map[string]error
	calledSymbols []string
}

func (f *fakeNewsSource) CompanyNews(symbol string, from, to time.Time) ([]NewsItem, error) {
	f.calledSymbols = append(f.calledSymbols, symbol)
	if err, ok := f.errBySymbol[symbol]; ok {
		return nil, err
	}
	return f.itemsBySymbol[symbol], nil
}

type fakeBatchNewsSource struct {
	items       []NewsItem
	err         error
	lastSymbols []string
}

func (f *fakeBatchNewsSource) News(symbols []string) ([]NewsItem, error) {
	f.lastSymbols = symbols
	if f.err != nil {
		return nil, f.err
	}
	return f.items, nil
}

type fakePublisher struct {
	published []struct {
		source, symbol string
		item           NewsItem
	}
	failFor map[string]bool
}

func (f *fakePublisher) Publish(ctx context.Context, source, symbol string, item NewsItem) error {
	if f.failFor[symbol] {
		return errors.New("simulated publish failure")
	}
	f.published = append(f.published, struct {
		source, symbol string
		item           NewsItem
	}{source, symbol, item})
	return nil
}

func TestRunCycle_PollsEachFinnhubSymbolAndPublishesResults(t *testing.T) {
	reader := &fakeWatchlistReader{symbols: []WatchedSymbol{
		{Symbol: "AAPL", WatcherCount: 5, AddedAt: t_(0)},
		{Symbol: "MSFT", WatcherCount: 3, AddedAt: t_(1)},
	}}
	finnhub := &fakeNewsSource{itemsBySymbol: map[string][]NewsItem{
		"AAPL": {{Headline: "Apple news"}},
		"MSFT": {{Headline: "Microsoft news"}},
	}}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Publisher:  publisher,
		FinnhubCap: 45,
	})

	if result.PolledSymbols != 2 {
		t.Errorf("expected 2 polled symbols, got %d", result.PolledSymbols)
	}
	if result.PublishedArticles != 2 {
		t.Errorf("expected 2 published articles, got %d", result.PublishedArticles)
	}
	if len(result.Errors) != 0 {
		t.Errorf("expected no errors, got %v", result.Errors)
	}
}

func TestRunCycle_OneSymbolFailingDoesNotFailTheWholeCycle(t *testing.T) {
	// api-spec.md: "success or partial success — a single symbol's fetch
	// failing doesn't fail the whole cycle".
	reader := &fakeWatchlistReader{symbols: []WatchedSymbol{
		{Symbol: "AAPL", WatcherCount: 5, AddedAt: t_(0)},
		{Symbol: "BADSYM", WatcherCount: 3, AddedAt: t_(1)},
	}}
	finnhub := &fakeNewsSource{
		itemsBySymbol: map[string][]NewsItem{"AAPL": {{Headline: "Apple news"}}},
		errBySymbol:   map[string]error{"BADSYM": errors.New("finnhub 500")},
	}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Publisher:  publisher,
		FinnhubCap: 45,
	})

	if result.PolledSymbols != 2 {
		t.Errorf("expected 2 polled symbols (both attempted), got %d", result.PolledSymbols)
	}
	if result.PublishedArticles != 1 {
		t.Errorf("expected 1 published article (AAPL succeeded), got %d", result.PublishedArticles)
	}
	if len(result.Errors) != 1 {
		t.Errorf("expected 1 error recorded (BADSYM), got %v", result.Errors)
	}
}

func TestRunCycle_OverflowSymbolsAreCountedButNotPolledWhenMarketauxIsNil(t *testing.T) {
	// deps.Marketaux == nil is the state before the Marketaux live check was
	// done, or a deliberate configuration choice — overflow symbols are
	// tracked honestly as unpolled, not silently dropped or crashed on.
	symbols := make([]WatchedSymbol, 0, 50)
	for i := 0; i < 50; i++ {
		symbols = append(symbols, WatchedSymbol{Symbol: "SYM", WatcherCount: 50 - i, AddedAt: t_(i)})
	}
	reader := &fakeWatchlistReader{symbols: symbols}
	finnhub := &fakeNewsSource{itemsBySymbol: map[string][]NewsItem{}}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Publisher:  publisher,
		FinnhubCap: 45,
	})

	if result.PolledSymbols != 45 {
		t.Errorf("expected 45 symbols polled (Finnhub cap), got %d", result.PolledSymbols)
	}
	if result.OverflowSymbols != 5 {
		t.Errorf("expected 5 overflow symbols tracked, got %d", result.OverflowSymbols)
	}
}

func TestRunCycle_WatchlistReadFailureIsAHardFailure(t *testing.T) {
	// api-spec.md: "5xx only on a hard failure before any polling started".
	reader := &fakeWatchlistReader{err: errors.New("db connection refused")}
	finnhub := &fakeNewsSource{}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Publisher:  publisher,
		FinnhubCap: 45,
	})

	if result.HardFailure == nil {
		t.Fatal("expected a hard failure when the watchlist read fails")
	}
	if len(finnhub.calledSymbols) != 0 {
		t.Errorf("expected no polling attempted after a watchlist read failure, got %v", finnhub.calledSymbols)
	}
}

func TestRunCycle_PublishFailureIsRecordedNotFatal(t *testing.T) {
	reader := &fakeWatchlistReader{symbols: []WatchedSymbol{
		{Symbol: "AAPL", WatcherCount: 5, AddedAt: t_(0)},
	}}
	finnhub := &fakeNewsSource{itemsBySymbol: map[string][]NewsItem{
		"AAPL": {{Headline: "Apple news"}},
	}}
	publisher := &fakePublisher{failFor: map[string]bool{"AAPL": true}}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Publisher:  publisher,
		FinnhubCap: 45,
	})

	if result.HardFailure != nil {
		t.Errorf("a publish failure should not be a hard failure, got %v", result.HardFailure)
	}
	if len(result.Errors) != 1 {
		t.Errorf("expected 1 error recorded for the failed publish, got %v", result.Errors)
	}
}

func TestRunCycle_PollsOverflowSymbolsViaMarketauxWhenWired(t *testing.T) {
	symbols := []WatchedSymbol{
		{Symbol: "AAPL", WatcherCount: 5, AddedAt: t_(0)},
		{Symbol: "OVERFLOW1", WatcherCount: 1, AddedAt: t_(1)},
		{Symbol: "OVERFLOW2", WatcherCount: 1, AddedAt: t_(2)},
	}
	reader := &fakeWatchlistReader{symbols: symbols}
	finnhub := &fakeNewsSource{itemsBySymbol: map[string][]NewsItem{"AAPL": {{Headline: "Apple news"}}}}
	marketaux := &fakeBatchNewsSource{items: []NewsItem{
		{Headline: "Overflow news 1", MatchedSymbols: []string{"OVERFLOW1"}},
		{Headline: "Overflow news 2", MatchedSymbols: []string{"OVERFLOW2"}},
	}}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Marketaux:  marketaux,
		Publisher:  publisher,
		FinnhubCap: 1,
	})

	if len(marketaux.lastSymbols) != 2 {
		t.Fatalf("expected Marketaux queried with 2 overflow symbols, got %v", marketaux.lastSymbols)
	}
	if result.PublishedArticles != 3 { // 1 from Finnhub + 2 from Marketaux
		t.Errorf("expected 3 published articles, got %d", result.PublishedArticles)
	}
	if len(result.Errors) != 0 {
		t.Errorf("expected no errors, got %v", result.Errors)
	}
}

func TestRunCycle_MarketauxArticleForUnwatchedSymbolIsNotPublished(t *testing.T) {
	// Confirmed live: a Marketaux response can include entities for symbols
	// nobody queried (marketaux.go) — must not publish news for an untracked
	// ticker just because it happened to be mentioned in a returned article.
	symbols := []WatchedSymbol{
		{Symbol: "OVERFLOW1", WatcherCount: 1, AddedAt: t_(0)},
	}
	reader := &fakeWatchlistReader{symbols: symbols}
	finnhub := &fakeNewsSource{}
	marketaux := &fakeBatchNewsSource{items: []NewsItem{
		{Headline: "Mentions an unwatched ticker", MatchedSymbols: []string{"NOT_WATCHED"}},
	}}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Marketaux:  marketaux,
		Publisher:  publisher,
		FinnhubCap: 0,
	})

	if result.PublishedArticles != 0 {
		t.Errorf("expected 0 published articles (NOT_WATCHED isn't on the overflow list), got %d", result.PublishedArticles)
	}
}

func TestRunCycle_MarketauxFailureIsRecordedNotFatal(t *testing.T) {
	symbols := []WatchedSymbol{{Symbol: "OVERFLOW1", WatcherCount: 1, AddedAt: t_(0)}}
	reader := &fakeWatchlistReader{symbols: symbols}
	finnhub := &fakeNewsSource{}
	marketaux := &fakeBatchNewsSource{err: errors.New("marketaux 402")}
	publisher := &fakePublisher{}

	result := RunCycle(context.Background(), Deps{
		Watchlist:  reader,
		Finnhub:    finnhub,
		Marketaux:  marketaux,
		Publisher:  publisher,
		FinnhubCap: 0,
	})

	if result.HardFailure != nil {
		t.Errorf("a Marketaux failure should not be a hard failure, got %v", result.HardFailure)
	}
	if len(result.Errors) != 1 {
		t.Errorf("expected 1 error recorded for the Marketaux failure, got %v", result.Errors)
	}
}
