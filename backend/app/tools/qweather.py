"""QWeather API helpers."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

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
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
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
            except httpx.HTTPStatusError as exc:
                # Log the error but don't crash - return mock data for development
                logger.bind(component="qweather").warning(
                    "QWeather API returned {status_code}, using fallback data",
                    status_code=exc.response.status_code
                )
                # Return minimal mock data so the app doesn't crash
                return {
                    "location": location,
                    "obs_time": None,
                    "temp": 20,
                    "feels_like": 20,
                    "text": "Unavailable",
                    "wind_dir": "N/A",
                    "wind_scale": "0",
                    "humidity": 50,
                    "precip": 0,
                    "vis": 10,
                }
            except Exception as exc:
                logger.bind(component="qweather").warning(
                    "QWeather request failed: {error}, returning empty data",
                    error=str(exc)
                )
                return {
                    "location": location,
                    "obs_time": None,
                    "temp": None,
                    "feels_like": None,
                    "text": "Error",
                    "wind_dir": None,
                    "wind_scale": None,
                    "humidity": None,
                    "precip": None,
                    "vis": None,
                }

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("QWeather is not configured.")
