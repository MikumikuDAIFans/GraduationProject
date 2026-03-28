"""External context service for map and weather enrichment."""

from __future__ import annotations

from app.api.schemas import GeocodeRead, TravelEstimateRead, WeatherNowRead
from app.tools.amap import AmapClient
from app.tools.qweather import QWeatherClient


class ContextService:
    """Wrap external map/weather clients into API-friendly methods."""

    def __init__(self) -> None:
        self.amap = AmapClient()
        self.qweather = QWeatherClient()

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
