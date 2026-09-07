package poller

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// WatchlistReader is defined here, next to the use case that consumes it,
// per this project's Go-idiomatic package structure (decision_log.md).
type WatchlistReader interface {
	DistinctWatchedSymbols(ctx context.Context) ([]WatchedSymbol, error)
}

type PostgresWatchlistReader struct {
	pool *pgxpool.Pool
}

func NewPostgresWatchlistReader(pool *pgxpool.Pool) *PostgresWatchlistReader {
	return &PostgresWatchlistReader{pool: pool}
}

// DistinctWatchedSymbols re-reads the distinct set of watched symbols every
// call — this *is* the diff, no separate subscription-manager or persisted
// subscription lifecycle needed (§4.2). Aggregates distinct watcher count and
// earliest added_at per symbol, which AssignSources needs for ranking.
func (r *PostgresWatchlistReader) DistinctWatchedSymbols(ctx context.Context) ([]WatchedSymbol, error) {
	rows, err := r.pool.Query(
		ctx,
		`SELECT symbol, count(DISTINCT user_id) AS watcher_count, min(added_at) AS earliest_added_at
		 FROM watchlist
		 GROUP BY symbol`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var symbols []WatchedSymbol
	for rows.Next() {
		var s WatchedSymbol
		var addedAt time.Time
		if err := rows.Scan(&s.Symbol, &s.WatcherCount, &addedAt); err != nil {
			return nil, err
		}
		s.AddedAt = addedAt
		symbols = append(symbols, s)
	}
	return symbols, rows.Err()
}
