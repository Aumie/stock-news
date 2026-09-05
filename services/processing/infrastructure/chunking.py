from __future__ import annotations


class FixedSizeChunker:
    """Splits text into overlapping fixed-size character chunks.

    Simple by design for v1 — no sentence/token-aware splitting. Good enough
    for short news articles; revisit if v2's longer-form content needs it.
    """

    def __init__(self, chunk_size: int = 1000, overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self._chunk_size:
            return [text]

        chunks = []
        start = 0
        step = self._chunk_size - self._overlap
        while start < len(text):
            chunks.append(text[start : start + self._chunk_size])
            start += step
        return chunks
