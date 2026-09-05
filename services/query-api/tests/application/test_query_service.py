from application.query_service import QueryService
from domain.retrieval import RetrievedChunk


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self._chunks = chunks
        self.last_symbols = None
        self.last_question = None

    def retrieve(self, symbols, question):
        self.last_symbols = symbols
        self.last_question = question
        return self._chunks


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
            article_id="a1", chunk_text="text", source="finnhub", headline="h", score=0.9
        )
    ]
    retriever = FakeRetriever(chunks=chunks)
    llm = FakeLLM(response_chunks=["ok"])
    service = QueryService(retriever=retriever, llm=llm)

    list(service.answer(symbols=["AAPL"], question="q"))

    assert "only" in llm.last_prompt.lower() or "insufficient" in llm.last_prompt.lower()
