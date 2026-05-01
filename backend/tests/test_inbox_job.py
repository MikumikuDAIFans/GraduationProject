from __future__ import annotations


def test_generate_proactive_inbox_items_is_callable() -> None:
    from app.jobs.inbox import generate_proactive_inbox_items

    assert callable(generate_proactive_inbox_items)


def test_legacy_inbox_job_is_disabled_by_default() -> None:
    import asyncio

    from app.jobs.inbox import _generate_proactive_inbox_items

    result = asyncio.run(_generate_proactive_inbox_items())

    assert result["status"] == "skipped"
    assert result["generated_count"] == 0
