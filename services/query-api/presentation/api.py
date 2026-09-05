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
from infrastructure.settings import Settings
from infrastructure.stub_llm import StubLLMClient

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

app = FastAPI(title="query-api")

_engine = create_engine(settings.database_url)
_embedder = SentenceTransformer(settings.embedding_model)

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
def query(request: QueryRequest) -> StreamingResponse:
    logger.info("query received", symbols=request.symbols)
    return StreamingResponse(
        _query_service.answer(symbols=request.symbols, question=request.question),
        media_type="text/plain",
    )
