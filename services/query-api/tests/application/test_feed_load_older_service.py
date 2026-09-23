from datetime import datetime, timezone

from application.feed_load_older_service import FeedLoadOlderService
from domain.feed import FeedItem


def _item(article_id="a1") -> FeedItem:
    return FeedItem(
        article_id=article_id,
        source="finnhub",
        headline="h",
        symbols=["AAPL"],
        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        canonical_url=None,
    )


class FakeFeedQueries:
    def __init__(self, pages: list[list[FeedItem]]):
        self._pages = pages
        self.call_count = 0
        self.calls: list[tuple] = []

    def recent_for_symbols(self, symbols, limit=50, before=None, before_id=None):
        self.calls.append((symbols, before, before_id))
        page = self._pages[min(self.call_count, len(self._pages) - 1)]
        self.call_count += 1
        return page


class FakeBackfillQueue:
    def __init__(self):
        self.enqueued: list[list[str]] = []

    def enqueue_symbols_backfill(self, symbols: list[str]) -> None:
        self.enqueued.append(symbols)


def test_returns_articles_immediately_if_already_in_postgres():
    feed_queries = FakeFeedQueries(pages=[[_item()]])
    backfill_queue = FakeBackfillQueue()
    service = FeedLoadOlderService(feed_queries, backfill_queue)

    items, backfilling = service.load_older(["AAPL"], before=None, before_id=None)

    assert items == [_item()]
    assert backfilling is False
    assert backfill_queue.enqueued == []  # no need to backfill, Postgres already had it


def test_enqueues_a_background_backfill_when_postgres_page_is_empty():
    # A single enqueue-and-return, not a synchronous retry loop — the
    # background task itself does one backfill window per symbol; the user
    # clicks "load older" / refresh again to check for newly-arrived
    # results, mirroring clicking a button repeatedly rather than blocking
    # the request on however long Finnhub takes (real bug: this used to
    # take 1-2+ minutes synchronously under Finnhub's flakiness, decision_log.md).
    feed_queries = FakeFeedQueries(pages=[[]])
    backfill_queue = FakeBackfillQueue()
    service = FeedLoadOlderService(feed_queries, backfill_queue)

    items, backfilling = service.load_older(["AAPL", "MSFT"], before=None, before_id=None)

    assert items == []
    assert backfilling is True
    assert backfill_queue.enqueued == [["AAPL", "MSFT"]]


def test_passes_cursor_through_to_feed_queries():
    feed_queries = FakeFeedQueries(pages=[[_item()]])
    backfill_queue = FakeBackfillQueue()
    service = FeedLoadOlderService(feed_queries, backfill_queue)

    service.load_older(["AAPL"], before=datetime(2026, 9, 1, tzinfo=timezone.utc), before_id="xyz")

    assert feed_queries.calls == [(["AAPL"], datetime(2026, 9, 1, tzinfo=timezone.utc), "xyz")]
