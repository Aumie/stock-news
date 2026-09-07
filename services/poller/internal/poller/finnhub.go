package poller

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// NewsItem is the domain shape the rest of the poller works with, decoupled
// from either source's specific field names.
type NewsItem struct {
	Headline    string
	Summary     string
	Source      string
	URL         string
	PublishedAt time.Time
	// MatchedSymbols: which symbols this specific article was actually
	// tagged under by the source. Empty for Finnhub (queried per-symbol, so
	// the caller already knows). Populated for Marketaux, since one batched
	// query can return articles relevant to symbols beyond the ones queried
	// (confirmed live — see marketaux.go) and the article itself carries the
	// real answer via its "entities".
	MatchedSymbols []string
}

// companyNewsItem mirrors Finnhub's documented Company News response shape
// exactly (docs.finnhub.io/docs/api/company-news — verified against the
// docs page's Response Attributes section, not a live call: no Finnhub API
// key available yet, see decision_log_claude.md). datetime is Unix seconds,
// per the docs' explicit wording ("Published time in UNIX timestamp").
type companyNewsItem struct {
	Category string `json:"category"`
	Datetime int64  `json:"datetime"`
	Headline string `json:"headline"`
	ID       int64  `json:"id"`
	Image    string `json:"image"`
	Related  string `json:"related"`
	Source   string `json:"source"`
	Summary  string `json:"summary"`
	URL      string `json:"url"`
}

type FinnhubClient struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

func NewFinnhubClient(baseURL, token string) *FinnhubClient {
	return &FinnhubClient{
		baseURL:    baseURL,
		token:      token,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// CompanyNews fetches news for one symbol in the given date range. A single
// symbol's fetch failing must not crash the whole poll cycle (api-spec.md) —
// this returns an error the caller catches per-symbol, never panics.
func (c *FinnhubClient) CompanyNews(symbol string, from, to time.Time) ([]NewsItem, error) {
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, c.baseURL+"/company-news", nil)
	if err != nil {
		return nil, fmt.Errorf("building finnhub request: %w", err)
	}

	q := req.URL.Query()
	q.Set("symbol", symbol)
	q.Set("from", from.Format("2006-01-02"))
	q.Set("to", to.Format("2006-01-02"))
	req.URL.RawQuery = q.Encode()

	// Header over query-param token (docs: either works) — keeps the token
	// out of logs that might capture request URLs.
	req.Header.Set("X-Finnhub-Token", c.token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("finnhub request for %s failed: %w", symbol, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("finnhub returned status %d for %s", resp.StatusCode, symbol)
	}

	var raw []companyNewsItem
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, fmt.Errorf("decoding finnhub response for %s: %w", symbol, err)
	}

	items := make([]NewsItem, len(raw))
	for i, r := range raw {
		items[i] = NewsItem{
			Headline:    r.Headline,
			Summary:     r.Summary,
			Source:      r.Source,
			URL:         r.URL,
			PublishedAt: time.Unix(r.Datetime, 0).UTC(),
		}
	}
	return items, nil
}
