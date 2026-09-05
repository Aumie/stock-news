from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.article import Article


class PostgresArticleRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def insert_by_canonical_url(self, article: Article) -> tuple[str, bool]:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO articles (source, headline, published_at, canonical_url)
                    VALUES (:source, :headline, :published_at, :canonical_url)
                    ON CONFLICT (canonical_url) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "source": article.source,
                    "headline": article.headline,
                    "published_at": article.published_at,
                    "canonical_url": article.canonical_url,
                },
            ).fetchone()
            if row is not None:
                return str(row[0]), True

            existing = conn.execute(
                text("SELECT id FROM articles WHERE canonical_url = :url"),
                {"url": article.canonical_url},
            ).fetchone()
            return str(existing[0]), False

    def insert_by_content_hash(self, article: Article, content_hash: str) -> tuple[str, bool]:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO articles (source, headline, published_at, content_hash)
                    VALUES (:source, :headline, :published_at, :content_hash)
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "source": article.source,
                    "headline": article.headline,
                    "published_at": article.published_at,
                    "content_hash": content_hash,
                },
            ).fetchone()
            if row is not None:
                return str(row[0]), True

            existing = conn.execute(
                text("SELECT id FROM articles WHERE content_hash = :h"),
                {"h": content_hash},
            ).fetchone()
            return str(existing[0]), False

    def find_by_fuzzy_key(self, fuzzy_key: str) -> str | None:
        published_date, _, normalized_headline = fuzzy_key.partition("|")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id FROM articles
                    WHERE published_at::date = CAST(:published_date AS date)
                      AND lower(regexp_replace(headline, '[^\\w\\s]', '', 'g')) = :normalized_headline
                    LIMIT 1
                    """
                ),
                {"published_date": published_date, "normalized_headline": normalized_headline},
            ).fetchone()
            return str(row[0]) if row is not None else None

    def register_fuzzy_key(self, article_id: str, fuzzy_key: str) -> None:
        # Fuzzy matching is derived at query time from headline/published_at
        # (see find_by_fuzzy_key) rather than stored separately — nothing to do
        # here for the Postgres-backed repo; the article row itself already
        # carries what a later lookup needs.
        pass

    def add_symbol(self, article_id: str, symbol: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO article_symbols (article_id, symbol)
                    VALUES (:article_id, :symbol)
                    ON CONFLICT (article_id, symbol) DO NOTHING
                    """
                ),
                {"article_id": article_id, "symbol": symbol},
            )
