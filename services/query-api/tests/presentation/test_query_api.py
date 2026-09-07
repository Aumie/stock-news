from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.query_service import QueryService
from application.watchlist_service import WatchlistService
from domain.retrieval import RetrievedChunk
from domain.watchlist import WatchlistEntry
from presentation.query_api import build_query_router

SECRET = "test-secret-at-least-32-bytes-long!"


class FakeWatchlistRepo:
    def __init__(self, entries: dict[str, list[str]]):
        self._entries = entries

    def list_for_user(self, user_id: str) -> list[WatchlistEntry]:
        return [
            WatchlistEntry(symbol=s, added_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
            for s in self._entries.get(user_id, [])
        ]

    def add(self, user_id, symbol):
        raise NotImplementedError

    def remove(self, user_id, symbol):
        raise NotImplementedError


class FakeRetriever:
    def __init__(self):
        self.last_symbols = None

    def retrieve(self, symbols, question):
        self.last_symbols = symbols
        return [RetrievedChunk(article_id="a1", chunk_text="text", source="finnhub", headline="h", score=0.9)]


class FakeLLM:
    def stream(self, prompt: str):
        yield "answer"


def _make_token(sub="user-1"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


@pytest.fixture
def retriever():
    return FakeRetriever()


@pytest.fixture
def client(retriever):
    watchlist_service = WatchlistService(repo=FakeWatchlistRepo({"user-1": ["AAPL", "MSFT"]}), lookup=None)
    query_service = QueryService(retriever=retriever, llm=FakeLLM())
    app = FastAPI()
    app.include_router(build_query_router(query_service, watchlist_service, secret=SECRET))
    return TestClient(app)


def test_query_derives_symbols_from_watchlist_not_request_body(client, retriever):
    response = client.post(
        "/query",
        json={"question": "what's new?", "symbols": ["IGNORED_SHOULD_NOT_BE_USED"]},
        headers={"Authorization": f"Bearer {_make_token('user-1')}"},
    )

    assert response.status_code == 200
    assert retriever.last_symbols == ["AAPL", "MSFT"]


def test_query_with_empty_watchlist_still_answers(client, retriever):
    response = client.post(
        "/query",
        json={"question": "what's new?"},
        headers={"Authorization": f"Bearer {_make_token('user-with-no-watchlist')}"},
    )

    assert response.status_code == 200
    assert retriever.last_symbols == []
