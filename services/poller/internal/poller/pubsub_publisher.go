package poller

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"cloud.google.com/go/pubsub/v2"
)

// PubSubPublisher publishes to a real GCP Pub/Sub topic — the actual client
// library and wire contract, not a stand-in. Locally this points at the
// Pub/Sub emulator (PUBSUB_EMULATOR_HOST), which supports real push
// subscriptions, so Processing's /pubsub/push endpoint is called directly —
// no bridging relay needed, unlike the earlier Redis Streams design
// (decision_log.md's "Local queue" entry). At the milestone 7 cloud
// migration, only the environment changes (no PUBSUB_EMULATOR_HOST, a real
// project); this code is unchanged.
type PubSubPublisher struct {
	client *pubsub.Client
	topic  *pubsub.Publisher
}

func NewPubSubPublisher(ctx context.Context, projectID, topicID string) (*PubSubPublisher, error) {
	client, err := pubsub.NewClient(ctx, projectID)
	if err != nil {
		return nil, fmt.Errorf("creating pubsub client: %w", err)
	}

	return &PubSubPublisher{
		client: client,
		topic:  client.Publisher(topicID),
	}, nil
}

func (p *PubSubPublisher) Publish(ctx context.Context, source, symbol string, item NewsItem) error {
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

	result := p.topic.Publish(ctx, &pubsub.Message{Data: payloadJSON})
	if _, err := result.Get(ctx); err != nil {
		return fmt.Errorf("publishing to pubsub topic: %w", err)
	}
	return nil
}

func (p *PubSubPublisher) Close() error {
	p.topic.Stop()
	return p.client.Close()
}
