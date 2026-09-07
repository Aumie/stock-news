from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    added_at: datetime


class SymbolAlreadyWatchedError(Exception):
    """Raised when the user already watches this symbol."""
