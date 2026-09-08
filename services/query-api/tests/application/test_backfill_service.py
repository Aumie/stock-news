from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from application.backfill_service import BackfillService
from infrastructure.finnhub_news_client import NewsArticle

TODAY = date(2026, 9, 20)


class FakeClock:
    def today(self) -> date:
        return TODAY


class FakeNewsClient:
    def __init__(
        self,
        articles_by_range: dict[tuple[date, date], list[NewsArticle]],
        failing_ranges: set[tuple[date, date]] | None = None,
    ):
        self._articles_by_range = articles_by_range
        self._failing_ranges = failing_ranges or set()
        self.calls: list[tuple[date, date]] = []

    def fetch_company_news(self, symbol: str, from_date: date, to_date: date) -> list[NewsArticle]:
        self.calls.append((from_date, to_date))
        if (from_date, to_date) in self._failing_ranges:
            raise httpx.ReadTimeout("simulated Finnhub timeout")
        return self._articles_by_range.get((from_date, to_date), [])


class FakeIngestClient:
    def __init__(self, new_article_ids: list[str] | None = None):
        self.ingested: list[tuple[NewsArticle, str]] = []
        self._new_article_ids = new_article_ids

    def ingest(self, article: NewsArticle, symbol: str) -> str:
        self.ingested.append((article, symbol))
        idx = len(self.ingested) - 1
        if self._new_article_ids is not None:
            return self._new_article_ids[idx]
        return f"id-{idx}"


class FakeProgressRepo:
    def __init__(self):
        self.progress: dict[str, date] = {}

    def get_earliest_backfilled(self, symbol: str) -> date | None:
        return self.progress.get(symbol)

    def set_earliest_backfilled(self, symbol: str, earliest: date) -> None:
        self.progress[symbol] = earliest


def _article(headline="h", published_at=None) -> NewsArticle:
    return NewsArticle(
        headline=headline,
        summary="s",
        source="finnhub",
        url=f"https://example.com/{headline}",
        published_at=published_at or datetime(2026, 9, 15, tzinfo=timezone.utc),
    )


# A 30-day range is fetched as three sequential <=14-day chunks, newest
# first — Finnhub's company-news endpoint doesn't reliably serve a single
# 30-day request for a busy symbol (confirmed live: a real 60s+ timeout for
# INTC at 30 days, a reliable ~9s response at 14 days, decision_log.md).
CHUNK_1 = (TODAY - timedelta(days=14), TODAY)
CHUNK_2 = (TODAY - timedelta(days=28), TODAY - timedelta(days=14))
CHUNK_3 = (TODAY - timedelta(days=30), TODAY - timedelta(days=28))


def test_first_backfill_fetches_last_30_days_as_three_chunks():
    news_client = FakeNewsClient({CHUNK_1: [_article("a")], CHUNK_2: [_article("b")], CHUNK_3: [_article("c")]})
    ingest_client = FakeIngestClient()
    progress_repo = FakeProgressRepo()
    service = BackfillService(news_client, ingest_client, progress_repo, clock=FakeClock())

    result = service.backfill_on_add("AAPL")

    assert news_client.calls == [CHUNK_1, CHUNK_2, CHUNK_3]
    assert result.from_date == TODAY - timedelta(days=30)
    assert result.to_date == TODAY
    assert result.articles_fetched == 3
    assert progress_repo.get_earliest_backfilled("AAPL") == TODAY - timedelta(days=30)


def test_first_backfill_ingests_every_article_across_all_chunks():
    news_client = FakeNewsClient(
        {CHUNK_1: [_article("a"), _article("b")], CHUNK_2: [_article("c")], CHUNK_3: []}
    )
    ingest_client = FakeIngestClient()
    service = BackfillService(news_client, ingest_client, FakeProgressRepo(), clock=FakeClock())

    service.backfill_on_add("AAPL")

    assert [symbol for _, symbol in ingest_client.ingested] == ["AAPL", "AAPL", "AAPL"]
    assert [a.headline for a, _ in ingest_client.ingested] == ["a", "b", "c"]


def test_load_more_extends_backward_from_earliest_backfilled_as_chunks():
    earliest_so_far = TODAY - timedelta(days=30)
    chunk_1 = (earliest_so_far - timedelta(days=14), earliest_so_far)
    chunk_2 = (earliest_so_far - timedelta(days=28), earliest_so_far - timedelta(days=14))
    chunk_3 = (earliest_so_far - timedelta(days=30), earliest_so_far - timedelta(days=28))
    news_client = FakeNewsClient({chunk_1: [_article()], chunk_2: [], chunk_3: []})
    progress_repo = FakeProgressRepo()
    progress_repo.set_earliest_backfilled("AAPL", earliest_so_far)
    service = BackfillService(news_client, FakeIngestClient(), progress_repo, clock=FakeClock())

    result = service.load_more("AAPL")

    assert news_client.calls == [chunk_1, chunk_2, chunk_3]
    assert result.from_date == earliest_so_far - timedelta(days=30)
    assert result.to_date == earliest_so_far
    assert progress_repo.get_earliest_backfilled("AAPL") == earliest_so_far - timedelta(days=30)


