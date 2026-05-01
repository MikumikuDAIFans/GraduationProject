from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.context import ContextService
from app.services.weather_cache import WeatherSnapshotCache


def test_weather_snapshot_cache_marks_stale_entries(tmp_path: Path) -> None:
    cache = WeatherSnapshotCache(tmp_path / "weather.json")
    entry = cache.set(
        "116.40,39.90",
        {"location": "116.40,39.90", "temp": 20, "text": "Sunny"},
        fetched_at=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert cache.get("116.40,39.90") == entry
    assert cache.is_stale(entry, max_age=timedelta(hours=1))


def test_context_weather_snapshot_uses_cache_without_refresh(tmp_path: Path) -> None:
    async def scenario() -> None:
        service = ContextService()
        service.weather_cache = WeatherSnapshotCache(tmp_path / "weather.json")
        service.weather_cache.set(
            "116.40,39.90",
            {"location": "116.40,39.90", "temp": 22, "text": "Cloudy"},
            fetched_at=datetime.now(timezone.utc),
        )

        snapshot = await service.weather_snapshot(location="116.40,39.90", allow_refresh=False)

        assert snapshot.source == "cache"
        assert snapshot.weather is not None
        assert snapshot.weather.text == "Cloudy"
        assert snapshot.is_stale is False

    asyncio.run(scenario())
