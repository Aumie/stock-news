from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from application.watchlist_service import WatchlistService
from infrastructure.finnhub_lookup import InvalidSymbolError
from presentation.auth_dependency import require_auth


class AddSymbolRequest(BaseModel):
    symbol: str


class WatchlistEntryResponse(BaseModel):
    symbol: str
    added_at: str


def build_watchlist_router(service: WatchlistService, secret: str) -> APIRouter:
    router = APIRouter()

    @router.get("/watchlist", response_model=list[WatchlistEntryResponse])
    def list_watchlist(user_id: str = require_auth(secret=secret)):
        return [
            WatchlistEntryResponse(symbol=entry.symbol, added_at=entry.added_at.isoformat())
            for entry in service.list_symbols(user_id)
        ]

    @router.post("/watchlist", status_code=201, response_model=WatchlistEntryResponse)
    def add_to_watchlist(request: AddSymbolRequest, user_id: str = require_auth(secret=secret)):
        try:
            entry = service.add_symbol(user_id, request.symbol)
        except InvalidSymbolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return WatchlistEntryResponse(symbol=entry.symbol, added_at=entry.added_at.isoformat())

    @router.delete("/watchlist/{symbol}", status_code=204)
    def remove_from_watchlist(symbol: str, user_id: str = require_auth(secret=secret)):
        service.remove_symbol(user_id, symbol)
        return Response(status_code=204)

    return router
