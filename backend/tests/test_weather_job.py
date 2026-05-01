from __future__ import annotations

from app.jobs.weather import _collect_weather_locations
from app.models import UserProfile


def test_collect_weather_locations_uses_unique_profile_coordinates() -> None:
    locations = _collect_weather_locations(
        [
            UserProfile(
                username="local-user",
                home_location_coords="116.40,39.90",
                work_location_coords="116.40,39.90",
            ),
            UserProfile(
                username="other-user",
                home_location_coords="121.47,31.23",
            ),
        ]
    )

    assert locations == ["116.40,39.90", "121.47,31.23"]
