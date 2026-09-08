from views.formatting import format_timestamp


def test_format_timestamp_with_microseconds():
    assert format_timestamp("2026-09-20T15:49:22.989432+00:00") == "Sep 20, 2026 3:49 PM UTC"


def test_format_timestamp_midnight_hour():
    assert format_timestamp("2026-01-05T00:05:00+00:00") == "Jan 5, 2026 12:05 AM UTC"


def test_format_timestamp_noon_hour():
    assert format_timestamp("2026-01-05T12:00:00+00:00") == "Jan 5, 2026 12:00 PM UTC"


def test_format_timestamp_single_digit_day_and_minute():
    assert format_timestamp("2026-01-05T09:05:00+00:00") == "Jan 5, 2026 9:05 AM UTC"
