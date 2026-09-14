package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	pollerpkg "stock-news/poller/internal/poller"
)

func main() {
	// The shared database-url secret (used by every service in this project)
	// carries a "+psycopg" driver suffix for the Python/SQLAlchemy services —
	// pgx has no notion of driver suffixes and fails to parse the URL with
	// one present, so strip it here rather than changing the shared secret
	// value and breaking the Python services again.
	databaseURL := strings.Replace(
		envOrDefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/stock-news"),
		"postgresql+psycopg://", "postgresql://", 1,
	)
	finnhubBaseURL := envOrDefault("FINNHUB_BASE_URL", "https://finnhub.io/api/v1")
	finnhubToken := os.Getenv("FINNHUB_API_KEY")
	marketauxBaseURL := envOrDefault("MARKETAUX_BASE_URL", "https://api.marketaux.com")
	marketauxToken := os.Getenv("MARKETAUX_API_KEY")
	pubsubProjectID := envOrDefault("PUBSUB_PROJECT_ID", "stock-news-local")
	pubsubTopicID := envOrDefault("PUBSUB_TOPIC_ID", "articles")
	port := envOrDefault("PORT", "8080")
	finnhubCap := envOrDefaultInt("FINNHUB_SYMBOL_CAP", 45)

	if finnhubToken == "" {
		log.Println("WARNING: FINNHUB_API_KEY is not set — Finnhub calls will fail. " +
			"No live key was available while building this service (decision_log_claude.md).")
	}
	if marketauxToken == "" {
		log.Println("INFO: MARKETAUX_API_KEY is not set — overflow symbols beyond the Finnhub " +
			"cap will be tracked but not polled, not silently dropped or crashed on.")
	}

	pool, err := pgxpool.New(context.Background(), databaseURL)
	if err != nil {
		log.Fatalf("failed to connect to postgres: %v", err)
	}
	defer pool.Close()

	ctx := context.Background()
	pubsubPublisher, err := pollerpkg.NewPubSubPublisher(ctx, pubsubProjectID, pubsubTopicID)
	if err != nil {
		log.Fatalf("failed to create pubsub publisher: %v", err)
	}
	defer pubsubPublisher.Close()

	deps := pollerpkg.Deps{
		Watchlist:  pollerpkg.NewPostgresWatchlistReader(pool),
		Finnhub:    pollerpkg.NewFinnhubClient(finnhubBaseURL, finnhubToken),
		Publisher:  pubsubPublisher,
		FinnhubCap: finnhubCap,
	}
	if marketauxToken != "" {
		deps.Marketaux = pollerpkg.NewMarketauxClient(marketauxBaseURL, marketauxToken)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/trigger", pollerpkg.TriggerHandler(deps))
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		log.Fatalf("failed to listen on port %s: %v", port, err)
	}

	log.Printf("poller service listening on :%s", port)
	if err := http.Serve(lis, mux); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envOrDefaultInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return parsed
}
