from __future__ import annotations

import httpx

from clients.query_api_auth import build_headers


class StatsAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def get_stats(self, jwt: str) -> dict:
        response = httpx.get(
            f"{self._base_url}/stats",
            headers=build_headers(self._base_url, jwt),
            # 30s, not 10s — found live: a busy symbol's watchlist-add
            # backfill runs dozens of sequential ingest calls against the
            # same Postgres instance /stats reads from, and 10s wasn't
            # always enough headroom while that write load was ongoing.
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
