package poller

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestFinnhubClient_CompanyNews_ParsesRealResponseShape(t *testing.T) {
	// Response shape per Finnhub's documented Company News API (verified via
	// docs.finnhub.io/docs/api/company-news, not a live call — no API key
	// available yet, see decision_log_claude.md).
	sample := `[
		{
			"category": "company",
			"datetime": 1725456000,
			"headline": "Apple unveils new iPhone",
			"id": 12345,
			"image": "https://example.com/image.jpg",
			"related": "AAPL",
			"source": "Reuters",
			"summary": "Apple announced its latest iPhone today.",
			"url": "https://example.com/news/apple-iphone"
		}
	]`

	var gotRequest *http.Request
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotRequest = r
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(sample))
	}))
	defer server.Close()

	client := NewFinnhubClient(server.URL, "test-token")
	items, err := client.CompanyNews("AAPL", time.Date(2026, 9, 1, 0, 0, 0, 0, time.UTC), time.Date(2026, 9, 4, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(items) != 1 {
		t.Fatalf("expected 1 news item, got %d", len(items))
	}
	item := items[0]
	if item.Headline != "Apple unveils new iPhone" {
		t.Errorf("unexpected headline: %s", item.Headline)
	}
	if item.Source != "Reuters" {
		t.Errorf("unexpected source: %s", item.Source)
	}
	if item.URL != "https://example.com/news/apple-iphone" {
		t.Errorf("unexpected url: %s", item.URL)
	}
	wantTime := time.Unix(1725456000, 0).UTC()
	if !item.PublishedAt.Equal(wantTime) {
		t.Errorf("expected published_at %v, got %v", wantTime, item.PublishedAt)
	}

	// Auth: token attached as X-Finnhub-Token header (per docs, either header
	// or query param works — using the header keeps the token out of logs
	// that might capture request URLs).
	if got := gotRequest.Header.Get("X-Finnhub-Token"); got != "test-token" {
		t.Errorf("expected X-Finnhub-Token header 'test-token', got %q", got)
	}

	q := gotRequest.URL.Query()
	if q.Get("symbol") != "AAPL" {
		t.Errorf("expected symbol=AAPL, got %q", q.Get("symbol"))
	}
	if q.Get("from") != "2026-09-01" {
		t.Errorf("expected from=2026-09-01, got %q", q.Get("from"))
	}
	if q.Get("to") != "2026-09-04" {
		t.Errorf("expected to=2026-09-04, got %q", q.Get("to"))
	}
}

func TestFinnhubClient_CompanyNews_EmptyArrayIsNotAnError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`[]`))
	}))
	defer server.Close()

	client := NewFinnhubClient(server.URL, "test-token")
	items, err := client.CompanyNews("AAPL", time.Now(), time.Now())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("expected 0 items, got %d", len(items))
	}
}

func TestFinnhubClient_CompanyNews_PropagatesHTTPErrorsWithoutCrashing(t *testing.T) {
	// A single symbol's fetch failing must not crash the whole poll cycle
	// (api-spec.md: "success or partial success — a single symbol's fetch
	// failing doesn't fail the whole cycle") — the client returns an error
	// the caller can catch per-symbol, rather than panicking.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte(`{"error": "rate limit exceeded"}`))
	}))
	defer server.Close()

	client := NewFinnhubClient(server.URL, "test-token")
	_, err := client.CompanyNews("AAPL", time.Now(), time.Now())
	if err == nil {
		t.Fatal("expected an error for a 429 response, got nil")
	}
}

func TestFinnhubClient_CompanyNews_RejectsMalformedJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`not json`))
	}))
	defer server.Close()

	client := NewFinnhubClient(server.URL, "test-token")
	_, err := client.CompanyNews("AAPL", time.Now(), time.Now())
	if err == nil {
		t.Fatal("expected an error for malformed JSON, got nil")
	}
}

// Sanity check that the test fixture's sample JSON round-trips through
// encoding/json the way our struct expects, independent of the HTTP client.
func TestCompanyNewsItem_JSONShapeMatchesFinnhubDocs(t *testing.T) {
	raw := `{"category":"company","datetime":1725456000,"headline":"h","id":1,"image":"i","related":"AAPL","source":"s","summary":"sum","url":"u"}`
	var item companyNewsItem
	if err := json.Unmarshal([]byte(raw), &item); err != nil {
		t.Fatalf("unexpected unmarshal error: %v", err)
	}
	if item.Datetime != 1725456000 {
		t.Errorf("expected datetime 1725456000, got %d", item.Datetime)
	}
}
