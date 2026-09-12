from __future__ import annotations

import httpx
import structlog
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, inspect

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
from presentation.internal_api import build_internal_router
from presentation.query_api import build_query_router
from presentation.stats_api import build_stats_router
from presentation.watchlist_api import build_watchlist_router

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

app = FastAPI(title="query-api")

# pool_pre_ping: this project's Postgres container gets restarted often
# enough in local dev (Docker Desktop instability, manual restarts to clear
# other issues) that a long-lived process here would otherwise hold a dead
# connection and surface it as a raw 500 (psycopg.errors.AdminShutdown) on
# whatever request happened to use it next — hit live, repeatedly, across
# this project's session history (decision_log_claude.md). pre_ping tests
# each pooled connection with a cheap query before handing it to a request,
# transparently reconnecting instead of failing the request.
_engine = create_engine(settings.database_url, pool_pre_ping=True)
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

_stats_queries = StatsQueries(_engine)
_query_service = QueryService(retriever=PgVectorRetriever(_engine, _embedder), llm=_llm, aggregate_queries=_stats_queries)

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
app.include_router(build_stats_router(_stats_queries, _watchlist_service, secret=settings.jwt_signing_secret))
app.include_router(build_internal_router(_backfill_queue))


@app.on_event("startup")
def _trigger_sweep_if_daily_symbol_features_missing() -> None:
    # Real recurring gap found live: celery-beat's own beat_init hook
    # already self-heals a missing daily_symbol_features table on its own
    # startup (celery_app.py), but that only covers celery-beat restarting —
    # query-api coming up on its own (a plain redeploy, or celery-beat
    # staying up the whole time while Postgres/the table got wiped
    # underneath it) left Stats stuck on "No data yet" with nothing to
    # notice (decision_log_claude.md: this table went missing repeatedly
    # this session after every Docker Desktop event). Checking here too
    # means the check runs wherever the app actually starts, not just one
    # specific process.
    if not inspect(_engine).has_table("daily_symbol_features"):
        logger.warning("api.daily_symbol_features_missing_on_startup — enqueuing a sweep to rebuild it")
        _backfill_queue.enqueue_daily_batch_sweep()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
