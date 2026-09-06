"""Real concurrency check for the race fixed in decision_log_claude.md
(#1/#6 from the smell audit): two concurrent calls processing the same
canonical_url must not crash and must not both write embeddings.

Requires a running Postgres from `docker compose up postgres`.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from application.process_article import ProcessArticleUseCase
from domain.article import Article
from infrastructure.chunking import FixedSizeChunker
from infrastructure.dedup_precheck import PostgresDedupPrecheck
from infrastructure.unit_of_work import PostgresUnitOfWork

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
)


class FakeEmbedder:
    def embed(self, texts):
        return [[0.1] * 384 for _ in texts]  # must match schema's vector(384)


@pytest.fixture
def engine():
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM embeddings"))
        conn.execute(text("DELETE FROM article_symbols"))
        conn.execute(text("DELETE FROM articles"))


def test_concurrent_inserts_of_same_canonical_url_do_not_crash_and_produce_one_article(engine):
    use_case = ProcessArticleUseCase(
        uow_factory=lambda: PostgresUnitOfWork(engine),
        dedup_precheck=PostgresDedupPrecheck(engine),
        chunker=FixedSizeChunker(),
        embedder=FakeEmbedder(),
    )

    article = Article(
        source="finnhub",
        headline="Concurrent insert race test",
        published_at=datetime(2026, 9, 4, 14, 30, 0, tzinfo=timezone.utc),
        content="Some content.",
        canonical_url="https://example.com/concurrency-race-test",
    )

    results: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(10)

    def worker():
        try:
            barrier.wait(timeout=5)
            article_id = use_case.process(article, symbol="AAPL")
            results.append(article_id)
        except Exception as exc:  # noqa: BLE001 - want to see any crash from the race
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"concurrent processing raised: {errors}"
    assert len(results) == 10
    assert len(set(results)) == 1, f"expected all 10 calls to agree on one article id, got {set(results)}"

    with engine.begin() as conn:
        article_count = conn.execute(
            text("SELECT count(*) FROM articles WHERE canonical_url = :url"),
            {"url": article.canonical_url},
        ).scalar()
        symbol_count = conn.execute(
            text("SELECT count(*) FROM article_symbols WHERE article_id = :id"),
            {"id": results[0]},
        ).scalar()

    assert article_count == 1
    assert symbol_count == 1
