from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from domain.article import Article
from domain.dedup import normalize_headline


class PostgresArticleRepository:
    """Operates on a Connection passed in by the caller (PostgresUnitOfWork)
    rather than opening its own — lets multiple calls share one transaction.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def insert_by_canonical_url(self, article: Article) -> tuple[str, bool]:
        # ON CONFLICT DO UPDATE ... RETURNING (not DO NOTHING + a separate
        # SELECT) — one atomic round trip, closing the race where a concurrent
        # insert lands between a DO NOTHING miss and a follow-up SELECT
        # (same pattern as auth's PostgresRepository.Create; decision_log_claude.md).
        row = self._conn.execute(
            text(
                """
                INSERT INTO articles (source, headline, published_at, canonical_url, normalized_headline)
                VALUES (:source, :headline, :published_at, :canonical_url, :normalized_headline)
                ON CONFLICT (canonical_url) DO UPDATE SET canonical_url = EXCLUDED.canonical_url
                RETURNING id, (xmax = 0) AS inserted
                """
            ),
            {
                "source": article.source,
                "headline": article.headline,
                "published_at": article.published_at,
                "canonical_url": article.canonical_url,
                "normalized_headline": normalize_headline(article.headline),
            },
        ).fetchone()
        return str(row[0]), bool(row[1])

    def insert_by_content_hash(self, article: Article, content_hash: str) -> tuple[str, bool]:
        row = self._conn.execute(
            text(
                """
                INSERT INTO articles (source, headline, published_at, content_hash, normalized_headline)
                VALUES (:source, :headline, :published_at, :content_hash, :normalized_headline)
                ON CONFLICT (content_hash) DO UPDATE SET content_hash = EXCLUDED.content_hash
                RETURNING id, (xmax = 0) AS inserted
                """
            ),
            {
                "source": article.source,
                "headline": article.headline,
                "published_at": article.published_at,
                "content_hash": content_hash,
                "normalized_headline": normalize_headline(article.headline),
            },
        ).fetchone()
        return str(row[0]), bool(row[1])

    def find_by_fuzzy_key(self, fuzzy_key: str) -> str | None:
        # normalized_headline is an exact match against the column populated
        # at insert time by the same normalize_headline() used to build this
        # key — no second, SQL-side normalization to keep in sync (see the
        # column comment in infra/postgres/init.sql).
        published_date, _, normalized_headline = fuzzy_key.partition("|")
        row = self._conn.execute(
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

    def register_fuzzy_key(self, article_id: str, fuzzy_key: str) -> None:
        # Fuzzy matching is derived at query time from headline/published_at
        # (see find_by_fuzzy_key) rather than stored separately — nothing to do
        # here for the Postgres-backed repo; the article row itself already
        # carries what a later lookup needs.
        pass

    def add_symbol(self, article_id: str, symbol: str) -> None:
        self._conn.execute(
            text(
                """
                INSERT INTO article_symbols (article_id, symbol)
                VALUES (:article_id, :symbol)
                ON CONFLICT (article_id, symbol) DO NOTHING
                """
            ),
            {"article_id": article_id, "symbol": symbol},
        )
