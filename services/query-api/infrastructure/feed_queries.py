from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.feed import FeedItem


class FeedQueries:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def recent_for_symbols(self, symbols: list[str], limit: int = 50) -> list[FeedItem]:
        if not symbols:
            return []

        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        a.id, a.source, a.headline, a.published_at, a.ingested_at,
                        ARRAY_AGG(DISTINCT s.symbol) AS symbols
                    FROM articles a
                    JOIN article_symbols s ON s.article_id = a.id
                    WHERE a.id IN (
                        SELECT article_id FROM article_symbols WHERE symbol = ANY(:symbols)
                    )
                    GROUP BY a.id, a.source, a.headline, a.published_at, a.ingested_at
                    ORDER BY a.ingested_at DESC
                    LIMIT :limit
                    """
                ),
                {"symbols": symbols, "limit": limit},
            ).fetchall()

        return [
            FeedItem(
                article_id=str(row.id),
                source=row.source,
                headline=row.headline,
                symbols=list(row.symbols),
                published_at=row.published_at,
                ingested_at=row.ingested_at,
            )
            for row in rows
        ]
