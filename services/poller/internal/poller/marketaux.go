package poller

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// marketauxTimeLayout matches the real format confirmed via a live call
// (decision_log_claude.md, milestone 3): "2026-09-20T06:00:55.000000Z" —
// microsecond precision, not Go's standard RFC3339 (which expects 3-digit ms).
const marketauxTimeLayout = "2006-01-02T15:04:05.000000Z"

// marketauxNewsItem mirrors Marketaux's real response shape, confirmed via a
// live call to api.marketaux.com/v1/news/all with a real API key — not
// built from docs alone (Marketaux's docs page blocks automated fetching,
// and don't render a sample response body).
type marketauxResponse struct {
	Data []marketauxNewsItem `json:"data"`
}

type marketauxNewsItem struct {
	Title       string            `json:"title"`
	Description string            `json:"description"`
	URL         string            `json:"url"`
	PublishedAt string            `json:"published_at"`
	Source      string            `json:"source"`
	Entities    []marketauxEntity `json:"entities"`
}

type marketauxEntity struct {
	Symbol string `json:"symbol"`
}

type MarketauxClient struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

func NewMarketauxClient(baseURL, token string) *MarketauxClient {
	return &MarketauxClient{
		baseURL:    baseURL,
		token:      token,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// News fetches news for the given symbols, batched at MarketauxSymbolsPerCall
// per request (§4.2; batch size raised from the spec's original 20 to 50
// after a live check found no hard limit at 98 symbols/request — see
// cadence.go and decision_log_claude.md). A single batch failing must not
// crash the whole poll cycle (api-spec.md) — returns an error the caller
// catches, never panics.
func (c *MarketauxClient) News(symbols []string) ([]NewsItem, error) {
	var allItems []NewsItem

	for start := 0; start < len(symbols); start += MarketauxSymbolsPerCall {
		end := start + MarketauxSymbolsPerCall
		if end > len(symbols) {
			end = len(symbols)
		}
		batch := symbols[start:end]

		items, err := c.newsForBatch(batch)
		if err != nil {
			return allItems, fmt.Errorf("marketaux batch %v failed: %w", batch, err)
		}
		allItems = append(allItems, items...)
	}

	return allItems, nil
}

func (c *MarketauxClient) newsForBatch(symbols []string) ([]NewsItem, error) {
	req, err := http.NewRequest(http.MethodGet, c.baseURL+"/v1/news/all", nil)
	if err != nil {
		return nil, fmt.Errorf("building marketaux request: %w", err)
	}

	q := req.URL.Query()
	q.Set("symbols", strings.Join(symbols, ","))
	q.Set("api_token", c.token)
	req.URL.RawQuery = q.Encode()

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("marketaux request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("marketaux returned status %d", resp.StatusCode)
	}

	var parsed marketauxResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decoding marketaux response: %w", err)
	}

	items := make([]NewsItem, 0, len(parsed.Data))
	for _, d := range parsed.Data {
		publishedAt, err := time.Parse(marketauxTimeLayout, d.PublishedAt)
		if err != nil {
			continue // skip items with an unparseable timestamp rather than failing the whole batch
		}
		matched := make([]string, 0, len(d.Entities))
		for _, e := range d.Entities {
			matched = append(matched, e.Symbol)
		}
		items = append(items, NewsItem{
			Headline:       d.Title,
			Summary:        d.Description,
			Source:         d.Source,
			URL:            d.URL,
			PublishedAt:    publishedAt,
			MatchedSymbols: matched,
		})
	}
	return items, nil
}
