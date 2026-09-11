from datetime import date, datetime, timezone

from application.query_service import QueryService
from domain.retrieval import RetrievedChunk
from domain.stats import BusiestSymbolDay

PUBLISHED_AT = datetime(2026, 9, 18, 14, 30, tzinfo=timezone.utc)


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self._chunks = chunks
        self.last_symbols = None
        self.last_question = None

    def retrieve(self, symbols, question):
        self.last_symbols = symbols
        self.last_question = question
        return self._chunks


class FakeAggregateQueries:
    def __init__(self, busiest: BusiestSymbolDay | None):
        self._busiest = busiest
        self.last_symbols = None

    def busiest_symbol_day(self, symbols):
        self.last_symbols = symbols
        return self._busiest


class FakeLLM:
    def __init__(self, response_chunks: list[str]):
        self._response_chunks = response_chunks
        self.last_prompt = None

    def stream(self, prompt: str):
        self.last_prompt = prompt
        yield from self._response_chunks


def test_empty_retrieval_returns_guardrail_without_calling_llm():
    retriever = FakeRetriever(chunks=[])
    llm = FakeLLM(response_chunks=["should not be used"])
    service = QueryService(retriever=retriever, llm=llm)

    output = list(service.answer(symbols=["AAPL"], question="anything happening?"))

    assert len(output) == 1
    assert "news" in output[0].lower()
    assert llm.last_prompt is None


