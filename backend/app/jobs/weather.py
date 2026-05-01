"""Background weather snapshot refresh jobs."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.models import UserProfile
from app.services.context import ContextService


@celery_app.task(name="app.jobs.weather.sync_daily_weather_snapshots")
def sync_daily_weather_snapshots() -> dict[str, int | str]:
    """Refresh a small set of user weather snapshots once per day."""
    return asyncio.run(_sync_daily_weather_snapshots())


async def _sync_daily_weather_snapshots(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    context_service: ContextService | None = None,
) -> dict[str, int | str]:
    context_service = context_service or ContextService()
    if not context_service.qweather.enabled:
        return {"status": "skipped", "reason": "weather provider is not configured", "refreshed_count": 0}

    session_factory = session_factory or get_sessionmaker()
    async with session_factory() as session:
        profiles = (await session.scalars(select(UserProfile))).all()

    locations = _collect_weather_locations(profiles)
    refreshed = 0
    failed = 0
    for location in locations:
        try:
            await context_service.weather_snapshot(location=location, allow_refresh=True)
            refreshed += 1
        except Exception:
            failed += 1

    return {
        "status": "ok",
        "refreshed_count": refreshed,
        "failed_count": failed,
    }


def _collect_weather_locations(profiles: list[UserProfile]) -> list[str]:
    seen: set[str] = set()
    locations: list[str] = []
    for profile in profiles:
        for location in (profile.home_location_coords, profile.work_location_coords):
            if not location:
                continue
            key = location.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            locations.append(location)
    return locations
