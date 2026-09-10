from __future__ import annotations

from typing import Iterable, Iterator, Protocol

from domain.retrieval import RetrievedChunk

NO_NEWS_MESSAGE = "I don't have any news on that for your watchlist right now."

_SYSTEM_PROMPT = (
    "You are a financial news assistant. Answer only using the retrieved article "
    "excerpts below. If the excerpts don't contain enough information to answer, "
    "say so plainly rather than speculating — insufficient grounding must never be "
    "filled in with a plausible-sounding guess. Each excerpt is labeled with its "
    "source, publish date, and headline, and a URL when one is available. If asked "
    "for a link to an article, give the exact URL from that excerpt's label — never "
    "invent, alter, or guess a URL. If the excerpt you're citing has no URL, say so "
    "instead of making one up. For questions about timing (e.g. whether news is "
    "recent, consecutive, or from a particular period), use each excerpt's labeled "
    "publish date directly."
)


class Retriever(Protocol):
    def retrieve(self, symbols: list[str], question: str) -> list[RetrievedChunk]: ...


class LLM(Protocol):
    def stream(self, prompt: str) -> Iterable[str]: ...


class QueryService:
    def __init__(self, retriever: Retriever, llm: LLM) -> None:
        self._retriever = retriever
        self._llm = llm

    def answer(self, symbols: list[str], question: str) -> Iterator[str]:
        chunks = self._retriever.retrieve(symbols, question)
        if not chunks:
            yield NO_NEWS_MESSAGE
            return

        prompt = self._build_prompt(chunks, question)
        yield from self._llm.stream(prompt)

    def _build_prompt(self, chunks: list[RetrievedChunk], question: str) -> str:
        excerpts = "\n\n".join(
            f"[{chunk.source}, published {chunk.published_at.isoformat()}] "
            f"{chunk.headline} ({chunk.canonical_url or 'no URL available'})\n{chunk.chunk_text}"
            for chunk in chunks
        )
        return f"{_SYSTEM_PROMPT}\n\nRetrieved excerpts:\n{excerpts}\n\nQuestion: {question}"
