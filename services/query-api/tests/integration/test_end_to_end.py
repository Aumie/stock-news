"""Real end-to-end check for milestone 1 (docs/milestone.md §1): given
articles already embedded in Postgres/pgvector, verify PgVectorRetriever +
QueryService produce a grounded answer (LLM stubbed — see docs/decision_log.md
on why a real paid LLM call isn't part of the automated suite).

Requires a running Postgres from `docker compose up postgres`.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

from application.query_service import QueryService
from infrastructure.pgvector_search import PgVectorRetriever

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/dataen"
)


class StubLLM:
    def stream(self, prompt: str):
        self.last_prompt = prompt
        yield "Apple announced a new iPhone with on-device AI, per finnhub."


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
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def seeded_article(engine, embedder):
    article_id = str(uuid.uuid4())
    chunk_text = "Apple announced its latest iPhone with new on-device AI features."
    vector = embedder.encode(chunk_text, convert_to_numpy=True).tolist()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO articles (id, source, headline, published_at, canonical_url)
                VALUES (:id, 'finnhub', 'Apple unveils new iPhone', :published_at, :url)
                """
            ),
            {
                "id": article_id,
                "published_at": datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc),
                "url": f"https://example.com/{article_id}",
            },
        )
        conn.execute(
            text("INSERT INTO article_symbols (article_id, symbol) VALUES (:id, 'AAPL')"),
            {"id": article_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO embeddings (article_id, chunk_index, vector, chunk_text)
                VALUES (:id, 0, :vector, :chunk_text)
                """
            ),
            {"id": article_id, "vector": str(vector), "chunk_text": chunk_text},
        )
    return article_id


def test_query_service_returns_grounded_answer_from_real_retrieval(engine, embedder, seeded_article):
    retriever = PgVectorRetriever(engine, embedder)
    llm = StubLLM()
    service = QueryService(retriever=retriever, llm=llm)

    output = "".join(service.answer(symbols=["AAPL"], question="What did Apple announce?"))

    assert "iPhone" in output
    assert "on-device AI features" in llm.last_prompt


def test_query_service_guardrail_when_symbol_has_no_articles(engine, embedder, seeded_article):
    retriever = PgVectorRetriever(engine, embedder)
    llm = StubLLM()
    service = QueryService(retriever=retriever, llm=llm)

    output = "".join(service.answer(symbols=["TSLA"], question="What's new?"))

    assert "news" in output.lower()
