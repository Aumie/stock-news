from __future__ import annotations

import httpx
import structlog
from fastapi import FastAPI
from sqlalchemy import create_engine

from application.process_article import ProcessArticleUseCase
from domain.validation import ArticleValidationError
from infrastructure.chunking import FixedSizeChunker
from infrastructure.dedup_precheck import PostgresDedupPrecheck
from infrastructure.embeddings import SentenceTransformerEmbedder
from infrastructure.logging import configure_logging
from infrastructure.pubsub import PubSubPushEnvelope, parse_push_envelope
from infrastructure.query_api_notifier import QueryApiNotifier
from infrastructure.settings import Settings
from infrastructure.unit_of_work import PostgresUnitOfWork
from presentation.ingest_api import build_ingest_router

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

app = FastAPI(title="processing")

_engine = create_engine(settings.database_url)
_query_api_http_client = httpx.Client(timeout=5.0)
_use_case = ProcessArticleUseCase(
    uow_factory=lambda: PostgresUnitOfWork(_engine),
    dedup_precheck=PostgresDedupPrecheck(_engine),
    chunker=FixedSizeChunker(),
    embedder=SentenceTransformerEmbedder(settings.embedding_model),
    news_ingested_notifier=QueryApiNotifier(http_client=_query_api_http_client, base_url=settings.query_api_url),
)


app.include_router(build_ingest_router(_use_case))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pubsub/push")
def pubsub_push(envelope: PubSubPushEnvelope) -> dict[str, str]:
    article, symbol = parse_push_envelope(envelope)
    try:
        article_id = _use_case.process(article, symbol=symbol)
    except ArticleValidationError as exc:
        # A 2xx tells Pub/Sub not to retry — structurally invalid data
        # (blank headline/content, malformed symbol) will never become
        # valid on redelivery, so retrying would only loop forever instead
        # of ever succeeding. Logged, not silently dropped.
        logger.warning("dropping invalid article from pubsub push", symbol=symbol, error=str(exc))
        return {"status": "dropped", "reason": str(exc)}
    logger.info("processed article", article_id=article_id, symbol=symbol, source=article.source)
    return {"status": "ok", "article_id": article_id}
