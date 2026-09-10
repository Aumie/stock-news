from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PostgresRebuildDebounceRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_last_triggered_at(self, symbol: str) -> datetime | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT last_triggered_at FROM symbol_rebuild_debounce WHERE symbol = :symbol"),
                {"symbol": symbol},
            ).fetchone()
        return row.last_triggered_at if row is not None else None

    def set_last_triggered_at(self, symbol: str, when: datetime) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO symbol_rebuild_debounce (symbol, last_triggered_at)
                    VALUES (:symbol, :when)
                    ON CONFLICT (symbol) DO UPDATE SET last_triggered_at = EXCLUDED.last_triggered_at
                    """
                ),
                {"symbol": symbol, "when": when},
            )
