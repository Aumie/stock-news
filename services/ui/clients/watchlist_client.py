from __future__ import annotations

import httpx

from clients.query_api_auth import build_headers


class WatchlistAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def list_symbols(self, jwt: str) -> list[dict]:
        response = httpx.get(
            f"{self._base_url}/watchlist",
            headers=build_headers(self._base_url, jwt),
            # query-api scales to zero (min_instance_count=0); a real cold
            # start loading its SentenceTransformer model was clocked at
            # 74.66s live (stats_client.py). This page is often the first
            # call after a cold instance, so it needs the same headroom —
            # found live: a real ReadTimeout crashed the Watchlist page.
            timeout=90.0,
        )
        response.raise_for_status()
        return response.json()

    def add_symbol(self, jwt: str, symbol: str) -> tuple[bool, str | None]:
        response = httpx.post(
            f"{self._base_url}/watchlist",
            headers=build_headers(self._base_url, jwt),
            json={"symbol": symbol},
            # The response returns as soon as symbol validation + the DB
            # write finish — the news/price backfill runs in a background
            # Celery task, not inline (decision_log.md) — but a cold
            # query-api instance still needs cold-start headroom before it
            # can even run the one synchronous Finnhub /search call (see
            # list_symbols' own comment, 74.66s measured live).
            timeout=90.0,
        )
        if response.status_code == 422:
            return False, response.json().get("detail", "invalid symbol")
        if response.status_code == 503:
            # Real bug found live: Finnhub's /search itself was down (a
            # genuine 503), which used to crash this call with an unhandled
            # 500 — distinct from 422 (symbol genuinely doesn't exist), this
            # means validation couldn't happen at all right now
            # (decision_log.md).
            return False, response.json().get("detail", "symbol validation is temporarily unavailable")
        response.raise_for_status()
        return True, None

    def remove_symbol(self, jwt: str, symbol: str) -> None:
        response = httpx.delete(
            f"{self._base_url}/watchlist/{symbol}",
            headers=build_headers(self._base_url, jwt),
            # Same query-api cold-start headroom as list_symbols above.
            timeout=90.0,
        )
        response.raise_for_status()
