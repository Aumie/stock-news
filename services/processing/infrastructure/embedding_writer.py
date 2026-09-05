from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PostgresEmbeddingWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, article_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        with self._engine.begin() as conn:
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                conn.execute(
                    text(
                        """
                        INSERT INTO embeddings (article_id, chunk_index, vector, chunk_text)
                        VALUES (:article_id, :chunk_index, :vector, :chunk_text)
                        ON CONFLICT (article_id, chunk_index) DO NOTHING
                        """
                    ),
                    {
                        "article_id": article_id,
                        "chunk_index": index,
                        "vector": str(vector),
                        "chunk_text": chunk,
                    },
                )
