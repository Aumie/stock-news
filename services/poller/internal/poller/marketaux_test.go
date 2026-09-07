package poller

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMarketauxClient_News_ParsesRealResponseShape(t *testing.T) {
	// Response shape confirmed against a real live call to
	// api.marketaux.com/v1/news/all (decision_log_claude.md, milestone 3) —
	// not fabricated from docs alone, unlike the Finnhub client. Real
	// responses can include entities for symbols NOT in the query (broad
	// relevance search, not a strict filter, unless filter_entities=true) —
	// confirmed live: querying AAPL,MSFT returned articles entity-tagged
	// GOOGL/NVDA. MatchedSymbols reflects the article's own entities, not
	// the query's symbol list.
	sample := `{
		"meta": {"found": 100, "returned": 1, "limit": 1, "page": 1},
		"data": [
			{
				"uuid": "1d069a3c-549f-4940-b9d4-c97d78c16d0b",
				"title": "Apple unveils new iPhone",
				"description": "Apple announced its latest iPhone today.",
				"url": "https://example.com/news/apple-iphone",
				"published_at": "2026-09-04T14:30:00.000000Z",
				"source": "example.com",
				"entities": [
					{"symbol": "AAPL", "name": "Apple Inc."},
					{"symbol": "MSFT", "name": "Microsoft Corporation"}
				]
			}
		]
	}`

	var gotRequest *http.Request
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotRequest = r
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(sample))
	}))
	defer server.Close()

	client := NewMarketauxClient(server.URL, "test-token")
	items, err := client.News([]string{"AAPL", "MSFT"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(items) != 1 {
		t.Fatalf("expected 1 news item, got %d", len(items))
	}
	if items[0].Headline != "Apple unveils new iPhone" {
		t.Errorf("unexpected headline: %s", items[0].Headline)
	}
	if items[0].Source != "example.com" {
		t.Errorf("unexpected source: %s", items[0].Source)
	}
	if items[0].URL != "https://example.com/news/apple-iphone" {
		t.Errorf("unexpected url: %s", items[0].URL)
	}
	if items[0].PublishedAt.Year() != 2026 {
		t.Errorf("unexpected published_at: %v", items[0].PublishedAt)
	}
	if len(items[0].MatchedSymbols) != 2 || items[0].MatchedSymbols[0] != "AAPL" || items[0].MatchedSymbols[1] != "MSFT" {
		t.Errorf("expected MatchedSymbols [AAPL MSFT] from the article's own entities, got %v", items[0].MatchedSymbols)
	}

	// Auth + symbol param shape confirmed live: api_token query param,
	// symbols as a flat comma-separated list.
	q := gotRequest.URL.Query()
	if q.Get("api_token") != "test-token" {
		t.Errorf("expected api_token=test-token, got %q", q.Get("api_token"))
	}
	if !strings.Contains(q.Get("symbols"), "AAPL") || !strings.Contains(q.Get("symbols"), "MSFT") {
		t.Errorf("expected symbols param to contain AAPL and MSFT, got %q", q.Get("symbols"))
	}
}

func TestMarketauxClient_News_BatchesLargeSymbolListsAtMarketauxSymbolsPerCall(t *testing.T) {
	var requestedBatches [][]string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		symbols := strings.Split(r.URL.Query().Get("symbols"), ",")
		requestedBatches = append(requestedBatches, symbols)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"meta":{"found":0,"returned":0,"limit":3,"page":1},"data":[]}`))
	}))
	defer server.Close()

	symbols := make([]string, 120)
	for i := range symbols {
		symbols[i] = "SYM"
	}

	client := NewMarketauxClient(server.URL, "test-token")
	_, err := client.News(symbols)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	wantBatches := CallsPerCycle(len(symbols)) // 3, at 50/call
	if len(requestedBatches) != wantBatches {
		t.Fatalf("expected %d batched requests for %d symbols at %d/call, got %d",
			wantBatches, len(symbols), MarketauxSymbolsPerCall, len(requestedBatches))
	}
	if len(requestedBatches[0]) != MarketauxSymbolsPerCall {
		t.Errorf("expected first batch to have %d symbols, got %d", MarketauxSymbolsPerCall, len(requestedBatches[0]))
	}
}

func TestMarketauxClient_News_PropagatesErrorsWithoutCrashing(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusPaymentRequired) // Marketaux's real "quota exceeded" status, confirmed live
		w.Write([]byte(`{"error": {"message": "usage limit reached"}}`))
	}))
	defer server.Close()

	client := NewMarketauxClient(server.URL, "test-token")
	_, err := client.News([]string{"AAPL"})
	if err == nil {
		t.Fatal("expected an error for a 402 response, got nil")
	}
}

func TestMarketauxClient_News_RejectsMalformedJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`not json`))
	}))
	defer server.Close()

	client := NewMarketauxClient(server.URL, "test-token")
	_, err := client.News([]string{"AAPL"})
	if err == nil {
		t.Fatal("expected an error for malformed JSON, got nil")
	}
}
