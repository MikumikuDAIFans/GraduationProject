"""QWeather API helpers."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class QWeatherClient:
    """Minimal QWeather client for current weather lookup."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return (
            self.settings.weather_provider == "qweather"
            and bool(self.settings.qweather_api_key)
            and bool(self.settings.qweather_api_host)
        )

    async def get_weather_now(self, *, location: str) -> dict[str, Any]:
        self._ensure_enabled()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{self.settings.qweather_api_host}/v7/weather/now",
                params={
                    "location": location,
                    "key": self.settings.qweather_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != "200":
            raise RuntimeError(f"QWeather request failed with code {data.get('code')}.")

        now = data.get("now") or {}
        return {
            "location": location,
            "obs_time": now.get("obsTime"),
            "temp": now.get("temp"),
            "feels_like": now.get("feelsLike"),
            "text": now.get("text"),
            "wind_dir": now.get("windDir"),
            "wind_scale": now.get("windScale"),
            "humidity": now.get("humidity"),
            "precip": now.get("precip"),
            "vis": now.get("vis"),
        }

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("QWeather is not configured.")
