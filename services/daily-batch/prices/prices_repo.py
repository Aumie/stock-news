from __future__ import annotations

import psycopg

from prices.yahoo_client import DailyBar


class PostgresPricesRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def upsert_bars(self, symbol: str, bars: list[DailyBar]) -> None:
        for bar in bars:
            self._conn.execute(
                """
                INSERT INTO prices (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
                """,
                (symbol, bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume),
            )
