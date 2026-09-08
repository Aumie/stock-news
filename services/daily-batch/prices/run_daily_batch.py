from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import structlog

from prices.yahoo_client import DailyBar, NoDataError

logger = structlog.get_logger()


class YahooClientProtocol(Protocol):
    def fetch_daily_bars(self, symbol: str, range_: str = "5d") -> list[DailyBar]: ...


class PricesRepoProtocol(Protocol):
    def upsert_bars(self, symbol: str, bars: list[DailyBar]) -> None: ...


@dataclass
class BatchResult:
    succeeded_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)


def run_daily_batch(
    symbols: list[str],
    yahoo_client: YahooClientProtocol,
    prices_repo: PricesRepoProtocol,
    range_: str = "5d",
) -> BatchResult:
    result = BatchResult()
    for symbol in symbols:
        try:
            bars = yahoo_client.fetch_daily_bars(symbol, range_=range_)
        except NoDataError:
            # One symbol's data being unavailable (delisted, typo, Yahoo
            # coverage gap) shouldn't block every other watched symbol's
            # price update — same "isolate, don't cascade" principle as the
            # poller's per-symbol overflow handling.
            logger.warning("daily_batch.symbol_skipped", symbol=symbol)
            result.failed_symbols.append(symbol)
            continue
        prices_repo.upsert_bars(symbol, bars)
        result.succeeded_symbols.append(symbol)
    return result