def test_load_more_with_no_prior_backfill_runs_an_initial_30day_backfill_instead_of_raising():
    # Real bug found live: NVDA was on a real user's watchlist from before
    # this feature existed (added via a path other than POST /watchlist), so
    # it had no symbol_backfill_progress row. Clicking "Load 2 more weeks"
    # crashed the whole Streamlit page with a raw 400/ValueError instead of
    # just doing the first backfill it never got (decision_log_claude.md).
    news_client = FakeNewsClient({CHUNK_1: [_article()], CHUNK_2: [], CHUNK_3: []})
    service = BackfillService(news_client, FakeIngestClient(), FakeProgressRepo(), clock=FakeClock())

    result = service.load_more("NEVERBACKFILLED")

    assert news_client.calls == [CHUNK_1, CHUNK_2, CHUNK_3]
    assert result.from_date == TODAY - timedelta(days=30)
    assert result.to_date == TODAY
    assert result.articles_fetched == 1


def test_has_more_is_false_when_finnhub_returns_no_articles_in_any_chunk():
    earliest_so_far = TODAY - timedelta(days=30)
    chunk_1 = (earliest_so_far - timedelta(days=14), earliest_so_far)
    chunk_2 = (earliest_so_far - timedelta(days=28), earliest_so_far - timedelta(days=14))
    chunk_3 = (earliest_so_far - timedelta(days=30), earliest_so_far - timedelta(days=28))
    news_client = FakeNewsClient({chunk_1: [], chunk_2: [], chunk_3: []})
    progress_repo = FakeProgressRepo()
    progress_repo.set_earliest_backfilled("AAPL", earliest_so_far)
    service = BackfillService(news_client, FakeIngestClient(), progress_repo, clock=FakeClock())

    result = service.load_more("AAPL")

    assert result.has_more is False
    assert result.articles_fetched == 0


def test_has_more_is_true_when_any_chunk_returns_articles():
    news_client = FakeNewsClient({CHUNK_1: [], CHUNK_2: [_article()], CHUNK_3: []})
    service = BackfillService(news_client, FakeIngestClient(), FakeProgressRepo(), clock=FakeClock())

    result = service.backfill_on_add("AAPL")

    assert result.has_more is True


def test_backfill_on_add_is_a_no_op_when_symbol_already_backfilled_by_another_watcher():
    # Symbol-scoped, not per-user (decision_log.md) — a second user adding
    # the same symbol shouldn't trigger a duplicate Finnhub fetch.
    news_client = FakeNewsClient({CHUNK_1: [_article()], CHUNK_2: [], CHUNK_3: []})
    ingest_client = FakeIngestClient()
    progress_repo = FakeProgressRepo()
    progress_repo.set_earliest_backfilled("AAPL", TODAY - timedelta(days=30))
    service = BackfillService(news_client, ingest_client, progress_repo, clock=FakeClock())

    result = service.backfill_on_add("AAPL")

    assert news_client.calls == []
    assert ingest_client.ingested == []
    assert result.articles_fetched == 0


def test_load_more_for_symbols_calls_load_more_once_per_symbol():
    aapl_chunk_1 = (TODAY - timedelta(days=14), TODAY)
    aapl_chunk_2 = (TODAY - timedelta(days=28), TODAY - timedelta(days=14))
    aapl_chunk_3 = (TODAY - timedelta(days=30), TODAY - timedelta(days=28))
    msft_earliest = TODAY - timedelta(days=30)
    msft_chunk_1 = (msft_earliest - timedelta(days=14), msft_earliest)
    msft_chunk_2 = (msft_earliest - timedelta(days=28), msft_earliest - timedelta(days=14))
    msft_chunk_3 = (msft_earliest - timedelta(days=30), msft_earliest - timedelta(days=28))
    news_client = FakeNewsClient(
        {
            aapl_chunk_1: [_article("aapl-news")],
            aapl_chunk_2: [],
            aapl_chunk_3: [],
            msft_chunk_1: [_article("msft-news-1")],
            msft_chunk_2: [_article("msft-news-2")],
            msft_chunk_3: [],
        }
    )
    progress_repo = FakeProgressRepo()
    progress_repo.set_earliest_backfilled("MSFT", msft_earliest)
    service = BackfillService(news_client, FakeIngestClient(), progress_repo, clock=FakeClock())

    result = service.load_more_for_symbols(["AAPL", "MSFT"])

    symbols_seen = [r.symbol for r in result.per_symbol]
    assert symbols_seen == ["AAPL", "MSFT"]
    assert result.total_articles_fetched == 3


