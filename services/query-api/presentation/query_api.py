from __future__ import annotations

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from application.query_service import QueryService
from application.watchlist_service import WatchlistService
from presentation.auth_dependency import require_auth

logger = structlog.get_logger()


class QueryRequest(BaseModel):
    question: str


def build_query_router(query_service: QueryService, watchlist_service: WatchlistService, secret: str) -> APIRouter:
    router = APIRouter()

    @router.post("/query")
    def query(request: QueryRequest, user_id: str = require_auth(secret=secret)) -> StreamingResponse:
        # Symbols are the caller's own watchlist, not client-supplied (§4.1,
        # api-spec.md's "milestone 1/2 shape, temporary" note) — a request
        # can no longer ask about a symbol it doesn't watch.
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        logger.info("query received", symbols=symbols, user_id=user_id)
        return StreamingResponse(
            query_service.answer(symbols=symbols, question=request.question),
            media_type="text/plain",
        )

    return router
