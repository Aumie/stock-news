package main

import (
	"context"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	pollerpkg "stock-news/poller/internal/poller"
)

func main() {
	logger := pollerpkg.NewLogger(envOrDefault("LOG_ENV", "dev"))

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
		logger.Warn("FINNHUB_API_KEY is not set — Finnhub calls will fail. " +
			"No live key was available while building this service (decision_log_claude.md).")
	}
	if marketauxToken == "" {
		logger.Info("MARKETAUX_API_KEY is not set — overflow symbols beyond the Finnhub " +
			"cap will be tracked but not polled, not silently dropped or crashed on.")
	}

	pool, err := pgxpool.New(context.Background(), databaseURL)
	if err != nil {
		logger.Error("failed to connect to postgres", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	ctx := context.Background()
	pubsubPublisher, err := pollerpkg.NewPubSubPublisher(ctx, pubsubProjectID, pubsubTopicID)
	if err != nil {
		logger.Error("failed to create pubsub publisher", "error", err)
		os.Exit(1)
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
	mux.HandleFunc("/trigger", pollerpkg.TriggerHandler(deps, logger))
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		logger.Error("failed to listen", "port", port, "error", err)
		os.Exit(1)
	}

	logger.Info("poller service listening", "port", port)
	if err := http.Serve(lis, mux); err != nil {
		logger.Error("failed to serve", "error", err)
		os.Exit(1)
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
