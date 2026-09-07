package poller

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// ProcessingClient publishes articles to Processing's /pubsub/push endpoint
// directly over HTTP — the same real Pub/Sub push envelope shape Pub/Sub
// itself would send, so this is a drop-in stand-in until milestone 4 wires
// the real queue (mirrors services/processing/scripts/seed_static_articles.py's
// approach from milestone 1).
type ProcessingClient struct {
	baseURL    string
	httpClient *http.Client
}

func NewProcessingClient(baseURL string) *ProcessingClient {
	return &ProcessingClient{
		baseURL:    baseURL,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

type articlePayload struct {
	Source       string `json:"source"`
	Headline     string `json:"headline"`
	PublishedAt  string `json:"published_at"`
	Content      string `json:"content"`
	Symbol       string `json:"symbol"`
	CanonicalURL string `json:"canonical_url,omitempty"`
}

type pubsubMessage struct {
	Data        string `json:"data"`
	MessageID   string `json:"messageId"`
	PublishTime string `json:"publishTime"`
}

type pubsubPushEnvelope struct {
	Message      pubsubMessage `json:"message"`
	Subscription string        `json:"subscription"`
}

// Publish sends one article, tagged with the symbol it was discovered under,
// to Processing. A single publish failing must not crash the whole poll
// cycle (api-spec.md) — returns an error the caller catches per-article.
func (c *ProcessingClient) Publish(ctx context.Context, source, symbol string, item NewsItem) error {
	payload := articlePayload{
		Source:       source,
		Headline:     item.Headline,
		PublishedAt:  item.PublishedAt.Format(time.RFC3339),
		Content:      item.Summary,
		Symbol:       symbol,
		CanonicalURL: item.URL,
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshaling article payload: %w", err)
	}

	envelope := pubsubPushEnvelope{
		Message: pubsubMessage{
			Data:        base64.StdEncoding.EncodeToString(payloadJSON),
			MessageID:   fmt.Sprintf("%s-%s-%d", source, symbol, item.PublishedAt.Unix()),
			PublishTime: time.Now().UTC().Format(time.RFC3339),
		},
		Subscription: "projects/local/subscriptions/poller",
	}
	envelopeJSON, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("marshaling pubsub envelope: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/pubsub/push", bytes.NewReader(envelopeJSON))
	if err != nil {
		return fmt.Errorf("building processing request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("publishing to processing failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("processing returned status %d", resp.StatusCode)
	}
	return nil
}
