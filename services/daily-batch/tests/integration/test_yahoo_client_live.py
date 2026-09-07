"""Live check for milestone 5 (docs/milestone.md §5): confirms Yahoo Finance's
chart API still returns real OHLCV for a known symbol with just a browser
User-Agent header — no key needed. This is the source-of-truth verification
behind the price-source correction in docs/decision_log.md (Finnhub's candle
endpoint returned a real 403; Stooq is blocked by a JS anti-bot challenge).

Skips (not fails) if the network is unreachable, matching this project's
pattern for external-dependency integration tests.
"""

from __future__ import annotations

import httpx
import pytest

from prices.yahoo_client import NoDataError, YahooClient


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=10.0) as http_client:
        yield YahooClient(http_client=http_client)


def test_fetch_daily_bars_returns_real_recent_data_for_aapl(client):
    try:
        bars = client.fetch_daily_bars("AAPL", range_="5d")
    except httpx.HTTPError as exc:
        pytest.skip(f"Yahoo Finance unreachable: {exc}")

    assert len(bars) >= 3
    for bar in bars:
        assert bar.low <= bar.open <= bar.high
        assert bar.low <= bar.close <= bar.high
        assert bar.volume > 0


def test_fetch_daily_bars_raises_no_data_for_unknown_symbol(client):
    with pytest.raises(NoDataError):
        client.fetch_daily_bars("ZZZNOTASYMBOL99", range_="5d")
