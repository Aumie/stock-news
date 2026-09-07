from __future__ import annotations

import httpx

BASE_URL = "https://finnhub.io/api/v1"


class InvalidSymbolError(Exception):
    """Raised when Finnhub's symbol search has no exact match for a ticker."""


class FinnhubSymbolLookup:
    def __init__(self, http_client: httpx.Client, api_key: str) -> None:
        self._http = http_client
        self._api_key = api_key

    def validate(self, symbol: str) -> None:
        response = self._http.get(
            f"{BASE_URL}/search",
            params={"q": symbol, "token": self._api_key},
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        # Finnhub's /search is fuzzy and returns cross-exchange matches
        # (AAPL.TO, AAPL.MX, ...) for a query like "AAPL" — accepting "any
        # result came back" would let e.g. "AAPLX" pass if it fuzzy-matched
        # something. Require an exact, case-insensitive symbol match instead
        # (§4.1's "validated against a known ticker reference").
        if not any(result["symbol"].upper() == symbol.upper() for result in results):
            raise InvalidSymbolError(f"unrecognized symbol: {symbol}")
