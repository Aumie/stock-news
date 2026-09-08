from views.feed_pagination import next_page_cursor

ITEM_A = {"article_id": "a", "published_at": "2026-09-20T00:00:00+00:00"}
ITEM_B = {"article_id": "b", "published_at": "2026-09-01T00:00:00+00:00"}


def test_next_page_cursor_uses_oldest_item_when_sorted_descending():
    cursor = next_page_cursor([ITEM_A, ITEM_B])

    assert cursor == ("2026-09-01T00:00:00+00:00", "b")


def test_next_page_cursor_is_none_for_empty_list():
    assert next_page_cursor([]) is None
