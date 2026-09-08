from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

import httpx
import structlog

from domain.backfill import BackfillResult, MultiSymbolBackfillResult, SymbolBackfillResult
from infrastructure.finnhub_news_client import NewsArticle

logger = structlog.get_logger()

BACKFILL_WINDOW_DAYS = 30

# Finnhub's company-news endpoint doesn't reliably serve a single 30-day
# request for a busy symbol — confirmed live: INTC over 30 days times out
# past 60s, while 14 days reliably returns in ~9s (decision_log.md). Each
# Finnhub call is capped at this width; a wider total window is fetched as
# multiple sequential chunks instead of widening the single request.
FETCH_CHUNK_DAYS = 14


class NewsClient(Protocol):
    def fetch_company_news(self, symbol: str, from_date: date, to_date: date) -> list[NewsArticle]: ...


class IngestClient(Protocol):
    def ingest(self, article: NewsArticle, symbol: str) -> str: ...


class BackfillProgressRepo(Protocol):
    def get_earliest_backfilled(self, symbol: str) -> date | None: ...
    def set_earliest_backfilled(self, symbol: str, earliest: date) -> None: ...


class Clock(Protocol):
    def today(self) -> date: ...


class BackfillService:
    def __init__(
        self,
        news_client: NewsClient,
        ingest_client: IngestClient,
        progress_repo: BackfillProgressRepo,
        clock: Clock,
    ) -> None:
        self._news_client = news_client
        self._ingest_client = ingest_client
        self._progress_repo = progress_repo
        self._clock = clock

    def backfill_on_add(self, symbol: str) -> BackfillResult:
        # Symbol-scoped, not per-user (matches the v2 OHLCV backfill design's
        # "shared, not duplicated" philosophy, decision_log.md) — if the
        # symbol was already backfilled by an earlier watcher, don't
        # re-fetch the same window again; report it as a no-op with the
        # already-known range rather than silently repeating work.
        existing = self._progress_repo.get_earliest_backfilled(symbol)
        if existing is not None:
            return BackfillResult(articles_fetched=0, from_date=existing, to_date=existing, has_more=True)

        to_date = self._clock.today()
        from_date = to_date - timedelta(days=BACKFILL_WINDOW_DAYS)
        return self._run_backfill(symbol, from_date, to_date)

    def load_more(self, symbol: str) -> BackfillResult:
        # A symbol can be watched with no backfill history at all — e.g. it
        # was on a watchlist before this feature existed, or was added
        # through a path other than backfill_on_add — so "no prior backfill"
        # is a real, normal state, not an error condition. Treat it the same
        # as a first-ever backfill (today - BACKFILL_WINDOW_DAYS) instead of raising: a
        # real 400 from this used to crash the whole watchlist page for any
        # pre-existing watched symbol (decision_log_claude.md).
        earliest = self._progress_repo.get_earliest_backfilled(symbol)
        if earliest is None:
            to_date = self._clock.today()
        else:
            to_date = earliest

        from_date = to_date - timedelta(days=BACKFILL_WINDOW_DAYS)
        return self._run_backfill(symbol, from_date, to_date)

    def load_more_for_symbols(self, symbols: list[str]) -> MultiSymbolBackfillResult:
        # Live Feed's single "Load 2 more weeks" button applies to every
        # watched symbol at once, not one symbol at a time — loops over
        # load_more() (which already handles the never-backfilled case
        # gracefully) and reports a combined result.
        per_symbol = [SymbolBackfillResult(symbol=symbol, result=self.load_more(symbol)) for symbol in symbols]
        return MultiSymbolBackfillResult(per_symbol=per_symbol)

    def _run_backfill(self, symbol: str, from_date: date, to_date: date) -> BackfillResult:
        # Fetched as sequential chunks, not one call for the whole range —
        # see FETCH_CHUNK_DAYS. Chunked from the newest end backward so a
        # partial failure still leaves the most recent, most relevant news
        # ingested rather than the oldest.
        #
        # Each chunk's Finnhub call is best-effort, not all-or-nothing: live
        # testing found Finnhub's company-news endpoint genuinely unreliable
        # under repeated calls (a real symbol timed out on every one of 4
        # sequential requests despite succeeding in isolation seconds
        # earlier, decision_log.md) — a slow/failed chunk must not turn
        # "add a symbol" into a 500 for the whole watchlist, since the
        # symbol itself is unaffected by Finnhub's flakiness and the failed
        # chunk's news simply won't be there yet (a later "load more" click
        # can still retry that range).
        total_articles = 0
        any_chunk_succeeded = False
        chunk_to = to_date
        while chunk_to > from_date:
            chunk_from = max(from_date, chunk_to - timedelta(days=FETCH_CHUNK_DAYS))
            try:
                articles = self._news_client.fetch_company_news(symbol, from_date=chunk_from, to_date=chunk_to)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                logger.warning(
                    "backfill_service.chunk_failed",
                    symbol=symbol,
                    from_date=chunk_from.isoformat(),
                    to_date=chunk_to.isoformat(),
                    error=str(exc),
                )
                chunk_to = chunk_from
                continue
            any_chunk_succeeded = True
            for article in articles:
                self._ingest_client.ingest(article, symbol=symbol)
            total_articles += len(articles)
            chunk_to = chunk_from

        # Only record progress once Finnhub was genuinely reached at least
        # once — a symbol whose every chunk failed must stay "not
        # backfilled" so a later add or load-more retries it for real,
        # rather than getting permanently stuck on the no-op path above
        # (real bug found live: GOOG's only attempt fully failed, but
        # progress was recorded anyway, so re-adding it after a remove
        # silently skipped fetching entirely, decision_log.md).
        if any_chunk_succeeded:
            self._progress_repo.set_earliest_backfilled(symbol, from_date)

        return BackfillResult(
            articles_fetched=total_articles,
            from_date=from_date,
            to_date=to_date,
            has_more=total_articles > 0,
        )
