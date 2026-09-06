from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.article import Article
from domain.dedup import content_hash, fuzzy_key


class PostgresDedupPrecheck:
    """Read-only "does this already exist" check, run before embedding and
    outside any write transaction — lets ProcessArticleUseCase skip the
    (CPU-bound, potentially slow) embed call entirely for an already-known
    article, preserving the spec's "no re-embed on a cross-match" guarantee
    (§4.3) without holding a DB transaction open across that embed call.

    Best-effort only: a concurrent insert can still land between this check
    and the real transaction. That race is closed by the transaction's own
    ON CONFLICT DO UPDATE ... RETURNING (PostgresArticleRepository), not here.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_existing(self, article: Article) -> str | None:
        with self._engine.connect() as conn:
            if article.canonical_url:
                row = conn.execute(
                    text("SELECT id FROM articles WHERE canonical_url = :url"),
                    {"url": article.canonical_url},
                ).fetchone()
                return str(row[0]) if row is not None else None

            row = conn.execute(
                text("SELECT id FROM articles WHERE content_hash = :h"),
                {"h": content_hash(article)},
            ).fetchone()
            if row is not None:
                return str(row[0])

            published_date, _, normalized_headline = fuzzy_key(article).partition("|")
            row = conn.execute(
                text(
                    """
                    SELECT id FROM articles
                    WHERE published_at::date = CAST(:published_date AS date)
                      AND normalized_headline = :normalized_headline
                    LIMIT 1
                    """
                ),
                {"published_date": published_date, "normalized_headline": normalized_headline},
            ).fetchone()
            return str(row[0]) if row is not None else None
