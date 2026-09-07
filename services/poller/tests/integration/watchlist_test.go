// Real end-to-end check for milestone 3 (docs/milestone.md §3): verifies
// PostgresWatchlistReader against a real running Postgres.
// Requires `docker compose up postgres`.
package integration

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"stock-news/poller/internal/poller"
)

func connectOrSkip(t *testing.T) *pgxpool.Pool {
	t.Helper()
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		databaseURL = "postgres://postgres:postgres@localhost:5432/stock-news"
	}

	pool, err := pgxpool.New(context.Background(), databaseURL)
	if err != nil {
		t.Skipf("Postgres not reachable at %s: %v", databaseURL, err)
	}
	if err := pool.Ping(context.Background()); err != nil {
		t.Skipf("Postgres not reachable at %s: %v", databaseURL, err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestDistinctWatchedSymbols_AggregatesWatcherCountAndEarliestAddedAt(t *testing.T) {
	pool := connectOrSkip(t)
	ctx := context.Background()

	// Two distinct users watching AAPL (added at different times), one user
	// watching MSFT — real rows in the real watchlist table.
	var userA, userB, userC string
	err := pool.QueryRow(ctx,
		`INSERT INTO users (google_sub, email) VALUES ($1, $2) RETURNING id`,
		"poller-e2e-user-a", "a@example.com").Scan(&userA)
	if err != nil {
		t.Fatalf("failed to insert test user: %v", err)
	}
	err = pool.QueryRow(ctx,
		`INSERT INTO users (google_sub, email) VALUES ($1, $2) RETURNING id`,
		"poller-e2e-user-b", "b@example.com").Scan(&userB)
	if err != nil {
		t.Fatalf("failed to insert test user: %v", err)
	}
	err = pool.QueryRow(ctx,
		`INSERT INTO users (google_sub, email) VALUES ($1, $2) RETURNING id`,
		"poller-e2e-user-c", "c@example.com").Scan(&userC)
	if err != nil {
		t.Fatalf("failed to insert test user: %v", err)
	}

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM watchlist WHERE user_id IN ($1, $2, $3)`, userA, userB, userC)
		pool.Exec(ctx, `DELETE FROM users WHERE id IN ($1, $2, $3)`, userA, userB, userC)
	})

	_, err = pool.Exec(ctx,
		`INSERT INTO watchlist (user_id, symbol, added_at) VALUES
		 ($1, 'AAPL', '2026-09-01T00:00:00Z'),
		 ($2, 'AAPL', '2026-09-02T00:00:00Z'),
		 ($3, 'MSFT', '2026-09-03T00:00:00Z')`,
		userA, userB, userC)
	if err != nil {
		t.Fatalf("failed to seed watchlist: %v", err)
	}

	reader := poller.NewPostgresWatchlistReader(pool)
	symbols, err := reader.DistinctWatchedSymbols(ctx)
	if err != nil {
		t.Fatalf("DistinctWatchedSymbols failed: %v", err)
	}

	bySymbol := map[string]poller.WatchedSymbol{}
	for _, s := range symbols {
		bySymbol[s.Symbol] = s
	}

	aapl, ok := bySymbol["AAPL"]
	if !ok {
		t.Fatal("expected AAPL in results")
	}
	if aapl.WatcherCount != 2 {
		t.Errorf("expected AAPL watcher count 2, got %d", aapl.WatcherCount)
	}

	msft, ok := bySymbol["MSFT"]
	if !ok {
		t.Fatal("expected MSFT in results")
	}
	if msft.WatcherCount != 1 {
		t.Errorf("expected MSFT watcher count 1, got %d", msft.WatcherCount)
	}
}
