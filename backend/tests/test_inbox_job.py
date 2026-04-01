from __future__ import annotations


def test_generate_proactive_inbox_items_is_callable() -> None:
    from app.jobs.inbox import generate_proactive_inbox_items

    assert callable(generate_proactive_inbox_items)
