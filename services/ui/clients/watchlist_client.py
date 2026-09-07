from __future__ import annotations

import httpx


class WatchlistAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def list_symbols(self, jwt: str) -> list[dict]:
        response = httpx.get(
            f"{self._base_url}/watchlist",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    def add_symbol(self, jwt: str, symbol: str) -> tuple[bool, str | None]:
        response = httpx.post(
            f"{self._base_url}/watchlist",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"symbol": symbol},
            timeout=10.0,
        )
        if response.status_code == 422:
            return False, response.json().get("detail", "invalid symbol")
        response.raise_for_status()
        return True, None

    def remove_symbol(self, jwt: str, symbol: str) -> None:
        response = httpx.delete(
            f"{self._base_url}/watchlist/{symbol}",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=10.0,
        )
        response.raise_for_status()
