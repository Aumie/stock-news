from __future__ import annotations

import httpx
import structlog
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine

from application.query_service import QueryService
from application.watchlist_service import WatchlistService
from infrastructure.backfill_dependencies import build_backfill_service
from infrastructure.celery_app import celery_app
from infrastructure.celery_backfill_queue import CeleryBackfillQueue
from infrastructure.feed_queries import FeedQueries
from infrastructure.finnhub_lookup import FinnhubSymbolLookup
from infrastructure.llm_client import AnthropicLLMClient
from infrastructure.logging import configure_logging
from infrastructure.pgvector_search import PgVectorRetriever
from infrastructure.postgres_backfill_repo import PostgresBackfillProgressRepo
from infrastructure.postgres_watchlist_repo import PostgresWatchlistRepository
from infrastructure.settings import DEFAULT_JWT_SIGNING_SECRET, Settings
from infrastructure.stats_queries import StatsQueries
from infrastructure.stub_llm import StubLLMClient
from presentation.feed_api import build_feed_router
from presentation.query_api import build_query_router
from presentation.stats_api import build_stats_router
from presentation.watchlist_api import build_watchlist_router

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

app = FastAPI(title="query-api")

_engine = create_engine(settings.database_url)
_embedder = SentenceTransformer(settings.embedding_model)

if settings.jwt_signing_secret == DEFAULT_JWT_SIGNING_SECRET:
    logger.warning(
        "JWT_SIGNING_SECRET is unset — using the well-known dev default. "
        "This allows anyone who has read this source to forge a valid JWT for any user."
    )

if settings.anthropic_api_key:
    _llm = AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.llm_model)
else:
    logger.warning("ANTHROPIC_API_KEY not set — using stub LLM, no real answers will be generated")
    _llm = StubLLMClient()

_query_service = QueryService(retriever=PgVectorRetriever(_engine, _embedder), llm=_llm)

_finnhub_http_client = httpx.Client(timeout=10.0)

# Still built here (not just in the Celery worker) — POST /feed/backfill-more
# is a separate, already-existing manual per-symbol backfill primitive that
# stays synchronous (a direct, deliberate user action reporting a real
# count back), unlike watchlist-add and /feed/load-older, both of which now
# enqueue a background task instead of blocking the request on however long
# Finnhub takes (decision_log.md).
_backfill_service = build_backfill_service(settings)
_backfill_queue = CeleryBackfillQueue(celery_app)

_watchlist_service = WatchlistService(
    repo=PostgresWatchlistRepository(_engine),
    lookup=FinnhubSymbolLookup(http_client=_finnhub_http_client, api_key=settings.finnhub_api_key),
    backfill_queue=_backfill_queue,
)

app.include_router(
    build_watchlist_router(
        _watchlist_service,
        secret=settings.jwt_signing_secret,
        backfill_progress_repo=PostgresBackfillProgressRepo(_engine),
    )
)
app.include_router(build_query_router(_query_service, _watchlist_service, secret=settings.jwt_signing_secret))
app.include_router(
    build_feed_router(
        FeedQueries(_engine),
        _watchlist_service,
        secret=settings.jwt_signing_secret,
        backfill_service=_backfill_service,
        backfill_queue=_backfill_queue,
    )
)
app.include_router(build_stats_router(StatsQueries(_engine), _watchlist_service, secret=settings.jwt_signing_secret))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
