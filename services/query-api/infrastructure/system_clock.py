from __future__ import annotations

from datetime import date, datetime, timezone


class SystemClock:
    def today(self) -> date:
        return date.today()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
