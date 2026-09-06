from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


class PostgresEmbeddingWriter:
    """Operates on a Connection passed in by the caller (PostgresUnitOfWork)
    rather than opening its own — lets multiple calls share one transaction.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def write(self, article_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            self._conn.execute(
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
