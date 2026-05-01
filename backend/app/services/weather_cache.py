"""Small persistent weather snapshot cache for assistant context."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class WeatherSnapshotCache:
    """File-backed cache keyed by weather lookup location.

    The cache is intentionally simple: weather is context for assistant
    suggestions, not an execution authority, so a small JSON file is enough for
    V1 and avoids another migration.
    """

    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = path or settings.weather_cache_file

    def get(self, location: str) -> dict[str, Any] | None:
        key = self._key(location)
        if not key:
            return None
        return self._read().get(key)

    def set(self, location: str, weather: dict[str, Any], *, fetched_at: datetime | None = None) -> dict[str, Any]:
        key = self._key(location)
        if not key:
            raise ValueError("location is required")
        fetched_at = self._as_utc(fetched_at or datetime.now(timezone.utc))
        data = self._read()
        entry = {
            "location": location,
            "fetched_at": fetched_at.isoformat(),
            "weather": weather,
        }
        data[key] = entry
        self._write(data)
        return entry

    def is_stale(self, entry: dict[str, Any] | None, *, max_age: timedelta) -> bool:
        if not entry:
            return True
        fetched_at = self._parse_datetime(entry.get("fetched_at"))
        if fetched_at is None:
            return True
        return datetime.now(timezone.utc) - fetched_at > max_age

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _key(location: str) -> str:
        return location.strip().lower()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return WeatherSnapshotCache._as_utc(parsed)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
