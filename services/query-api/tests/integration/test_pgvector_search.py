"""Real check for a bug found live: PgVectorRetriever's SQL ordered by
`e.article_id, e.chunk_index, e.vector <=> :query_vector` — article_id sorts
first, so retrieval was effectively random once there were more candidate
articles than top_k, with vector similarity only breaking ties inside a
no-op DISTINCT ON (article_id, chunk_index) is already the embeddings table's
primary key, so every row was already distinct on that pair).

This surfaced when the live poller's real background ingestion added enough
unrelated real articles that a genuinely relevant seeded article stopped
appearing in query-api's own test_end_to_end.py at all (decision_log_claude.md).

Requires `docker compose up postgres`.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

from infrastructure.pgvector_search import PgVectorRetriever

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
)


@pytest.fixture(scope="module")
def embedder():
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    yield engine


def _insert_article_with_embedding(engine, embedder, headline: str, chunk_text: str, symbol: str) -> str:
    article_id = str(uuid.uuid4())
    vector = embedder.encode(chunk_text, convert_to_numpy=True).tolist()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO articles (id, source, headline, published_at, canonical_url, normalized_headline)
                VALUES (CAST(:id AS uuid), 'finnhub', :headline, now(), :url, :normalized)
                """
            ),
            {
                "id": article_id,
                "headline": headline,
                "url": f"https://example.com/{article_id}",
                "normalized": headline.lower(),
            },
        )
        conn.execute(
            text("INSERT INTO article_symbols (article_id, symbol) VALUES (CAST(:id AS uuid), :symbol)"),
            {"id": article_id, "symbol": symbol},
        )
        conn.execute(
            text("INSERT INTO embeddings (article_id, chunk_index, vector, chunk_text) VALUES (CAST(:id AS uuid), 0, :vector, :chunk_text)"),
            {"id": article_id, "vector": str(vector), "chunk_text": chunk_text},
        )
    return article_id


@pytest.fixture
def relevant_and_decoy_articles(engine, embedder):
    relevant_id = _insert_article_with_embedding(
        engine, embedder,
        "Apple unveils new iPhone",
        "Apple announced its latest iPhone with new on-device AI features.",
        "TESTSYM",
    )
    # Enough unrelated decoys that the old buggy ORDER BY (sorting by
    # article_id first) would very likely bury the relevant article outside
    # top_k=5 — this is the exact shape of the real live failure.
    decoy_topics = [
        "Trump discusses trade policy with foreign leaders",
        "Federal Reserve considers interest rate changes",
        "Oil prices fluctuate amid supply concerns",
        "Tech layoffs continue across the industry",
        "Housing market shows signs of cooling",
        "Cryptocurrency markets see volatile trading",
        "Airline industry reports quarterly earnings",
        "Retail sales data released for the quarter",
    ]
    decoy_ids = [
        _insert_article_with_embedding(engine, embedder, topic, topic, "TESTSYM") for topic in decoy_topics
    ]
    yield relevant_id, decoy_ids
    with engine.begin() as conn:
        all_ids = [relevant_id, *decoy_ids]
        conn.execute(text("DELETE FROM embeddings WHERE article_id = ANY(CAST(:ids AS uuid[]))"), {"ids": all_ids})
        conn.execute(text("DELETE FROM article_symbols WHERE article_id = ANY(CAST(:ids AS uuid[]))"), {"ids": all_ids})
        conn.execute(text("DELETE FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": all_ids})


def test_retrieve_ranks_by_similarity_not_article_id(engine, embedder, relevant_and_decoy_articles):
    relevant_id, decoy_ids = relevant_and_decoy_articles
    retriever = PgVectorRetriever(engine, embedder, top_k=3)

    results = retriever.retrieve(symbols=["TESTSYM"], question="What did Apple announce about the iPhone?")

    result_ids = [r.article_id for r in results]
    assert relevant_id in result_ids, (
        f"the genuinely relevant article should rank in the top 3 by similarity, got {result_ids}"
    )
    # The relevant article should score highest of everything returned.
    relevant_result = next(r for r in results if r.article_id == relevant_id)
    assert all(relevant_result.score >= r.score for r in results)


def test_retrieve_scores_are_sorted_descending(engine, embedder, relevant_and_decoy_articles):
    retriever = PgVectorRetriever(engine, embedder, top_k=5)

    results = retriever.retrieve(symbols=["TESTSYM"], question="What did Apple announce about the iPhone?")

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True), f"results should be ordered by descending similarity: {scores}"
