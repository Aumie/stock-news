from datetime import datetime, timezone

import pytest

from application.feed_load_older_service import FeedLoadOlderService
from domain.backfill import BackfillResult, MultiSymbolBackfillResult, SymbolBackfillResult
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


def _backfill_result(articles_fetched=0, has_more=True):
    from datetime import date

    return MultiSymbolBackfillResult(
        per_symbol=[
            SymbolBackfillResult(
                symbol="AAPL",
                result=BackfillResult(
                    articles_fetched=articles_fetched, from_date=date(2026, 8, 1), to_date=date(2026, 8, 15), has_more=has_more
                ),
            )
        ]
    )


class FakeFeedQueries:
    def __init__(self, pages: list[list[FeedItem]]):
        self._pages = pages
        self.call_count = 0

    def recent_for_symbols(self, symbols, limit=50, before=None, before_id=None):
        page = self._pages[min(self.call_count, len(self._pages) - 1)]
        self.call_count += 1
        return page


class FakeBackfillService:
    def __init__(self, results: list[MultiSymbolBackfillResult]):
        self._results = results
        self.call_count = 0

    def load_more_for_symbols(self, symbols):
        result = self._results[min(self.call_count, len(self._results) - 1)]
        self.call_count += 1
        return result


def test_returns_articles_immediately_if_already_in_postgres():
    feed_queries = FakeFeedQueries(pages=[[_item()]])
    backfill_service = FakeBackfillService(results=[])
    service = FeedLoadOlderService(feed_queries, backfill_service)

    items, exhausted = service.load_older(["AAPL"], before=None, before_id=None)

    assert items == [_item()]
    assert exhausted is False
    assert backfill_service.call_count == 0  # no need to backfill, Postgres already had it


def test_backfills_once_when_postgres_page_is_empty_then_finds_articles():
    feed_queries = FakeFeedQueries(pages=[[], [_item()]])
    backfill_service = FakeBackfillService(results=[_backfill_result(articles_fetched=5)])
    service = FeedLoadOlderService(feed_queries, backfill_service)

    items, exhausted = service.load_older(["AAPL"], before=None, before_id=None)

    assert items == [_item()]
    assert exhausted is False
    assert backfill_service.call_count == 1


def test_keeps_backfilling_through_empty_windows_up_to_the_cap():
    feed_queries = FakeFeedQueries(pages=[[]])  # always empty in Postgres
    backfill_service = FakeBackfillService(results=[_backfill_result(articles_fetched=0)])  # always empty window
    service = FeedLoadOlderService(feed_queries, backfill_service)

    items, exhausted = service.load_older(["AAPL"], before=None, before_id=None)

    assert items == []
    assert exhausted is True
    assert backfill_service.call_count == FeedLoadOlderService.MAX_BACKFILL_ATTEMPTS


def test_stops_early_if_a_backfill_window_reports_no_more_history():
    feed_queries = FakeFeedQueries(pages=[[]])
    backfill_service = FakeBackfillService(results=[_backfill_result(articles_fetched=0, has_more=False)])
    service = FeedLoadOlderService(feed_queries, backfill_service)

    items, exhausted = service.load_older(["AAPL"], before=None, before_id=None)

    assert items == []
    assert exhausted is True
    assert backfill_service.call_count == 1  # gave up immediately, has_more=False means no history exists at all


def test_passes_cursor_through_to_feed_queries():
    feed_queries = FakeFeedQueries(pages=[[_item()]])
    backfill_service = FakeBackfillService(results=[])
    service = FeedLoadOlderService(feed_queries, backfill_service)

    service.load_older(["AAPL"], before=datetime(2026, 9, 1, tzinfo=timezone.utc), before_id="xyz")
