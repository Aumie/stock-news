from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from domain.stats import BusiestSymbolDay, OverviewStats, PriceDelta, RollingVolumePoint


class StatsQueries:
    """Reads from `daily_symbol_features` (services/daily-batch/dbt/models),
    the feature-store-lite table dbt materializes daily. Deliberately
    non-trivial SQL per docs/stock-news-digest-requirements.md §4.6: window
    functions, not flat COUNT/GROUP BY.

    The table doesn't exist until the daily-batch job has run at least once
    (true for any fresh deployment) — every method degrades to an empty/zero
    result in that case instead of raising, since "no data yet" is a normal
    state here, not an error (a real 500 was caught live during milestone 6's
    verification, see docs/decision_log_claude.md).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _table_exists(self) -> bool:
        return inspect(self._engine).has_table("daily_symbol_features")

    # Both 7d and 30d figures are derived from a single 30-day fetch per
    # symbol (one query each for volume/total/price, not two) — a real
    # scaling concern the user raised directly: doubling every query per
    # window would mean 6 queries x N watched symbols per page load instead
    # of 3, which matters once a watchlist has many symbols even though the
    # JSON response itself stays small either way (decision_log.md).

    def rolling_article_volume(self, symbol: str) -> list[RollingVolumePoint]:
        if not self._table_exists():
            return []
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        date,
                        article_count,
                        AVG(article_count) OVER (
                            ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                        ) AS rolling_avg_7d,
                        AVG(article_count) OVER (
                            ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                        ) AS rolling_avg_30d
                    FROM daily_symbol_features
                    WHERE symbol = :symbol
                      AND date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY date
                    """
                ),
                {"symbol": symbol},
            ).fetchall()
        return [
            RollingVolumePoint(
                symbol=symbol,
                date=row.date,
                articles_today=row.article_count,
                rolling_avg_7d=float(row.rolling_avg_7d),
                rolling_avg_30d=float(row.rolling_avg_30d),
            )
            for row in rows
        ]

    def total_ingestion(self, symbol: str) -> tuple[int, int]:
        """Returns (total_7d, total_30d)."""
        if not self._table_exists():
            return (0, 0)
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(article_count) FILTER (
                            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                        ), 0) AS total_7d,
                        COALESCE(SUM(article_count), 0) AS total_30d
                    FROM daily_symbol_features
                    WHERE symbol = :symbol
                      AND date >= CURRENT_DATE - INTERVAL '30 days'
                    """
                ),
                {"symbol": symbol},
            ).fetchone()
        return (int(row.total_7d), int(row.total_30d))

    def price_deltas(self, symbol: str) -> list[PriceDelta]:
        """Returns up to 30 days of deltas; callers wanting the 7d view slice the tail themselves."""
        if not self._table_exists():
            return []
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT date, price_close, price_change_pct
                    FROM daily_symbol_features
                    WHERE symbol = :symbol AND price_close IS NOT NULL
                      AND date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY date
                    """
                ),
                {"symbol": symbol},
            ).fetchall()
        return [
            PriceDelta(
                symbol=symbol,
                date=row.date,
                price_close=float(row.price_close),
                price_change_pct=float(row.price_change_pct) if row.price_change_pct is not None else None,
            )
            for row in rows
        ]

    def overview_stats(self, symbols: list[str]) -> OverviewStats:
        # Real-time counts against `articles`/`article_symbols` directly —
        # deliberately not from daily_symbol_features, which only updates
        # once a day (§4.6) and would make this stale until the next batch
        # run. Filters on published_at, not ingested_at — a real bug found
        # live: a 30-day backfill re-run inserts old news with ingested_at
        # set to right now, so counting by ingested_at made this balloon to
        # a symbol's entire article history any time a backfill was
        # re-triggered, not just genuinely new same-day news
        # (decision_log_claude.md).
        if not symbols:
            return OverviewStats(articles_ingested_today=0, tickers_tracked=0)

        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT a.id) AS articles_today
                    FROM articles a
                    JOIN article_symbols s ON s.article_id = a.id
                    WHERE s.symbol = ANY(:symbols)
                      AND a.published_at >= date_trunc('day', now())
                    """
                ),
                {"symbols": symbols},
            ).fetchone()
        return OverviewStats(articles_ingested_today=row.articles_today, tickers_tracked=len(symbols))

    def busiest_symbol_day(self, symbols: list[str]) -> BusiestSymbolDay | None:
        """Which watched symbol had the most articles published on a single
        day, and how many. Queries `articles`/`article_symbols` directly
        (like `overview_stats`) rather than `daily_symbol_features` — that
        table is only as fresh as the last daily-batch run and can go
        missing entirely after a Postgres restart with nothing to rebuild it
        (decision_log_claude.md), so a real-time count from the source
        tables is the more reliable answer for an ad-hoc question like this.
        """
        if not symbols:
            return None
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT s.symbol, a.published_at::date AS day, COUNT(*) AS article_count
                    FROM articles a
                    JOIN article_symbols s ON s.article_id = a.id
                    WHERE s.symbol = ANY(:symbols)
                    GROUP BY s.symbol, day
                    ORDER BY article_count DESC
                    LIMIT 1
                    """
                ),
                {"symbols": symbols},
            ).fetchone()
        if row is None:
            return None
        return BusiestSymbolDay(symbol=row.symbol, date=row.day, article_count=row.article_count)
