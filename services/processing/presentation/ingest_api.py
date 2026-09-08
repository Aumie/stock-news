from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from application.process_article import ProcessArticleUseCase
from domain.article import Article


class IngestRequest(BaseModel):
    source: str
    headline: str
    published_at: datetime
    content: str
    symbol: str
    canonical_url: str | None = None


class IngestResponse(BaseModel):
    article_id: str


def build_ingest_router(use_case: ProcessArticleUseCase) -> APIRouter:
    router = APIRouter()

    @router.post("/articles/ingest", response_model=IngestResponse)
    def ingest(request: IngestRequest):
        # Direct synchronous call into the same dedup/embed pipeline
        # /pubsub/push uses — deliberately not routed through Pub/Sub. The
        # queue exists to decouple the poller's unbounded async arrivals
        # from processing; a backfill request is synchronous and
        # user-initiated (query-api's caller is waiting for a response and
        # a count of what was actually new), which doesn't need that
        # decoupling (decision_log.md).
        article = Article(
            source=request.source,
            headline=request.headline,
            published_at=request.published_at,
            content=request.content,
            canonical_url=request.canonical_url,
        )
        article_id = use_case.process(article, symbol=request.symbol)
        return IngestResponse(article_id=article_id)

    return router
