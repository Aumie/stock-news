"""Live check: confirms Finnhub's company-news endpoint still returns the
assumed shape for a real symbol/date range. Same source poller.go already
verified live for the continuous poll cycle — this is query-api's own
on-demand backfill path (watchlist-add), see decision_log.md.

Requires FINNHUB_API_KEY. Skips if unset or unreachable.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pytest

from infrastructure.finnhub_news_client import FinnhubNewsClient

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")


@pytest.fixture
def client():
    if not FINNHUB_API_KEY:
        pytest.skip("FINNHUB_API_KEY not set")
    with httpx.Client(timeout=10.0) as http_client:
        yield FinnhubNewsClient(http_client=http_client, api_key=FINNHUB_API_KEY)


def test_fetch_company_news_returns_real_recent_articles(client):
    today = date.today()
    articles = client.fetch_company_news("AAPL", from_date=today - timedelta(days=14), to_date=today)

    assert len(articles) > 0
    for article in articles:
        assert article.headline
        assert article.source
        assert article.url
