"""Higher-level map service integration for location-aware features."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.tools.amap import AmapClient


class MapsClient:
    """Facade around Amap geocoding, route estimation, and POI search."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.amap = AmapClient()
        self.base_url = "https://restapi.amap.com/v3"

    @property
    def enabled(self) -> bool:
        return self.amap.enabled

    async def geocode_address(self, address: str) -> tuple[float, float] | None:
        payload = await self.amap.geocode(address=address)
        location = payload.get("location")
        if not location or "," not in location:
            return None
        lng, lat = location.split(",", 1)
        return (float(lat), float(lng))

    async def calculate_route_time(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "driving",
    ) -> int:
        if not self.enabled:
            return 0

        origin_text = f"{origin[1]},{origin[0]}"
        destination_text = f"{destination[1]},{destination[0]}"
        payload = await self.amap.estimate_route(origin=origin_text, destination=destination_text, mode=mode)
        return int(round(payload.get("duration_minutes", 0)))

    async def search_poi(
        self,
        keyword: str,
        location: tuple[float, float] | None = None,
        radius: int = 5000,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        params: dict[str, Any] = {
            "key": self.settings.map_api_key,
            "keywords": keyword,
            "radius": radius,
            "offset": 10,
            "page": 1,
            "extensions": "base",
        }
        if location is not None:
            params["location"] = f"{location[1]},{location[0]}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/place/text", params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "1":
            return []

        pois = data.get("pois") or []
        return [
            {
                "name": poi.get("name"),
                "address": poi.get("address"),
                "location": poi.get("location"),
                "distance": poi.get("distance"),
            }
            for poi in pois[:10]
        ]
