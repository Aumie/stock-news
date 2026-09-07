from __future__ import annotations

import httpx


class StatsAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def get_stats(self, jwt: str) -> dict:
        response = httpx.get(
            f"{self._base_url}/stats",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
