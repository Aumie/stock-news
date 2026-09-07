"""Live check for milestone 6's live ingestion feed (docs/milestone.md §6):
recently ingested articles, scoped to a set of watched symbols, most recent
first, with symbols aggregated per article (one article can be tagged with
several watched symbols).

Requires `docker compose up postgres`.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from infrastructure.feed_queries import FeedQueries

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
)


@pytest.fixture
def engine():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    yield engine


@pytest.fixture
def seeded_articles(engine):
    now = datetime.now(timezone.utc)
    older = _insert_article(engine, "finnhub", "Older AAPL story", now - timedelta(minutes=10), ["AAPL"])
    newer = _insert_article(engine, "marketaux", "Newer AAPL+MSFT story", now - timedelta(minutes=1), ["AAPL", "MSFT"])
    unwatched = _insert_article(engine, "finnhub", "Unwatched TSLA story", now, ["TSLA"])
    yield older, newer, unwatched
    with engine.begin() as conn:
        for article_id in (older, newer, unwatched):
            conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
            conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def _insert_article(engine, source, headline, published_at, symbols) -> str:
    article_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO articles (id, source, headline, published_at, canonical_url, normalized_headline)
                VALUES (CAST(:id AS uuid), :source, :headline, :published_at, :url, :normalized)
                """
            ),
            {
                "id": article_id,
                "source": source,
                "headline": headline,
                "published_at": published_at,
                "url": f"https://example.com/{article_id}",
                "normalized": headline.lower(),
            },
        )
        for symbol in symbols:
            conn.execute(
                text("INSERT INTO article_symbols (article_id, symbol) VALUES (CAST(:id AS uuid), :symbol)"),
                {"id": article_id, "symbol": symbol},
            )
    return article_id


def test_recent_feed_scoped_to_watched_symbols_most_recent_first(engine, seeded_articles):
    older, newer, unwatched = seeded_articles
    queries = FeedQueries(engine)

    items = queries.recent_for_symbols(["AAPL", "MSFT"], limit=10)

    ids = [item.article_id for item in items]
    assert newer in ids
    assert older in ids
    assert unwatched not in ids
    assert ids.index(newer) < ids.index(older)  # most recent first


def test_recent_feed_aggregates_symbols_per_article(engine, seeded_articles):
    _, newer, _ = seeded_articles
    queries = FeedQueries(engine)

    items = queries.recent_for_symbols(["AAPL", "MSFT"], limit=10)

    item = next(i for i in items if i.article_id == newer)
    assert set(item.symbols) == {"AAPL", "MSFT"}


def test_recent_feed_with_no_watched_symbols_is_empty(engine):
    queries = FeedQueries(engine)

    assert queries.recent_for_symbols([], limit=10) == []
