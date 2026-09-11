from __future__ import annotations

from typing import Iterable, Iterator, Protocol

from application.aggregate_question_detection import is_busiest_symbol_question, is_list_all_articles_question
from domain.retrieval import RetrievedChunk
from domain.stats import ArticleListing, BusiestSymbolDay

NO_NEWS_MESSAGE = "I don't have any news on that for your watchlist right now."
NO_AGGREGATE_DATA_MESSAGE = "I don't have enough article history for your watchlist to answer that yet."

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


class AggregateQueries(Protocol):
    def busiest_symbol_day(self, symbols: list[str]) -> BusiestSymbolDay | None: ...
    def list_articles(self, symbols: list[str]) -> tuple[list[ArticleListing], int]: ...


class LLM(Protocol):
    def stream(self, prompt: str) -> Iterable[str]: ...


class QueryService:
    def __init__(self, retriever: Retriever, llm: LLM, aggregate_queries: AggregateQueries | None = None) -> None:
        self._retriever = retriever
        self._llm = llm
        self._aggregate_queries = aggregate_queries

    def answer(self, symbols: list[str], question: str) -> Iterator[str]:
        # Real gap found live: asked "what symbol have most news in a day?"
        # — RAG's top-k semantic retrieval only pulls the chunks most
        # relevant to the question text, it can never answer a genuine
        # aggregate/count across the whole watchlist's history. Routed to a
        # real SQL aggregate instead of vector retrieval for this narrow
        # class of question, rather than asking the LLM to guess at a count
        # it was never given (decision_log_claude.md).
        if self._aggregate_queries is not None and is_busiest_symbol_question(question):
            yield from self._answer_busiest_symbol_day(symbols, question)
            return

        # User's follow-up after the count feature: "give me all 66
        # articles" then "cant we have it query all that?" — same reasoning
        # as the busiest-symbol-day branch above: RAG's top-k retrieval only
        # returns its most semantically similar chunks, never a genuine full
        # listing, so this routes to a real SQL fetch instead
        # (decision_log_claude.md).
        if self._aggregate_queries is not None and is_list_all_articles_question(question):
            yield from self._answer_list_all_articles(symbols, question)
            return

        chunks = self._retriever.retrieve(symbols, question)
        if not chunks:
            yield NO_NEWS_MESSAGE
            return

        prompt = self._build_prompt(chunks, question)
        yield from self._llm.stream(prompt)

    def _answer_busiest_symbol_day(self, symbols: list[str], question: str) -> Iterator[str]:
        busiest = self._aggregate_queries.busiest_symbol_day(symbols)
        if busiest is None:
            yield NO_AGGREGATE_DATA_MESSAGE
            return

        fact = (
            f"{busiest.symbol} had the most news on {busiest.date.isoformat()}, "
            f"with {busiest.article_count} articles published that day."
        )
        prompt = (
            f"{_SYSTEM_PROMPT}\n\nHere is the real, computed answer to the user's question — "
            f"just phrase it naturally, don't add or change any numbers or dates:\n{fact}"
            f"\n\nQuestion: {question}"
        )
        yield from self._llm.stream(prompt)

    def _answer_list_all_articles(self, symbols: list[str], question: str) -> Iterator[str]:
        articles, total = self._aggregate_queries.list_articles(symbols)
        if not articles:
            yield NO_NEWS_MESSAGE
            return

        listing = "\n".join(
            f"- [{a.source}, {a.published_at.isoformat()}] {a.headline} ({a.canonical_url or 'no URL available'})"
            for a in articles
        )
        note = (
            f"(Showing all {total} articles.)"
            if len(articles) == total
            else f"(Showing the {len(articles)} most recent of {total} total articles — there are more than shown here.)"
        )
        prompt = (
            f"{_SYSTEM_PROMPT}\n\nHere is the real, computed list of articles for the user's question — "
            f"present them clearly (e.g. as a list), using the exact headlines, dates, and URLs given, "
            f"never inventing or omitting any. Include this note verbatim: {note}\n\n{listing}"
            f"\n\nQuestion: {question}"
        )
        yield from self._llm.stream(prompt)

    def _build_prompt(self, chunks: list[RetrievedChunk], question: str) -> str:
        excerpts = "\n\n".join(
            f"[{chunk.source}, published {chunk.published_at.isoformat()}] "
            f"{chunk.headline} ({chunk.canonical_url or 'no URL available'})\n{chunk.chunk_text}"
            for chunk in chunks
        )
        return f"{_SYSTEM_PROMPT}\n\nRetrieved excerpts:\n{excerpts}\n\nQuestion: {question}"
