from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

BASE_URL = "https://query1.finance.yahoo.com"
# Yahoo's chart API rejects requests with no User-Agent (or a non-browser
# one) — this is a normal header, not bot-detection bypass (docs/decision_log.md,
# "Data & storage": price source correction).
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class NoDataError(Exception):
    """Raised when Yahoo has no chart data for the requested symbol/range."""


@dataclass(frozen=True)
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


def parse_chart_response(payload: dict) -> list[DailyBar]:
    result = payload.get("chart", {}).get("result")
    if not result:
        raise NoDataError(payload.get("chart", {}).get("error"))

    series = result[0]
    timestamps = series["timestamp"]
    quote = series["indicators"]["quote"][0]

    bars = []
    for i, ts in enumerate(timestamps):
        close = quote["close"][i]
        if close is None:
            # Mid-session gap (e.g. a still-forming intraday bar) — Yahoo
            # returns nulls across all fields for that index, not a shorter array.
            continue
        bars.append(
            DailyBar(
                date=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                open=quote["open"][i],
                high=quote["high"][i],
                low=quote["low"][i],
                close=close,
                volume=quote["volume"][i],
            )
        )
    return bars


class YahooClient:
    def __init__(self, http_client: httpx.Client):
        self._http = http_client

    def fetch_daily_bars(self, symbol: str, range_: str = "5d") -> list[DailyBar]:
        response = self._http.get(
            f"{BASE_URL}/v8/finance/chart/{symbol}",
            params={"range": range_, "interval": "1d"},
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code == 404:
            # Yahoo returns a bare 404 for a symbol it doesn't recognize at
            # all (confirmed live), distinct from the 200 + null-result shape
            # parse_chart_response handles for a known-but-empty range.
            raise NoDataError(f"unknown symbol: {symbol}")
        response.raise_for_status()
        return parse_chart_response(response.json())
