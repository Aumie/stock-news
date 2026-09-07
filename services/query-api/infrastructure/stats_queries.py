from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.stats import IngestionLagStats, PriceDelta, RollingVolumePoint


class StatsQueries:
    """Reads from `daily_symbol_features` (services/daily-batch/dbt/models),
    the feature-store-lite table dbt materializes daily. Deliberately
    non-trivial SQL per docs/stock-news-digest-requirements.md §4.6: window
    functions, not flat COUNT/GROUP BY.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def rolling_article_volume(self, symbol: str) -> list[RollingVolumePoint]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        date,
                        article_count,
                        AVG(article_count) OVER (
                            ORDER BY date
                            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                        ) AS rolling_7day_avg
                    FROM daily_symbol_features
                    WHERE symbol = :symbol
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
                rolling_7day_avg=float(row.rolling_7day_avg),
            )
            for row in rows
        ]

    def ingestion_lag_stats(self, symbol: str) -> IngestionLagStats:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        AVG(avg_ingestion_lag_seconds) AS avg_lag,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY avg_ingestion_lag_seconds) AS p50_lag,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY avg_ingestion_lag_seconds) AS p95_lag
                    FROM daily_symbol_features
                    WHERE symbol = :symbol AND avg_ingestion_lag_seconds IS NOT NULL
                    """
                ),
                {"symbol": symbol},
            ).fetchone()
        return IngestionLagStats(
            symbol=symbol,
            avg_lag_seconds=float(row.avg_lag) if row.avg_lag is not None else 0.0,
            p50_lag_seconds=float(row.p50_lag) if row.p50_lag is not None else 0.0,
            p95_lag_seconds=float(row.p95_lag) if row.p95_lag is not None else 0.0,
        )

    def price_deltas(self, symbol: str) -> list[PriceDelta]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT date, price_close, price_change_pct
                    FROM daily_symbol_features
                    WHERE symbol = :symbol AND price_close IS NOT NULL
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
