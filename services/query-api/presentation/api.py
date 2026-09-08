from __future__ import annotations

import httpx
import structlog
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine

from application.backfill_service import BackfillService
from application.query_service import QueryService
from application.watchlist_service import WatchlistService
from infrastructure.feed_queries import FeedQueries
from infrastructure.finnhub_lookup import FinnhubSymbolLookup
from infrastructure.finnhub_news_client import FinnhubNewsClient
from infrastructure.llm_client import AnthropicLLMClient
from infrastructure.local_docker_job_trigger import LocalDockerJobTrigger
from infrastructure.logging import configure_logging
from infrastructure.pgvector_search import PgVectorRetriever
from infrastructure.postgres_backfill_repo import PostgresBackfillProgressRepo
from infrastructure.postgres_watchlist_repo import PostgresWatchlistRepository
from infrastructure.processing_ingest_client import ProcessingIngestClient
from infrastructure.settings import DEFAULT_JWT_SIGNING_SECRET, Settings
from infrastructure.stats_queries import StatsQueries
from infrastructure.stub_llm import StubLLMClient
from infrastructure.system_clock import SystemClock
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

# 30s, not 10s — shared by the quick /search symbol-validation lookup and
# the company-news backfill fetch, and the latter genuinely got slower once
# the backfill window widened from 14 to 30 days (a real ReadTimeout hit
# live at 10s for a busy symbol, decision_log.md).
_finnhub_http_client = httpx.Client(timeout=30.0)
_processing_http_client = httpx.Client(timeout=30.0)

_backfill_service = BackfillService(
    news_client=FinnhubNewsClient(http_client=_finnhub_http_client, api_key=settings.finnhub_api_key),
    ingest_client=ProcessingIngestClient(http_client=_processing_http_client, base_url=settings.processing_url),
    progress_repo=PostgresBackfillProgressRepo(_engine),
    clock=SystemClock(),
)
if settings.compose_project_name:
    _job_trigger = LocalDockerJobTrigger(project_name=settings.compose_project_name)
else:
    logger.warning(
        "COMPOSE_PROJECT_NAME not set — no job trigger wired, symbols added to a "
        "watchlist won't get an immediate price/feature-store backfill (the daily "
        "sweep will still pick them up)"
    )
    _job_trigger = None

_watchlist_service = WatchlistService(
    repo=PostgresWatchlistRepository(_engine),
    lookup=FinnhubSymbolLookup(http_client=_finnhub_http_client, api_key=settings.finnhub_api_key),
    backfill_service=_backfill_service,
    job_trigger=_job_trigger,
)

app.include_router(build_watchlist_router(_watchlist_service, secret=settings.jwt_signing_secret))
app.include_router(build_query_router(_query_service, _watchlist_service, secret=settings.jwt_signing_secret))
app.include_router(
    build_feed_router(
        FeedQueries(_engine), _watchlist_service, secret=settings.jwt_signing_secret, backfill_service=_backfill_service
    )
)
app.include_router(build_stats_router(StatsQueries(_engine), _watchlist_service, secret=settings.jwt_signing_secret))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
