from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from infrastructure.finnhub_news_client import NewsArticle
from infrastructure.processing_ingest_client import ProcessingIngestClient

ARTICLE = NewsArticle(
    source="finnhub",
    headline="Some headline",
    summary="Some summary",
    url="https://example.com/article",
    published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


def test_ingest_sends_no_authorization_header_locally(httpx_mock):
    httpx_mock.add_response(json={"article_id": "abc"})
    client = ProcessingIngestClient(http_client=httpx.Client(), base_url="http://localhost:8001")

    client.ingest(ARTICLE, symbol="AAPL")

    request = httpx_mock.get_requests()[0]
    assert "Authorization" not in request.headers


def test_ingest_attaches_a_google_id_token_in_the_cloud(httpx_mock):
    httpx_mock.add_response(json={"article_id": "abc"})
    client = ProcessingIngestClient(http_client=httpx.Client(), base_url="https://processing-abc.a.run.app")

    with patch(
        "infrastructure.processing_ingest_client.fetch_authorization_header",
        return_value="Bearer fake-id-token",
    ) as mock_fetch:
        client.ingest(ARTICLE, symbol="AAPL")

    mock_fetch.assert_called_once_with("https://processing-abc.a.run.app")
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer fake-id-token"
