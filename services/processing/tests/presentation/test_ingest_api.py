from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.validation import ArticleValidationError
from presentation.ingest_api import build_ingest_router


class FakeUseCase:
    def __init__(self, article_id: str = "fake-id"):
        self._article_id = article_id
        self.last_article = None
        self.last_symbol = None

    def process(self, article, symbol: str) -> str:
        self.last_article = article
        self.last_symbol = symbol
        return self._article_id


class FakeUseCaseRejectingInput:
    def process(self, article, symbol: str) -> str:
        raise ArticleValidationError(f"malformed symbol: {symbol!r}")


def _client(use_case):
    app = FastAPI()
    app.include_router(build_ingest_router(use_case))
    return TestClient(app)


def test_ingest_calls_use_case_with_parsed_article():
    use_case = FakeUseCase(article_id="abc-123")
    client = _client(use_case)

    response = client.post(
        "/articles/ingest",
        json={
            "source": "finnhub",
            "headline": "Apple unveils new iPhone",
            "published_at": "2026-09-01T14:30:00Z",
            "content": "body text",
            "symbol": "AAPL",
            "canonical_url": "https://example.com/article",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"article_id": "abc-123"}
    assert use_case.last_article.headline == "Apple unveils new iPhone"
    assert use_case.last_article.source == "finnhub"
    assert use_case.last_article.canonical_url == "https://example.com/article"
    assert use_case.last_symbol == "AAPL"


def test_ingest_without_canonical_url():
    use_case = FakeUseCase()
    client = _client(use_case)

    response = client.post(
        "/articles/ingest",
        json={
            "source": "finnhub",
            "headline": "headline",
            "published_at": "2026-09-01T14:30:00Z",
            "content": "body",
            "symbol": "AAPL",
        },
    )

    assert response.status_code == 200
    assert use_case.last_article.canonical_url is None


def test_ingest_missing_required_field_returns_422():
    client = _client(FakeUseCase())

    response = client.post("/articles/ingest", json={"source": "finnhub"})

    assert response.status_code == 422


def test_ingest_rejects_structurally_invalid_input_with_422():
    client = _client(FakeUseCaseRejectingInput())

    response = client.post(
        "/articles/ingest",
        json={
            "source": "finnhub",
            "headline": "headline",
            "published_at": "2026-09-01T14:30:00Z",
            "content": "body",
            "symbol": "not-a-symbol",
        },
    )

    assert response.status_code == 422
    assert "not-a-symbol" in response.json()["detail"]
