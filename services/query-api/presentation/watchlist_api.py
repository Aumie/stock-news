from __future__ import annotations

from typing import Protocol

import structlog
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from application.watchlist_service import WatchlistService
from infrastructure.finnhub_lookup import InvalidSymbolError, SymbolLookupUnavailableError
from presentation.auth_dependency import require_auth

logger = structlog.get_logger()


class BackfillProgressReader(Protocol):
    def get_earliest_backfilled(self, symbol: str) -> object: ...


class AddSymbolRequest(BaseModel):
    symbol: str


class WatchlistEntryResponse(BaseModel):
    symbol: str
    added_at: str
    # True until the symbol's news backfill (a background Celery task,
    # decision_log.md) has actually landed — a symbol_backfill_progress row
    # only exists once that succeeds. Lets the UI show an honest "still
    # backfilling" state instead of a newly-added symbol looking silently
    # empty/incomplete with no explanation (user request: "shouldnt we have
    # some msg to tell that the newly ingested will appear in a moment?").
    backfill_pending: bool


def build_watchlist_router(
    service: WatchlistService, secret: str, backfill_progress_repo: BackfillProgressReader | None = None
) -> APIRouter:
    router = APIRouter()

    def _is_backfill_pending(symbol: str) -> bool:
        if backfill_progress_repo is None:
            return False
        return backfill_progress_repo.get_earliest_backfilled(symbol) is None

    @router.get("/watchlist", response_model=list[WatchlistEntryResponse])
    def list_watchlist(user_id: str = require_auth(secret=secret)):
        return [
            WatchlistEntryResponse(
                symbol=entry.symbol,
                added_at=entry.added_at.isoformat(),
                backfill_pending=_is_backfill_pending(entry.symbol),
            )
            for entry in service.list_symbols(user_id)
        ]

    @router.post("/watchlist", status_code=201, response_model=WatchlistEntryResponse)
    def add_to_watchlist(request: AddSymbolRequest, user_id: str = require_auth(secret=secret)):
        try:
            entry = service.add_symbol(user_id, request.symbol)
        except InvalidSymbolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SymbolLookupUnavailableError as exc:
            # Distinct from InvalidSymbolError (422): Finnhub itself didn't
            # answer, the symbol's validity is simply unknown right now — a
            # real 503 from Finnhub used to crash this as an unhandled 500
            # (decision_log.md). Logged at warning level (not silently
            # swallowed) — a real gap found live: the first version of this
            # handler returned 503 with no log line at all, making a
            # genuine bug indistinguishable from real Finnhub flakiness.
            logger.warning("watchlist_api.symbol_lookup_unavailable", symbol=request.symbol, error=str(exc))
            raise HTTPException(
                status_code=503, detail="Symbol validation is temporarily unavailable — try again shortly."
            ) from exc
        # Always pending immediately after a fresh add — the backfill task
        # was just enqueued, not run yet.
        return WatchlistEntryResponse(symbol=entry.symbol, added_at=entry.added_at.isoformat(), backfill_pending=True)

    @router.delete("/watchlist/{symbol}", status_code=204)
    def remove_from_watchlist(symbol: str, user_id: str = require_auth(secret=secret)):
        service.remove_symbol(user_id, symbol)
        return Response(status_code=204)

    return router
