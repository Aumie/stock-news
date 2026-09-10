from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

# 1 hour: real news volume on a busy symbol can arrive many times an hour
# (a genuine burst hit TSLA — 6 articles in ~14 minutes, live — so
# triggering a full daily_symbol_features rebuild on every single article
# would fire far too often). 1 hour keeps Stats meaningfully fresher than
# the old 24h-only sweep without turning "new news" into a near-continuous
# rebuild loop (decision_log_claude.md).
DEBOUNCE_INTERVAL = timedelta(hours=1)


class RebuildDebounceRepo(Protocol):
    def get_last_triggered_at(self, symbol: str) -> datetime | None: ...
    def set_last_triggered_at(self, symbol: str, when: datetime) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class RebuildTrigger(Protocol):
    def trigger_for_symbol(self, symbol: str) -> None: ...


class RebuildDebounceService:
    def __init__(self, repo: RebuildDebounceRepo, clock: Clock, trigger: RebuildTrigger) -> None:
        self._repo = repo
        self._clock = clock
        self._trigger = trigger

    def notify_symbol_has_new_news(self, symbol: str) -> bool:
        """Triggers a daily_symbol_features rebuild for this symbol, unless
        one already fired within the debounce window. Returns whether a
        rebuild was actually triggered, for callers/tests that care.
        """
        now = self._clock.now()
        last_triggered = self._repo.get_last_triggered_at(symbol)
        if last_triggered is not None and now - last_triggered < DEBOUNCE_INTERVAL:
            return False

        self._trigger.trigger_for_symbol(symbol)
        self._repo.set_last_triggered_at(symbol, now)
        return True
