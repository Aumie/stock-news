from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from domain.watchlist import WatchlistEntry


class PostgresWatchlistRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_for_user(self, user_id: str) -> list[WatchlistEntry]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                text("SELECT symbol, added_at FROM watchlist WHERE user_id = CAST(:user_id AS uuid) ORDER BY added_at"),
                {"user_id": user_id},
            ).fetchall()
        return [WatchlistEntry(symbol=row.symbol, added_at=row.added_at) for row in rows]

    def add(self, user_id: str, symbol: str) -> WatchlistEntry:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO watchlist (user_id, symbol)
                    VALUES (CAST(:user_id AS uuid), :symbol)
                    ON CONFLICT (user_id, symbol) DO UPDATE SET symbol = EXCLUDED.symbol
                    RETURNING symbol, added_at
                    """
                ),
                {"user_id": user_id, "symbol": symbol},
            ).fetchone()
        return WatchlistEntry(symbol=row.symbol, added_at=row.added_at)

    def remove(self, user_id: str, symbol: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("DELETE FROM watchlist WHERE user_id = CAST(:user_id AS uuid) AND symbol = :symbol"),
                {"user_id": user_id, "symbol": symbol},
            )