def test_nonempty_retrieval_streams_llm_response_grounded_in_chunks():
    chunks = [
        RetrievedChunk(
            article_id="a1",
            chunk_text="Apple announced a new iPhone today.",
            source="finnhub",
            headline="Apple unveils new iPhone",
            score=0.9,
            published_at=PUBLISHED_AT,
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["Apple ", "announced ", "a new iPhone."])
    service = QueryService(retriever=retriever, llm=llm)

    output = list(service.answer(symbols=["AAPL"], question="what's new with Apple?"))

    assert output == ["Apple ", "announced ", "a new iPhone."]
    assert "Apple announced a new iPhone today." in llm.last_prompt
    assert retriever.last_symbols == ["AAPL"]
    assert retriever.last_question == "what's new with Apple?"


def test_prompt_instructs_llm_to_only_use_retrieved_chunks():
    chunks = [
        RetrievedChunk(
            article_id="a1", chunk_text="text", source="finnhub", headline="h", score=0.9, published_at=PUBLISHED_AT
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["ok"])
    service = QueryService(retriever=retriever, llm=llm)

    list(service.answer(symbols=["AAPL"], question="q"))

    assert "only" in llm.last_prompt.lower() or "insufficient" in llm.last_prompt.lower()


def test_prompt_includes_canonical_url_when_present():
    # Real bug found live: the LLM claimed "the excerpts include some URLs"
    # when the prompt never contained a URL at all — RetrievedChunk had no
    # such field, so the model was hallucinating about its own context
    # (decision_log_claude.md). The prompt must actually carry the URL so a
    # real one can be cited instead of invented.
    chunks = [
        RetrievedChunk(
            article_id="a1",
            chunk_text="Apple announced a new iPhone today.",
            source="finnhub",
            headline="Apple unveils new iPhone",
            score=0.9,
            published_at=PUBLISHED_AT,
            canonical_url="https://example.com/apple-iphone",
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["ok"])
    service = QueryService(retriever=retriever, llm=llm)

    list(service.answer(symbols=["AAPL"], question="q"))

    assert "https://example.com/apple-iphone" in llm.last_prompt


def test_prompt_marks_missing_url_explicitly_instead_of_omitting_it():
    chunks = [
        RetrievedChunk(
            article_id="a1",
            chunk_text="text",
            source="finnhub",
            headline="h",
            score=0.9,
            published_at=PUBLISHED_AT,
            canonical_url=None,
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["ok"])
    service = QueryService(retriever=retriever, llm=llm)

    list(service.answer(symbols=["AAPL"], question="q"))

    assert "no URL available" in llm.last_prompt


def test_prompt_includes_publish_date():
    # Real gap found live: asked "any consecutive news in a week?" and the
    # model correctly said it couldn't tell — RetrievedChunk had no
    # published_at at all, so unlike the URL case this was an honest "I
    # don't have that" rather than a hallucination, but still a real,
    # fixable grounding gap (decision_log_claude.md).
    chunks = [
        RetrievedChunk(
            article_id="a1",
            chunk_text="text",
            source="finnhub",
            headline="h",
            score=0.9,
            published_at=PUBLISHED_AT,
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["ok"])
    service = QueryService(retriever=retriever, llm=llm)

    list(service.answer(symbols=["AAPL"], question="q"))

    assert PUBLISHED_AT.isoformat() in llm.last_prompt


class TestBusiestSymbolDayQuestions:
    # User's exact question: "what symbol have most news in a day?" — RAG's
    # top-k semantic retrieval only pulls chunks relevant to the question
    # text, it can never answer a genuine aggregate/count across the whole
    # watchlist's history. These questions route to a real SQL aggregate
    # instead (decision_log_claude.md).
    def test_routes_to_aggregate_queries_instead_of_retrieval(self):
        retriever = FakeRetriever(chunks=[])
        aggregate = FakeAggregateQueries(
            busiest=BusiestSymbolDay(symbol="GOOG", date=date(2026, 9, 21), article_count=66)
        )
        llm = FakeLLM(response_chunks=["GOOG had the most news."])
        service = QueryService(retriever=retriever, llm=llm, aggregate_queries=aggregate)

        output = list(service.answer(symbols=["GOOG", "TSLA"], question="what symbol have most news in a day?"))

        assert output == ["GOOG had the most news."]
        assert aggregate.last_symbols == ["GOOG", "TSLA"]
        assert retriever.last_symbols is None  # retrieval never called

    def test_prompt_gives_the_llm_the_real_computed_fact_to_phrase(self):
        aggregate = FakeAggregateQueries(
            busiest=BusiestSymbolDay(symbol="GOOG", date=date(2026, 9, 21), article_count=66)
        )
        llm = FakeLLM(response_chunks=["ok"])
        service = QueryService(retriever=FakeRetriever(chunks=[]), llm=llm, aggregate_queries=aggregate)

        list(service.answer(symbols=["GOOG"], question="which symbol has the most articles in a day"))

        assert "GOOG" in llm.last_prompt
        assert "66" in llm.last_prompt
        assert "2026-09-21" in llm.last_prompt

    def test_returns_guardrail_when_no_aggregate_data_exists(self):
        aggregate = FakeAggregateQueries(busiest=None)
        llm = FakeLLM(response_chunks=["should not be used"])
        service = QueryService(retriever=FakeRetriever(chunks=[]), llm=llm, aggregate_queries=aggregate)

        output = list(service.answer(symbols=["GOOG"], question="what symbol has the most news in a day?"))

        assert len(output) == 1
        assert llm.last_prompt is None

    def test_ordinary_questions_still_use_retrieval_when_aggregate_queries_configured(self):
        chunks = [
            RetrievedChunk(
                article_id="a1", chunk_text="text", source="finnhub", headline="h", score=0.9, published_at=PUBLISHED_AT
            )
        ]
        retriever = FakeRetriever(chunks=chunks)
        aggregate = FakeAggregateQueries(busiest=None)
        llm = FakeLLM(response_chunks=["ok"])
        service = QueryService(retriever=retriever, llm=llm, aggregate_queries=aggregate)

        list(service.answer(symbols=["AAPL"], question="what's new with Apple?"))

        assert retriever.last_question == "what's new with Apple?"
        assert aggregate.last_symbols is None  # aggregate path never triggered

    def test_falls_back_to_retrieval_when_no_aggregate_queries_configured(self):
        # Optional collaborator, matching this codebase's established
        # pattern (BackfillQueue, JobTrigger, etc.) — existing callers that
        # don't wire this in must keep working exactly as before.
        chunks = [
            RetrievedChunk(
                article_id="a1", chunk_text="text", source="finnhub", headline="h", score=0.9, published_at=PUBLISHED_AT
            )
        ]
        retriever = FakeRetriever(chunks=chunks)
        llm = FakeLLM(response_chunks=["ok"])
        service = QueryService(retriever=retriever, llm=llm)

        list(service.answer(symbols=["AAPL"], question="what symbol have most news in a day?"))

        assert retriever.last_question == "what symbol have most news in a day?"
