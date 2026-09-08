from datetime import date, datetime, timezone

import httpx

from infrastructure.finnhub_news_client import FinnhubNewsClient, NewsArticle

SAMPLE_RESPONSE = [
    {
        "category": "company",
        "datetime": 1789909222,
        "headline": "Turning 73 Forces a Withdrawal From This Stock",
        "id": 142288139,
        "image": "https://example.com/img.png",
        "related": "AAPL",
        "source": "Yahoo",
        "summary": "Some summary text.",
        "url": "https://finnhub.io/api/news?id=abc123",
    },
    {
        "category": "company",
        "datetime": 1789902600,
        "headline": "Greg Abel Recently Plowed $4.2 Billion",
        "id": 142286308,
        "image": "",
        "related": "AAPL",
        "source": "Motley Fool",
        "summary": "Another summary.",
        "url": "https://finnhub.io/api/news?id=def456",
    },
]


def test_fetch_company_news_parses_articles(httpx_mock):
    httpx_mock.add_response(json=SAMPLE_RESPONSE)
    client = FinnhubNewsClient(http_client=httpx.Client(), api_key="test-key")

    articles = client.fetch_company_news("AAPL", from_date=date(2026, 9, 6), to_date=date(2026, 9, 20))

    assert articles == [
        NewsArticle(
            headline="Turning 73 Forces a Withdrawal From This Stock",
            summary="Some summary text.",
            source="Yahoo",
            url="https://finnhub.io/api/news?id=abc123",
            published_at=datetime.fromtimestamp(1789909222, tz=timezone.utc),
        ),
        NewsArticle(
            headline="Greg Abel Recently Plowed $4.2 Billion",
            summary="Another summary.",
            source="Motley Fool",
            url="https://finnhub.io/api/news?id=def456",
            published_at=datetime.fromtimestamp(1789902600, tz=timezone.utc),
        ),
    ]


def test_fetch_company_news_sends_symbol_and_date_range(httpx_mock):
    httpx_mock.add_response(json=[])
    client = FinnhubNewsClient(http_client=httpx.Client(), api_key="test-key")

    client.fetch_company_news("AAPL", from_date=date(2026, 9, 6), to_date=date(2026, 9, 20))

    request = httpx_mock.get_requests()[0]
    assert request.url.params["symbol"] == "AAPL"
    assert request.url.params["from"] == "2026-09-06"
    assert request.url.params["to"] == "2026-09-20"
    assert request.url.params["token"] == "test-key"


def test_fetch_company_news_returns_empty_list_for_no_articles(httpx_mock):
    httpx_mock.add_response(json=[])
    client = FinnhubNewsClient(http_client=httpx.Client(), api_key="test-key")

    articles = client.fetch_company_news("AAPL", from_date=date(2026, 9, 6), to_date=date(2026, 9, 20))

    assert articles == []
