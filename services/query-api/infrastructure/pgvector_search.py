from __future__ import annotations

from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.retrieval import RetrievedChunk


class PgVectorRetriever:
    def __init__(self, engine: Engine, embedder: SentenceTransformer, top_k: int = 5) -> None:
        self._engine = engine
        self._embedder = embedder
        self._top_k = top_k

    def retrieve(self, symbols: list[str], question: str) -> list[RetrievedChunk]:
        if not symbols:
            return []

        query_vector = self._embedder.encode(question, convert_to_numpy=True).tolist()
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        e.article_id, e.chunk_text, a.source, a.headline,
                        1 - (e.vector <=> :query_vector) AS score
                    FROM embeddings e
                    JOIN articles a ON a.id = e.article_id
                    JOIN article_symbols s ON s.article_id = a.id
                    WHERE s.symbol = ANY(:symbols)
                    ORDER BY e.vector <=> :query_vector
                    LIMIT :top_k
                    """
                ),
                {"query_vector": str(query_vector), "symbols": symbols, "top_k": self._top_k},
            ).fetchall()

        return [
            RetrievedChunk(
                article_id=str(row.article_id),
                chunk_text=row.chunk_text,
                source=row.source,
                headline=row.headline,
                score=float(row.score),
            )
            for row in rows
        ]
