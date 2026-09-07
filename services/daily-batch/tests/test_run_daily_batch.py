from datetime import date

from prices.run_daily_batch import run_daily_batch
from prices.yahoo_client import DailyBar, NoDataError


class FakeYahooClient:
    def __init__(self, bars_by_symbol: dict[str, list[DailyBar]]):
        self._bars_by_symbol = bars_by_symbol

    def fetch_daily_bars(self, symbol: str, range_: str = "5d") -> list[DailyBar]:
        if symbol not in self._bars_by_symbol:
            raise NoDataError(f"unknown symbol: {symbol}")
        return self._bars_by_symbol[symbol]


class FakePricesRepo:
    def __init__(self):
        self.upserted: dict[str, list[DailyBar]] = {}

    def upsert_bars(self, symbol: str, bars: list[DailyBar]) -> None:
        self.upserted[symbol] = bars


def test_run_daily_batch_upserts_bars_for_every_watched_symbol():
    bar = DailyBar(date=date(2026, 9, 19), open=1, high=2, low=0.5, close=1.5, volume=100)
    client = FakeYahooClient({"AAPL": [bar], "MSFT": [bar]})
    repo = FakePricesRepo()

    result = run_daily_batch(symbols=["AAPL", "MSFT"], yahoo_client=client, prices_repo=repo)

    assert repo.upserted == {"AAPL": [bar], "MSFT": [bar]}
    assert result.succeeded_symbols == ["AAPL", "MSFT"]
    assert result.failed_symbols == []


def test_run_daily_batch_continues_past_a_single_symbol_failure():
    bar = DailyBar(date=date(2026, 9, 19), open=1, high=2, low=0.5, close=1.5, volume=100)
    client = FakeYahooClient({"AAPL": [bar]})
    repo = FakePricesRepo()

    result = run_daily_batch(symbols=["AAPL", "DELISTEDCO"], yahoo_client=client, prices_repo=repo)

    assert repo.upserted == {"AAPL": [bar]}
    assert result.succeeded_symbols == ["AAPL"]
    assert result.failed_symbols == ["DELISTEDCO"]


def test_run_daily_batch_with_no_watched_symbols_is_a_no_op():
    repo = FakePricesRepo()

    result = run_daily_batch(symbols=[], yahoo_client=FakeYahooClient({}), prices_repo=repo)

    assert repo.upserted == {}
    assert result.succeeded_symbols == []
    assert result.failed_symbols == []
