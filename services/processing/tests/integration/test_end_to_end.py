"""Real end-to-end check for milestone 1 (docs/milestone.md §1):
ingest -> dedup -> embed -> write to a real Postgres/pgvector, then verify a
real vector search retrieves the right grounded chunks.

Requires a running Postgres from `docker compose up postgres` at
DATABASE_URL (defaults to localhost:5432). Not run as part of the default
`pytest` invocation from CI without that dependency — see conftest.py's skip.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from application.process_article import ProcessArticleUseCase
from domain.article import Article
from infrastructure.chunking import FixedSizeChunker
from infrastructure.embedding_writer import PostgresEmbeddingWriter
from infrastructure.embeddings import SentenceTransformerEmbedder
from infrastructure.postgres_repo import PostgresArticleRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/dataen"
)


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
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


@pytest.fixture(scope="module")
def embedder():
    return SentenceTransformerEmbedder()


@pytest.fixture(scope="module")
def use_case(engine, embedder):
    return ProcessArticleUseCase(
        repo=PostgresArticleRepository(engine),
        chunker=FixedSizeChunker(),
        embedder=embedder,
        embedding_writer=PostgresEmbeddingWriter(engine),
    )


def test_ingest_then_vector_search_returns_grounded_chunk(engine, use_case, embedder):
    apple_article = Article(
        source="finnhub",
        headline="Apple unveils new iPhone with on-device AI features",
        published_at=datetime(2026, 9, 4, 14, 30, 0, tzinfo=timezone.utc),
        content=(
            "Apple announced its latest iPhone lineup today, headlined by new "
            "on-device AI capabilities and an upgraded camera system."
        ),
        canonical_url="https://example.com/apple-iphone-ai-e2e",
    )
    msft_article = Article(
        source="finnhub",
        headline="Microsoft reports strong cloud growth in latest earnings",
        published_at=datetime(2026, 9, 4, 16, 0, 0, tzinfo=timezone.utc),
        content=(
            "Microsoft's Azure cloud division posted double-digit revenue growth "
            "this quarter, beating analyst expectations."
        ),
        canonical_url="https://example.com/msft-earnings-e2e",
    )

    use_case.process(apple_article, symbol="AAPL")
    use_case.process(msft_article, symbol="MSFT")

    with engine.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM embeddings")).scalar()
    assert count == 2

    # Exercises the same query-api/infrastructure/pgvector_search.py would run,
    # inline here since that module lives in a separate service's dependency
    # tree (query-api owns retrieval; processing owns writing embeddings).
    query_vector = embedder._model.encode("What did Apple announce?", convert_to_numpy=True).tolist()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT e.article_id, e.chunk_text, a.source, a.headline
                FROM embeddings e
                JOIN articles a ON a.id = e.article_id
                JOIN article_symbols s ON s.article_id = a.id
                WHERE s.symbol = ANY(:symbols)
                ORDER BY e.vector <=> :query_vector
                LIMIT 5
                """
            ),
            {"query_vector": str(query_vector), "symbols": ["AAPL"]},
        ).fetchall()

    assert len(rows) == 1
    assert "iPhone" in rows[0].chunk_text
    assert rows[0].source == "finnhub"


def test_duplicate_article_across_sources_is_not_reembedded(engine, use_case):
    a = Article(
        source="finnhub",
        headline="Tesla announces new factory location",
        published_at=datetime(2026, 9, 5, 9, 0, 0, tzinfo=timezone.utc),
        content="Tesla will build a new factory.",
        canonical_url=None,
    )
    b = Article(
        source="marketaux",
        headline="Tesla Announces New Factory Location!",
        published_at=datetime(2026, 9, 5, 20, 0, 0, tzinfo=timezone.utc),
        content="Tesla will build a new factory, the company confirmed.",
        canonical_url=None,
    )

    id_a = use_case.process(a, symbol="TSLA")
    id_b = use_case.process(b, symbol="TSLA")

    assert id_a == id_b

    with engine.begin() as conn:
        symbol_count = conn.execute(
            text("SELECT count(*) FROM article_symbols WHERE article_id = :id"),
            {"id": id_a},
        ).scalar()
    assert symbol_count == 1
