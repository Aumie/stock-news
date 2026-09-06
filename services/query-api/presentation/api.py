from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine

from application.query_service import QueryService
from infrastructure.llm_client import AnthropicLLMClient
from infrastructure.logging import configure_logging
from infrastructure.pgvector_search import PgVectorRetriever
from infrastructure.settings import DEFAULT_JWT_SIGNING_SECRET, Settings
from infrastructure.stub_llm import StubLLMClient
from presentation.auth_dependency import require_auth

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


class QueryRequest(BaseModel):
    question: str
    symbols: list[str]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
def query(request: QueryRequest, user_id: str = require_auth(secret=settings.jwt_signing_secret)) -> StreamingResponse:
    logger.info("query received", symbols=request.symbols, user_id=user_id)
    return StreamingResponse(
        _query_service.answer(symbols=request.symbols, question=request.question),
        media_type="text/plain",
    )
