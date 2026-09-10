from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel


class NewsIngestedQueue(Protocol):
    def enqueue_symbol_news_ingested(self, symbol: str) -> None: ...


class SymbolNewsIngestedRequest(BaseModel):
    symbol: str


def build_internal_router(queue: NewsIngestedQueue) -> APIRouter:
    # Service-to-service only, no per-user JWT (require_auth is for
    # end-user requests) — processing calls this after every successful
    # ingest, not a browser. Locally this relies on the same "not exposed
    # outside the Docker network" boundary /health does; the cloud target
    # needs its own IAM lock (only processing's service account can invoke
    # it), same as every other inter-service call in api-spec.md — not yet
    # built, called out here rather than silently assumed.
    router = APIRouter(prefix="/internal")

    @router.post("/symbol-news-ingested", status_code=202)
    def symbol_news_ingested(request: SymbolNewsIngestedRequest) -> dict[str, str]:
        queue.enqueue_symbol_news_ingested(request.symbol)
        return {"status": "accepted"}

    return router
