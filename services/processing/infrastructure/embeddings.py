from __future__ import annotations

from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbedder:
    """Local, free embeddings — no per-call API cost (decision_log.md, §8)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]
