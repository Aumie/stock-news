from __future__ import annotations


def next_page_cursor(items: list[dict]) -> tuple[str, str] | None:
    # Assumes items are already sorted descending by published_at (the feed
    # always is) — the oldest item shown so far is the correct cursor for
    # "load older news from here."
    if not items:
        return None
    oldest = items[-1]
    return oldest["published_at"], oldest["article_id"]
