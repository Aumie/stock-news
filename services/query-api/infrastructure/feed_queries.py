from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.feed import FeedItem


class FeedQueries:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def recent_for_symbols(
        self,
        symbols: list[str],
        limit: int = 50,
        before: datetime | None = None,
        before_id: str | None = None,
        per_symbol_limit: int | None = None,
    ) -> list[FeedItem]:
        if not symbols:
            return []

        # per_symbol_limit is only meaningful on the very first page (no
        # cursor) — real bug found live: a flat top-N-by-published_at query
        # let one noisy symbol crowd a newly-added, quieter symbol out of
        # the feed entirely, even though the quieter symbol's articles were
        # real and present. Guarantees every watched symbol at least
        # per_symbol_limit recent articles via ROW_NUMBER() per symbol,
        # then merges and re-sorts for display. Deliberately not extended to
        # paged requests (before/before_id) — that needs a genuine
        # per-symbol cursor, a larger redesign deferred until it's actually
        # needed beyond the first page (decision_log_claude.md).
        if per_symbol_limit is not None and before is None:
            with self._engine.begin() as conn:
                rows = conn.execute(
                    text(
                        """
                        WITH ranked AS (
                            SELECT
                                a.id, a.source, a.headline, a.published_at, a.ingested_at, a.canonical_url,
                                s.symbol,
                                ROW_NUMBER() OVER (PARTITION BY s.symbol ORDER BY a.published_at DESC, a.id DESC) AS rn
                            FROM articles a
                            JOIN article_symbols s ON s.article_id = a.id
                            WHERE s.symbol = ANY(:symbols)
                        )
                        SELECT
                            r.id, r.source, r.headline, r.published_at, r.ingested_at, r.canonical_url,
                            ARRAY_AGG(DISTINCT a2.symbol) AS symbols
                        FROM ranked r
                        JOIN article_symbols a2 ON a2.article_id = r.id
                        WHERE r.rn <= :per_symbol_limit
                        GROUP BY r.id, r.source, r.headline, r.published_at, r.ingested_at, r.canonical_url
                        ORDER BY r.published_at DESC, r.id DESC
                        """
                    ),
                    {"symbols": symbols, "per_symbol_limit": per_symbol_limit},
                ).fetchall()
            return [
                FeedItem(
                    article_id=str(row.id),
                    source=row.source,
                    headline=row.headline,
                    symbols=list(row.symbols),
                    published_at=row.published_at,
                    ingested_at=row.ingested_at,
                    canonical_url=row.canonical_url,
                )
                for row in rows
            ]

        # Keyset pagination on (published_at, id) DESC, not plain
        # `published_at < :before` — two articles can share the exact same
        # published_at, and without the id tiebreak a page boundary landing
        # between them would either duplicate or silently skip one
        # (confirmed both directions are possible without it). `before_id`
        # is optional (first page has no cursor at all).
        cursor_clause = ""
        params = {"symbols": symbols, "limit": limit}
        if before is not None:
            if before_id is not None:
                cursor_clause = "AND (a.published_at, a.id) < (:before, CAST(:before_id AS uuid))"
                params["before_id"] = before_id
            else:
                cursor_clause = "AND a.published_at < :before"
            params["before"] = before

        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        a.id, a.source, a.headline, a.published_at, a.ingested_at, a.canonical_url,
                        ARRAY_AGG(DISTINCT s.symbol) AS symbols
                    FROM articles a
                    JOIN article_symbols s ON s.article_id = a.id
                    WHERE a.id IN (
                        SELECT article_id FROM article_symbols WHERE symbol = ANY(:symbols)
                    )
                    {cursor_clause}
                    GROUP BY a.id, a.source, a.headline, a.published_at, a.ingested_at, a.canonical_url
                    ORDER BY a.published_at DESC, a.id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()

        return [
            FeedItem(
                article_id=str(row.id),
                source=row.source,
                headline=row.headline,
                symbols=list(row.symbols),
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                canonical_url=row.canonical_url,
            )
            for row in rows
        ]
