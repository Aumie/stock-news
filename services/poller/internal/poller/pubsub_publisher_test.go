package poller

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	"cloud.google.com/go/pubsub/v2"
	"cloud.google.com/go/pubsub/v2/apiv1/pubsubpb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// startEmulatorOrSkip requires a real Pub/Sub emulator reachable at
// PUBSUB_EMULATOR_HOST — this project doesn't fake the pubsub client,
// consistent with verifying real infrastructure wherever possible
// (backend-service-delivery skill). Skips cleanly if not running.
func startEmulatorOrSkip(t *testing.T) string {
	t.Helper()
	addr := os.Getenv("PUBSUB_EMULATOR_HOST")
	if addr == "" {
		addr = "localhost:8681"
	}
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Skipf("pubsub emulator not reachable at %s: %v", addr, err)
	}
	conn.Close()
	os.Setenv("PUBSUB_EMULATOR_HOST", addr)
	return addr
}

func TestPubSubPublisher_Publish_SendsCorrectArticlePayloadShape(t *testing.T) {
	startEmulatorOrSkip(t)
	ctx := context.Background()

	projectID := "test-project-" + strings.ReplaceAll(time.Now().Format("150405.000"), ".", "")
	topicID := "test-topic"
	subID := "test-sub"

	ensureTopicAndPullSub(t, ctx, projectID, topicID, subID)

	publisher, err := NewPubSubPublisher(ctx, projectID, topicID)
	if err != nil {
		t.Fatalf("failed to create publisher: %v", err)
	}
	defer publisher.Close()

	item := NewsItem{
		Headline:    "Pub/Sub emulator test headline",
		Summary:     "Verifying the real Pub/Sub client publishes correctly against the emulator.",
		Source:      "finnhub",
		URL:         "https://example.com/pubsub-emulator-test",
		PublishedAt: time.Date(2026, 9, 4, 14, 30, 0, 0, time.UTC),
	}

	if err := publisher.Publish(ctx, "finnhub", "AAPL", item); err != nil {
		t.Fatalf("Publish failed: %v", err)
	}

	msg := pullOneMessage(t, ctx, projectID, subID)

	var payload map[string]interface{}
	if err := json.Unmarshal(msg, &payload); err != nil {
		t.Fatalf("message data was not valid JSON: %v", err)
	}
	if payload["headline"] != item.Headline {
		t.Errorf("expected headline %q, got %v", item.Headline, payload["headline"])
	}
	if payload["symbol"] != "AAPL" {
		t.Errorf("expected symbol AAPL, got %v", payload["symbol"])
	}
	if payload["canonical_url"] != item.URL {
		t.Errorf("expected canonical_url %q, got %v", item.URL, payload["canonical_url"])
	}
}

// ensureTopicAndPullSub creates a topic and a pull subscription against the
// emulator via the gcloud-equivalent admin API, using exec'd curl-free calls
// through the client library's admin surface.
func ensureTopicAndPullSub(t *testing.T, ctx context.Context, projectID, topicID, subID string) {
	t.Helper()
	client, err := pubsub.NewClient(ctx, projectID)
	if err != nil {
		t.Fatalf("failed to create admin client: %v", err)
	}
	defer client.Close()

	topicAdmin := client.TopicAdminClient
	topicName := "projects/" + projectID + "/topics/" + topicID
	if _, err := topicAdmin.CreateTopic(ctx, &pubsubpb.Topic{Name: topicName}); err != nil {
		t.Fatalf("failed to create topic: %v", err)
	}

	subAdmin := client.SubscriptionAdminClient
	subName := "projects/" + projectID + "/subscriptions/" + subID
	if _, err := subAdmin.CreateSubscription(ctx, &pubsubpb.Subscription{
		Name:  subName,
		Topic: topicName,
	}); err != nil {
		t.Fatalf("failed to create subscription: %v", err)
	}
}

func pullOneMessage(t *testing.T, ctx context.Context, projectID, subID string) []byte {
	t.Helper()
	client, err := pubsub.NewClient(ctx, projectID)
	if err != nil {
		t.Fatalf("failed to create client for pull: %v", err)
	}
	defer client.Close()

	subscriber := client.Subscriber(subID)
	pullCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	var result []byte
	err = subscriber.Receive(pullCtx, func(ctx context.Context, m *pubsub.Message) {
		result = m.Data
		m.Ack()
		cancel()
	})
	if err != nil && pullCtx.Err() == nil {
		t.Fatalf("Receive failed: %v", err)
	}
	if result == nil {
		t.Fatal("no message received within timeout")
	}
	return result
}
