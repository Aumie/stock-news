from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PostgresBackfillProgressRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_earliest_backfilled(self, symbol: str) -> date | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT earliest_backfilled_date FROM symbol_backfill_progress WHERE symbol = :symbol"),
                {"symbol": symbol},
            ).fetchone()
        return row.earliest_backfilled_date if row is not None else None

    def set_earliest_backfilled(self, symbol: str, earliest: date) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO symbol_backfill_progress (symbol, earliest_backfilled_date)
                    VALUES (:symbol, :earliest)
                    ON CONFLICT (symbol) DO UPDATE SET earliest_backfilled_date = EXCLUDED.earliest_backfilled_date
                    """
                ),
                {"symbol": symbol, "earliest": earliest},
            )