def test_load_more_for_symbols_with_empty_list_is_a_no_op():
    service = BackfillService(FakeNewsClient({}), FakeIngestClient(), FakeProgressRepo(), clock=FakeClock())

    result = service.load_more_for_symbols([])

    assert result.per_symbol == []
    assert result.total_articles_fetched == 0


def test_a_failed_chunk_does_not_raise_and_other_chunks_still_run():
    # Real bug found live: Finnhub's company-news endpoint timed out on every
    # one of 4 sequential requests despite succeeding in isolation seconds
    # earlier — a flaky external API, not something fixable by changing the
    # request shape further. A failed chunk must be skipped, not crash the
    # whole add-symbol request with a 500 (decision_log.md).
    news_client = FakeNewsClient(
        {CHUNK_1: [_article("a")], CHUNK_3: [_article("c")]},
        failing_ranges={CHUNK_2},
    )
    service = BackfillService(news_client, FakeIngestClient(), FakeProgressRepo(), clock=FakeClock())

    result = service.backfill_on_add("AAPL")  # does not raise

    assert news_client.calls == [CHUNK_1, CHUNK_2, CHUNK_3]
    assert result.articles_fetched == 2  # chunk_1's "a" + chunk_3's "c", chunk_2 skipped
    assert result.from_date == TODAY - timedelta(days=30)


def test_progress_is_not_recorded_when_every_chunk_fails():
    # Real bug found live: a symbol (GOOG) whose only backfill attempt had
    # every chunk fail against Finnhub still got marked "backfilled" —
    # backfill_on_add's no-op check (existing is not None) then treated any
    # later re-add as already handled by another watcher and skipped
    # fetching entirely, permanently stranding the symbol with zero articles
    # and no automatic way to retry (decision_log.md). Progress must only be
    # recorded once at least one chunk genuinely succeeded, even if that
    # chunk returned zero real articles — reachability, not article count,
    # is what "successfully attempted" means here.
    news_client = FakeNewsClient({}, failing_ranges={CHUNK_1, CHUNK_2, CHUNK_3})
    progress_repo = FakeProgressRepo()
    service = BackfillService(news_client, FakeIngestClient(), progress_repo, clock=FakeClock())

    result = service.backfill_on_add("AAPL")  # does not raise

    assert result.articles_fetched == 0
    assert result.has_more is False
    assert progress_repo.get_earliest_backfilled("AAPL") is None


def test_progress_is_recorded_when_at_least_one_chunk_succeeds_even_with_zero_articles():
    # A chunk that reaches Finnhub and genuinely finds no news (not a
    # failure) is still a successful attempt — the symbol just has no
    # recent coverage, which is a real, legitimate outcome, not a reason to
    # retry indefinitely on every future add.
    news_client = FakeNewsClient({CHUNK_1: []}, failing_ranges={CHUNK_2, CHUNK_3})
    progress_repo = FakeProgressRepo()
    service = BackfillService(news_client, FakeIngestClient(), progress_repo, clock=FakeClock())

    result = service.backfill_on_add("AAPL")

    assert result.articles_fetched == 0
    assert progress_repo.get_earliest_backfilled("AAPL") == TODAY - timedelta(days=30)


def test_backfill_on_add_retries_a_symbol_whose_prior_attempt_fully_failed():
    # Direct regression test for the reported bug: GOOG was removed and
    # re-added after its only backfill attempt had every chunk fail. With no
    # progress row left behind by that failed attempt, re-adding must
    # genuinely retry the fetch, not silently no-op as "already backfilled."
    news_client = FakeNewsClient({CHUNK_1: [_article("goog-news")], CHUNK_2: [], CHUNK_3: []})
    ingest_client = FakeIngestClient()
    progress_repo = FakeProgressRepo()  # empty — the failed attempt left no progress row
    service = BackfillService(news_client, ingest_client, progress_repo, clock=FakeClock())

    result = service.backfill_on_add("GOOG")

    assert news_client.calls == [CHUNK_1, CHUNK_2, CHUNK_3]
    assert result.articles_fetched == 1
    assert ingest_client.ingested != []
    assert progress_repo.get_earliest_backfilled("GOOG") == TODAY - timedelta(days=30)
