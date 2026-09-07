// Real end-to-end check for milestone 3: verifies ProcessingClient's
// pub/sub-push envelope is genuinely accepted by the real, running
// Processing service (not just a fake matching our own assumptions).
// Requires `docker compose up postgres processing`.
package integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	"stock-news/poller/internal/poller"
)

func TestProcessingClient_Publish_AcceptedByRealProcessingService(t *testing.T) {
	baseURL := "http://localhost:8001"

	healthResp, err := http.Get(baseURL + "/health")
	if err != nil || healthResp.StatusCode != http.StatusOK {
		t.Skipf("processing service not reachable at %s: %v", baseURL, err)
	}
	healthResp.Body.Close()

	client := poller.NewProcessingClient(baseURL)
	item := poller.NewsItem{
		Headline:    "Poller e2e test: real-time news headline",
		Summary:     "This article was published by the poller's ProcessingClient integration test.",
		Source:      "finnhub",
		URL:         "https://example.com/poller-e2e-test-" + time.Now().Format("150405.000000"),
		PublishedAt: time.Now().UTC(),
	}

	err = client.Publish(context.Background(), "finnhub", "AAPL", item)
	if err != nil {
		t.Fatalf("Publish failed against the real processing service: %v", err)
	}
}
