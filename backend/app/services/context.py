"""External context service for map and weather enrichment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.schemas import GeocodeRead, TravelEstimateRead, WeatherNowRead, WeatherSnapshotRead
from app.core.config import get_settings
from app.services.weather_cache import WeatherSnapshotCache
from app.tools.amap import AmapClient
from app.tools.qweather import QWeatherClient


class ContextService:
    """Wrap external map/weather clients into API-friendly methods."""

    def __init__(self) -> None:
        self.amap = AmapClient()
        self.qweather = QWeatherClient()
        self.settings = get_settings()
        self.weather_cache = WeatherSnapshotCache()

    async def geocode(self, address: str, city: str | None = None) -> GeocodeRead:
        payload = await self.amap.geocode(address=address, city=city)
        return GeocodeRead.model_validate(payload)

    async def estimate_travel(
        self,
        *,
        origin: str,
        destination: str,
        city: str | None = None,
        mode: str = "driving",
    ) -> TravelEstimateRead:
        payload = await self.amap.estimate_route(
            origin=origin,
            destination=destination,
            city=city,
            mode=mode,
        )
        return TravelEstimateRead.model_validate(payload)

    async def weather_now(self, *, location: str) -> WeatherNowRead:
        payload = await self.qweather.get_weather_now(location=location)
        return WeatherNowRead.model_validate(payload)

    async def weather_snapshot(self, *, location: str, allow_refresh: bool = False) -> WeatherSnapshotRead:
        max_age = timedelta(hours=self.settings.weather_snapshot_max_age_hours)
        cached = self.weather_cache.get(location)
        if cached is not None and (not allow_refresh or not self.weather_cache.is_stale(cached, max_age=max_age)):
            return self._snapshot_from_cache(location=location, cached=cached, max_age=max_age)

        if not allow_refresh:
            if cached is not None:
                return self._snapshot_from_cache(location=location, cached=cached, max_age=max_age)
            return WeatherSnapshotRead(
                location=location,
                source="missing",
                is_stale=True,
                max_age_hours=self.settings.weather_snapshot_max_age_hours,
            )

        payload = await self.qweather.get_weather_now(location=location)
        entry = self.weather_cache.set(location, payload)
        return WeatherSnapshotRead(
            location=location,
            source="live",
            fetched_at=self._parse_datetime(entry.get("fetched_at")),
            is_stale=False,
            max_age_hours=self.settings.weather_snapshot_max_age_hours,
            weather=WeatherNowRead.model_validate(payload),
        )

    def _snapshot_from_cache(
        self,
        *,
        location: str,
        cached: dict,
        max_age: timedelta,
    ) -> WeatherSnapshotRead:
        weather = cached.get("weather")
        return WeatherSnapshotRead(
            location=location,
            source="cache",
            fetched_at=self._parse_datetime(cached.get("fetched_at")),
            is_stale=self.weather_cache.is_stale(cached, max_age=max_age),
            max_age_hours=self.settings.weather_snapshot_max_age_hours,
            weather=WeatherNowRead.model_validate(weather) if isinstance(weather, dict) else None,
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
