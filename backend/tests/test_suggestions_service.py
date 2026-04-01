from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from app.services.suggestions import SuggestionService


def test_compute_gaps_for_date_respects_profile_window() -> None:
    service = SuggestionService()
    events = [
        SimpleNamespace(
            start_time=datetime.fromisoformat("2026-03-26T10:00:00"),
            end_time=datetime.fromisoformat("2026-03-26T11:00:00"),
        ),
        SimpleNamespace(
            start_time=datetime.fromisoformat("2026-03-26T14:00:00"),
            end_time=datetime.fromisoformat("2026-03-26T15:00:00"),
        ),
    ]
    profile = SimpleNamespace(wake_up_time="09:30", sleep_time="21:00")

    gaps = service._compute_gaps_for_date(events=events, profile=profile, target_date=date(2026, 3, 26))

    assert gaps[0][0].hour == 9 and gaps[0][0].minute == 30
    assert gaps[0][1].hour == 10
    assert gaps[-1][1].hour == 21


def test_compute_gaps_deducts_buffer() -> None:
    service = SuggestionService()
    events = [
        SimpleNamespace(
            start_time=datetime(2026, 3, 26, 10, 0),
            end_time=datetime(2026, 3, 26, 11, 0),
            buffer_before=10,
            buffer_after=15,
        ),
    ]
    profile = SimpleNamespace(wake_up_time="08:00", sleep_time="22:00")

    gaps = service._compute_gaps_for_date(events=events, profile=profile, target_date=date(2026, 3, 26))

    assert gaps[0][0].hour == 8 and gaps[0][0].minute == 0
    assert gaps[0][1].hour == 9 and gaps[0][1].minute == 50
    assert gaps[1][0].hour == 11 and gaps[1][0].minute == 15
    assert gaps[1][1].hour == 22


async def _fake_weather_now(*, location: str):
    return SimpleNamespace(text="Sunny", temp="18", humidity="33")


async def _fake_rainy_weather_now(*, location: str):
    return SimpleNamespace(text="Rain", temp="16", humidity="80")


async def _fake_search_poi(*, keyword: str, location, radius: int):
    return [
        {
            "name": "星巴克",
            "address": "Campus Road 1",
            "location": "116.3974,39.9080",
            "distance": "500",
        }
    ]


def test_build_context_suggestions_includes_departure_and_weather() -> None:
    service = SuggestionService()
    service.context_service.weather_now = _fake_weather_now  # type: ignore[method-assign]
    today = date.today()

    events = [
        SimpleNamespace(
            id=1,
            title="Defense rehearsal",
            location_name="Campus",
            departure_time=datetime.combine(today, datetime.min.time()).replace(hour=9),
            start_time=datetime.combine(today, datetime.min.time()).replace(hour=10),
            end_time=datetime.combine(today, datetime.min.time()).replace(hour=11),
            travel_duration_minutes=60,
        )
    ]
    profile = SimpleNamespace(home_location_coords="116.397,39.908")

    import asyncio

    suggestions = asyncio.run(
        service._build_context_suggestions(events=events, profile=profile, dates=[today])
    )

    types = [item.type for item in suggestions]
    assert "departure_plan" in types
    assert "weather_watch" in types


def test_build_context_suggestions_includes_location_break() -> None:
    service = SuggestionService()
    service.maps_client.amap.settings.map_api_key = "test-key"
    service.maps_client.search_poi = _fake_search_poi  # type: ignore[method-assign]
    today = date.today()

    events = []
    profile = SimpleNamespace(
        home_location_coords="116.397,39.908",
        wake_up_time="08:00",
        sleep_time="22:00",
    )

    import asyncio

    suggestions = asyncio.run(
        service._build_context_suggestions(events=events, profile=profile, dates=[today])
    )

    types = [item.type for item in suggestions]
    assert "location_based_break" in types


def test_build_context_suggestions_includes_weather_alert_for_outdoor_event() -> None:
    service = SuggestionService()
    service.context_service.weather_now = _fake_rainy_weather_now  # type: ignore[method-assign]
    today = date.today()
    events = [
        SimpleNamespace(
            id=1,
            title="Campus run",
            location_name="Outdoor track",
            departure_time=None,
            start_time=datetime.combine(today, datetime.min.time()).replace(hour=10),
            end_time=datetime.combine(today, datetime.min.time()).replace(hour=11),
            travel_duration_minutes=None,
        )
    ]
    profile = SimpleNamespace(home_location_coords="116.397,39.908")

    import asyncio

    suggestions = asyncio.run(
        service._build_context_suggestions(events=events, profile=profile, dates=[today])
    )

    types = [item.type for item in suggestions]
    assert "weather_alert" in types


