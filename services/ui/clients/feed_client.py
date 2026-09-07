from __future__ import annotations

import httpx


class FeedAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def recent(self, jwt: str) -> list[dict]:
        response = httpx.get(
            f"{self._base_url}/feed",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
