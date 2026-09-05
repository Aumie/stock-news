from __future__ import annotations

import structlog
from fastapi import FastAPI
from sqlalchemy import create_engine

from application.process_article import ProcessArticleUseCase
from infrastructure.chunking import FixedSizeChunker
from infrastructure.embedding_writer import PostgresEmbeddingWriter
from infrastructure.embeddings import SentenceTransformerEmbedder
from infrastructure.logging import configure_logging
from infrastructure.postgres_repo import PostgresArticleRepository
from infrastructure.pubsub import PubSubPushEnvelope, parse_push_envelope
from infrastructure.settings import Settings

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

app = FastAPI(title="processing")

_engine = create_engine(settings.database_url)
_use_case = ProcessArticleUseCase(
    repo=PostgresArticleRepository(_engine),
    chunker=FixedSizeChunker(),
    embedder=SentenceTransformerEmbedder(settings.embedding_model),
    embedding_writer=PostgresEmbeddingWriter(_engine),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pubsub/push")
def pubsub_push(envelope: PubSubPushEnvelope) -> dict[str, str]:
    article, symbol = parse_push_envelope(envelope)
    article_id = _use_case.process(article, symbol=symbol)
    logger.info("processed article", article_id=article_id, symbol=symbol, source=article.source)
    return {"status": "ok", "article_id": article_id}
