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


def _insert_article(engine, source, headline, published_at, symbols, ingested_at=None) -> str:
    article_id = str(uuid.uuid4())
    with engine.begin() as conn:
        if ingested_at is not None:
            conn.execute(
                text(
                    """
                    INSERT INTO articles (id, source, headline, published_at, ingested_at, canonical_url, normalized_headline)
                    VALUES (CAST(:id AS uuid), :source, :headline, :published_at, :ingested_at, :url, :normalized)
                    """
                ),
                {
                    "id": article_id,
                    "source": source,
                    "headline": headline,
                    "published_at": published_at,
                    "ingested_at": ingested_at,
                    "url": f"https://example.com/{article_id}",
                    "normalized": headline.lower(),
                },
            )
        else:
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


def test_recent_feed_includes_canonical_url(engine, seeded_articles):
    _, newer, _ = seeded_articles
    queries = FeedQueries(engine)

    items = queries.recent_for_symbols(["AAPL", "MSFT"], limit=10)

    item = next(i for i in items if i.article_id == newer)
    assert item.canonical_url == f"https://example.com/{newer}"


def test_recent_feed_with_before_cursor_returns_only_older_articles(engine):
    # Real bug found live: GET /feed hardcoded limit=50, so once a symbol
    # had more than 50 real articles, backfilled (older) articles could
    # never surface no matter how many times "load more" was clicked —
    # the backfill worked, its results were just structurally unreachable.
    # Keyset pagination via a `before` cursor lets the feed page backward
    # through history instead of always showing the same fixed top-N.
    now = datetime.now(timezone.utc)
    a = _insert_article(engine, "finnhub", "Article A (newest)", now, ["PAGETEST"])
    b = _insert_article(engine, "finnhub", "Article B (middle)", now - timedelta(days=1), ["PAGETEST"])
    c = _insert_article(engine, "finnhub", "Article C (oldest)", now - timedelta(days=2), ["PAGETEST"])
    try:
        queries = FeedQueries(engine)
        first_page = queries.recent_for_symbols(["PAGETEST"], limit=2)
        assert [item.article_id for item in first_page] == [a, b]

        second_page = queries.recent_for_symbols(["PAGETEST"], limit=2, before=first_page[-1].published_at)

        assert [item.article_id for item in second_page] == [c]
    finally:
        with engine.begin() as conn:
            for article_id in (a, b, c):
                conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
                conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_recent_feed_before_cursor_excludes_exact_match_via_id_tiebreak(engine):
    # Two articles sharing the exact same published_at must not both be
    # returned again on the next page (or both silently skipped) — the
    # cursor needs a stable tiebreaker (article id) for a true total order.
    now = datetime.now(timezone.utc)
    same_time = now - timedelta(days=1)
    a = _insert_article(engine, "finnhub", "Same time A", same_time, ["TIETEST"])
    b = _insert_article(engine, "finnhub", "Same time B", same_time, ["TIETEST"])
    try:
        queries = FeedQueries(engine)
        first_page = queries.recent_for_symbols(["TIETEST"], limit=1)
        assert len(first_page) == 1
        first_id = first_page[0].article_id

        second_page = queries.recent_for_symbols(
            ["TIETEST"], limit=10, before=first_page[0].published_at, before_id=first_id
        )

        remaining_ids = [item.article_id for item in second_page]
        assert first_id not in remaining_ids
        assert remaining_ids == [b if first_id == a else a]
    finally:
        with engine.begin() as conn:
            for article_id in (a, b):
                conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
                conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_recent_feed_orders_by_published_at_not_ingested_at(engine):
    # Real bug found live: sort was by ingested_at, but the user wants
    # descending publish date — an article ingested later (e.g. backfilled
    # after the fact) can have an EARLIER published_at than one ingested
    # first, so these two orderings genuinely diverge and need their own test.
    # Both ingested_at values are set explicitly and INVERTED relative to
    # published_at, so a query still sorting by ingested_at would fail this.
    now = datetime.now(timezone.utc)
    old_news_ingested_late = _insert_article(
        engine,
        "finnhub",
        "Old news, backfilled late",
        published_at=now - timedelta(days=10),
        ingested_at=now,  # ingested most recently
        symbols=["ORDERTEST"],
    )
    new_news_ingested_early = _insert_article(
        engine,
        "finnhub",
        "New news, ingested early",
        published_at=now - timedelta(minutes=5),
        ingested_at=now - timedelta(days=10),  # ingested long ago
        symbols=["ORDERTEST"],
    )
    try:
        queries = FeedQueries(engine)

        items = queries.recent_for_symbols(["ORDERTEST"], limit=10)

        ids = [item.article_id for item in items]
        assert ids.index(new_news_ingested_early) < ids.index(old_news_ingested_late)
    finally:
        with engine.begin() as conn:
            for article_id in (old_news_ingested_late, new_news_ingested_early):
                conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
                conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_first_page_guarantees_per_symbol_quota_not_crowded_out_by_a_noisy_symbol(engine):
    # Real bug reported live: a noisy symbol (many articles/day) crowded a
    # newly-added, quieter symbol entirely out of the flat top-50-by-
    # published_at feed, even though the quieter symbol's articles were
    # real and present in Postgres. First page must guarantee each watched
    # symbol at least per_symbol_limit recent articles, not just whichever
    # sort to the top globally.
    now = datetime.now(timezone.utc)
    noisy_ids = [
        _insert_article(engine, "finnhub", f"Noisy article {i}", now - timedelta(minutes=i), ["NOISY"])
        for i in range(30)
    ]
    quiet_ids = [
        _insert_article(engine, "finnhub", f"Quiet article {i}", now - timedelta(days=1, minutes=i), ["QUIET"])
        for i in range(2)
    ]
    try:
        queries = FeedQueries(engine)

        items = queries.recent_for_symbols(["NOISY", "QUIET"], per_symbol_limit=10)

        quiet_in_feed = [item for item in items if "QUIET" in item.symbols]
        assert len(quiet_in_feed) == 2  # both quiet articles present, not crowded out
        noisy_in_feed = [item for item in items if "NOISY" in item.symbols]
        assert len(noisy_in_feed) == 10  # capped at the per-symbol quota, not all 30
    finally:
        with engine.begin() as conn:
            for article_id in (*noisy_ids, *quiet_ids):
                conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
                conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_first_page_results_are_still_sorted_by_published_at_descending(engine):
    now = datetime.now(timezone.utc)
    a_id = _insert_article(engine, "finnhub", "A", now, ["MIXSYM"])
    b_id = _insert_article(engine, "finnhub", "B", now - timedelta(hours=1), ["MIXSYM2"])
    c_id = _insert_article(engine, "finnhub", "C", now - timedelta(hours=2), ["MIXSYM"])
    try:
        queries = FeedQueries(engine)

        items = queries.recent_for_symbols(["MIXSYM", "MIXSYM2"], per_symbol_limit=10)

        ids = [item.article_id for item in items]
        assert ids == [a_id, b_id, c_id]
    finally:
        with engine.begin() as conn:
            for article_id in (a_id, b_id, c_id):
                conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
                conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})
