from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation.internal_api import build_internal_router


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_symbol_news_ingested(self, symbol: str) -> None:
        self.enqueued.append(symbol)


def _client(queue: FakeQueue) -> TestClient:
    app = FastAPI()
    app.include_router(build_internal_router(queue))
    return TestClient(app)


def test_symbol_news_ingested_enqueues_and_returns_202():
    queue = FakeQueue()
    client = _client(queue)

    response = client.post("/internal/symbol-news-ingested", json={"symbol": "TSLA"})

    assert response.status_code == 202
    assert queue.enqueued == ["TSLA"]


def test_symbol_news_ingested_requires_no_auth_header():
    # Service-to-service call, not a per-user request — must not require the
    # Authorization header every other endpoint in this service needs.
    queue = FakeQueue()
    client = _client(queue)

    response = client.post("/internal/symbol-news-ingested", json={"symbol": "AAPL"})

    assert response.status_code == 202
