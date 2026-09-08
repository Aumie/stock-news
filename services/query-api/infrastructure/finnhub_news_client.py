from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

BASE_URL = "https://finnhub.io/api/v1"


@dataclass(frozen=True)
class NewsArticle:
    headline: str
    summary: str
    source: str
    url: str
    published_at: datetime


class FinnhubNewsClient:
    """Python port of services/poller/internal/poller/finnhub.go's
    CompanyNews — same endpoint, same response shape, verified live against
    the same key. Used for on-demand watchlist-add backfill (query-api),
    not the continuous poll cycle (poller, Go).
    """

    def __init__(self, http_client: httpx.Client, api_key: str) -> None:
        self._http = http_client
        self._api_key = api_key

    def fetch_company_news(self, symbol: str, from_date: date, to_date: date) -> list[NewsArticle]:
        response = self._http.get(
            f"{BASE_URL}/company-news",
            params={
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "token": self._api_key,
            },
        )
        response.raise_for_status()
        return [
            NewsArticle(
                headline=item["headline"],
                summary=item["summary"],
                source=item["source"],
                url=item["url"],
                published_at=datetime.fromtimestamp(item["datetime"], tz=timezone.utc),
            )
            for item in response.json()
        ]
