from __future__ import annotations


def sort_and_filter_feed(items: list[dict], selected_symbols: list[str]) -> list[dict]:
    # Explicit sort here rather than trusting the backend's own ORDER BY —
    # filtering shouldn't silently depend on the response already being
    # sorted the way this page needs it displayed. Sorted by published_at,
    # not ingested_at (user-specified: descending by publish date) — the two
    # genuinely diverge for backfilled articles (old news ingested late).
    items = sorted(items, key=lambda item: item["published_at"], reverse=True)
    if selected_symbols:
        items = [item for item in items if any(s in selected_symbols for s in item["symbols"])]
    return items
