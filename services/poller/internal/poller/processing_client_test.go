package poller

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProcessingClient_Publish_SendsCorrectPubSubPushEnvelopeShape(t *testing.T) {
	var gotBody map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/pubsub/push" {
			t.Errorf("expected path /pubsub/push, got %s", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotBody)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status": "ok", "article_id": "test-id"}`))
	}))
	defer server.Close()

	client := NewProcessingClient(server.URL)
	item := NewsItem{
		Headline:    "Apple unveils new iPhone",
		Summary:     "Apple announced its latest iPhone today.",
		Source:      "finnhub",
		URL:         "https://example.com/news/apple-iphone",
		PublishedAt: time.Date(2026, 9, 4, 14, 30, 0, 0, time.UTC),
	}

	err := client.Publish(context.Background(), "finnhub", "AAPL", item)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	message, ok := gotBody["message"].(map[string]interface{})
	if !ok {
		t.Fatal("expected a 'message' field in the envelope")
	}
	if _, ok := gotBody["subscription"]; !ok {
		t.Fatal("expected a 'subscription' field in the envelope")
	}

	dataB64, ok := message["data"].(string)
	if !ok {
		t.Fatal("expected message.data to be a base64 string")
	}
	decoded, err := base64.StdEncoding.DecodeString(dataB64)
	if err != nil {
		t.Fatalf("message.data was not valid base64: %v", err)
	}

	var payload map[string]interface{}
	if err := json.Unmarshal(decoded, &payload); err != nil {
		t.Fatalf("decoded message.data was not valid JSON: %v", err)
	}

	// Must match services/processing/infrastructure/pubsub.py's ArticlePayload
	// field names exactly.
	for _, field := range []string{"source", "headline", "published_at", "content", "symbol"} {
		if _, ok := payload[field]; !ok {
			t.Errorf("expected field %q in article payload, got %v", field, payload)
		}
	}
	if payload["symbol"] != "AAPL" {
		t.Errorf("expected symbol AAPL, got %v", payload["symbol"])
	}
	if payload["canonical_url"] != "https://example.com/news/apple-iphone" {
		t.Errorf("expected canonical_url set, got %v", payload["canonical_url"])
	}
}

func TestProcessingClient_Publish_ReturnsErrorOnNon200(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewProcessingClient(server.URL)
	err := client.Publish(context.Background(), "finnhub", "AAPL", NewsItem{})
	if err == nil {
		t.Fatal("expected an error for a 500 response, got nil")
	}
}
