from __future__ import annotations

from datetime import datetime, timedelta, timezone

from application.rebuild_debounce_service import DEBOUNCE_INTERVAL, RebuildDebounceService

START = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeRepo:
    def __init__(self) -> None:
        self.last_triggered: dict[str, datetime] = {}

    def get_last_triggered_at(self, symbol: str) -> datetime | None:
        return self.last_triggered.get(symbol)

    def set_last_triggered_at(self, symbol: str, when: datetime) -> None:
        self.last_triggered[symbol] = when


class FakeTrigger:
    def __init__(self) -> None:
        self.triggered_for: list[str] = []

    def trigger_for_symbol(self, symbol: str) -> None:
        self.triggered_for.append(symbol)


def test_triggers_on_first_notification_for_a_symbol():
    repo = FakeRepo()
    trigger = FakeTrigger()
    service = RebuildDebounceService(repo, FakeClock(START), trigger)

    triggered = service.notify_symbol_has_new_news("TSLA")

    assert triggered is True
    assert trigger.triggered_for == ["TSLA"]
    assert repo.get_last_triggered_at("TSLA") == START


def test_does_not_retrigger_within_the_debounce_window():
    repo = FakeRepo()
    repo.set_last_triggered_at("TSLA", START)
    trigger = FakeTrigger()
    clock = FakeClock(START + timedelta(minutes=30))
    service = RebuildDebounceService(repo, clock, trigger)

    triggered = service.notify_symbol_has_new_news("TSLA")

    assert triggered is False
    assert trigger.triggered_for == []


def test_retriggers_once_the_debounce_window_has_elapsed():
    repo = FakeRepo()
    repo.set_last_triggered_at("TSLA", START)
    trigger = FakeTrigger()
    clock = FakeClock(START + DEBOUNCE_INTERVAL + timedelta(seconds=1))
    service = RebuildDebounceService(repo, clock, trigger)

    triggered = service.notify_symbol_has_new_news("TSLA")

    assert triggered is True
    assert trigger.triggered_for == ["TSLA"]
    assert repo.get_last_triggered_at("TSLA") == clock.now()


def test_debounce_is_scoped_per_symbol():
    repo = FakeRepo()
    repo.set_last_triggered_at("TSLA", START)
    trigger = FakeTrigger()
    clock = FakeClock(START + timedelta(minutes=5))
    service = RebuildDebounceService(repo, clock, trigger)

    triggered = service.notify_symbol_has_new_news("AAPL")

    assert triggered is True
    assert trigger.triggered_for == ["AAPL"]
