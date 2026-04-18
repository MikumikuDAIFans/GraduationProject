"""Amap Web Service helpers."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class AmapClient:
    """Minimal Amap client for geocoding and route estimates."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = "https://restapi.amap.com"

    @property
    def enabled(self) -> bool:
        return self.settings.map_provider == "amap" and bool(self.settings.map_api_key)

    async def geocode(self, address: str, city: str | None = None) -> dict[str, Any]:
        self._ensure_enabled()
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{self.base_url}/v3/geocode/geo",
                params={
                    "key": self.settings.map_api_key,
                    "address": address,
                    "city": city,
                },
            )
            response.raise_for_status()
            data = response.json()
        self._ensure_success(data)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            raise RuntimeError("Amap geocode returned no results.")
        item = geocodes[0]
        return {
            "formatted_address": item.get("formatted_address") or address,
            "location": item.get("location"),
            "province": item.get("province"),
            "city": item.get("city"),
            "district": item.get("district"),
        }

    async def estimate_route(
        self,
        *,
        origin: str,
        destination: str,
        city: str | None = None,
        mode: str = "driving",
    ) -> dict[str, Any]:
        self._ensure_enabled()
        origin_location = await self._resolve_location(origin, city)
        destination_location = await self._resolve_location(destination, city)
        endpoint = "/v3/direction/driving" if mode != "walking" else "/v3/direction/walking"

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{self.base_url}{endpoint}",
                params={
                    "key": self.settings.map_api_key,
                    "origin": origin_location,
                    "destination": destination_location,
                },
            )
            response.raise_for_status()
            data = response.json()

        self._ensure_success(data)
        route = data.get("route") or {}
        paths = route.get("paths") or []
        if not paths:
            raise RuntimeError("Amap route returned no paths.")

        path = paths[0]
        duration_seconds = int(path.get("duration", 0))
        distance_meters = int(path.get("distance", 0))
        return {
            "origin": origin,
            "destination": destination,
            "origin_location": origin_location,
            "destination_location": destination_location,
            "mode": mode,
            "duration_seconds": duration_seconds,
            "duration_minutes": round(duration_seconds / 60, 1),
            "distance_meters": distance_meters,
            "distance_km": round(distance_meters / 1000, 2),
        }

    async def _resolve_location(self, text: str, city: str | None = None) -> str:
        if self._looks_like_coordinates(text):
            return text
        geocoded = await self.geocode(text, city)
        location = geocoded.get("location")
        if not location:
            raise RuntimeError(f"Amap could not resolve location for {text!r}.")
        return str(location)

    def _looks_like_coordinates(self, text: str) -> bool:
        parts = [part.strip() for part in text.split(",")]
        if len(parts) != 2 or any(not part for part in parts):
            return False
        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            return False
        return -180 <= lng <= 180 and -90 <= lat <= 90

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("Amap is not configured.")

    def _ensure_success(self, payload: dict[str, Any]) -> None:
        if payload.get("status") != "1":
            raise RuntimeError(payload.get("info") or "Amap request failed.")
