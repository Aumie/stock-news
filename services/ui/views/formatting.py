from __future__ import annotations

from datetime import datetime


def format_timestamp(iso_string: str) -> str:
    # Backend responses use datetime.isoformat(), e.g.
    # "2026-09-20T15:49:22.989432+00:00" — not something a user should see
    # raw (reported live: confusing microsecond-precision UTC ISO string).
    # Deliberately not using %-d/%-I (no-leading-zero) strftime directives —
    # they're a glibc/Linux extension that raises ValueError on Windows,
    # confirmed by testing this locally before deciding.
    dt = datetime.fromisoformat(iso_string)
    hour_12 = dt.hour % 12 or 12
    am_pm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year} {hour_12}:{dt.minute:02d} {am_pm} UTC"
