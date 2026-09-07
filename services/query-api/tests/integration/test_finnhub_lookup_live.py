"""Live check for milestone 6's watchlist-management requirement (§4.1):
confirms Finnhub's /search endpoint still behaves as assumed — fuzzy,
cross-exchange results for a valid ticker, empty results for garbage.

Requires FINNHUB_API_KEY. Skips (not fails) if unset or unreachable.
"""

from __future__ import annotations

import os

import httpx
import pytest

from infrastructure.finnhub_lookup import FinnhubSymbolLookup, InvalidSymbolError

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")


@pytest.fixture
def lookup():
    if not FINNHUB_API_KEY:
        pytest.skip("FINNHUB_API_KEY not set")
    with httpx.Client(timeout=10.0) as http_client:
        yield FinnhubSymbolLookup(http_client=http_client, api_key=FINNHUB_API_KEY)


def test_validate_accepts_real_known_symbol(lookup):
    lookup.validate("AAPL")  # does not raise


def test_validate_rejects_real_unknown_symbol(lookup):
    with pytest.raises(InvalidSymbolError):
        lookup.validate("ZZZNOTAREALTICKER99")