def test_build_split_task_suggestions_creates_multiple_segments() -> None:
    service = SuggestionService()
    task = SimpleNamespace(
        id=5,
        content="Write thesis chapter",
        priority=3,
        can_split=True,
        preferred_period=None,
    )
    slots = [
        (
            datetime.fromisoformat("2026-03-28T09:00:00"),
            datetime.fromisoformat("2026-03-28T10:00:00"),
        ),
        (
            datetime.fromisoformat("2026-03-28T14:00:00"),
            datetime.fromisoformat("2026-03-28T15:30:00"),
        ),
    ]

    suggestions = service._build_split_task_suggestions(
        task=task,
        duration_minutes=120,
        focus_block_minutes=60,
        slots=slots,
        remaining_limit=4,
    )

    assert len(suggestions) == 2
    assert all(item.type == "task_split_slot" for item in suggestions)
    assert suggestions[0].segment_index == 1
    assert suggestions[1].segment_total == 2
    assert suggestions[0].split_group == suggestions[1].split_group


def test_build_split_task_suggestions_can_split_within_one_long_slot() -> None:
    service = SuggestionService()
    task = SimpleNamespace(
        id=6,
        content="Deep research",
        priority=3,
        can_split=True,
        preferred_period=None,
    )
    slots = [
        (
            datetime.fromisoformat("2026-03-28T13:00:00"),
            datetime.fromisoformat("2026-03-28T16:30:00"),
        ),
    ]

    suggestions = service._build_split_task_suggestions(
        task=task,
        duration_minutes=180,
        focus_block_minutes=60,
        slots=slots,
        remaining_limit=6,
    )

    assert len(suggestions) == 3
    assert suggestions[0].start_time.isoformat().startswith("2026-03-28T13:00:00")
    assert suggestions[1].segment_index == 2
    assert suggestions[2].segment_total == 3


def test_build_task_slot_suggestions_respects_preferred_period() -> None:
    service = SuggestionService()
    task = SimpleNamespace(
        id=8,
        content="Prepare demo slides",
        priority=3,
        can_split=False,
        preferred_period="evening",
        estimated_duration_minutes=60,
        deadline=None,
    )
    profile = SimpleNamespace(
        wake_up_time="08:00",
        sleep_time="22:00",
        preferences_json={"focus_block_minutes": 60},
    )
    events = []
    dates = [date(2026, 3, 28)]

    suggestions = service._build_task_slot_suggestions(
        events=events,
        profile=profile,
        tasks=[task],
        dates=dates,
        limit=3,
    )

    assert len(suggestions) == 1
    assert suggestions[0].start_time.hour >= 18


def test_build_task_slot_suggestions_uses_remaining_minutes_and_replan_type() -> None:
    service = SuggestionService()
    task = SimpleNamespace(
        id=9,
        content="Write thesis chapter",
        priority=3,
        can_split=False,
        preferred_period=None,
        estimated_duration_minutes=180,
        deadline=None,
    )
    profile = SimpleNamespace(
        wake_up_time="08:00",
        sleep_time="22:00",
        preferences_json={"focus_block_minutes": 60},
    )
    dates = [date(2026, 3, 28)]
    events = [
        SimpleNamespace(
            linked_task_id=9,
            status="completed",
            start_time=datetime.fromisoformat("2026-03-28T09:00:00"),
            end_time=datetime.fromisoformat("2026-03-28T10:00:00"),
        ),
        SimpleNamespace(
            linked_task_id=9,
            status="canceled",
            start_time=datetime.fromisoformat("2026-03-28T10:05:00"),
            end_time=datetime.fromisoformat("2026-03-28T11:05:00"),
        ),
    ]
    task_progress = service._task_progress_map(events=events)

    suggestions = service._build_task_slot_suggestions(
        events=[],
        profile=profile,
        tasks=[task],
        task_progress=task_progress,
        dates=dates,
        limit=3,
    )

    assert len(suggestions) == 1
    assert suggestions[0].type == "task_replan_slot"
    assert suggestions[0].estimated_minutes == 120
