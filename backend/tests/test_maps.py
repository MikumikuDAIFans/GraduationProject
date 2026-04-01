from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.tools.maps import MapsClient


def test_calculate_route_time() -> None:
    client = MapsClient()
    client.settings.map_api_key = "test-key"
    client.amap.settings.map_api_key = "test-key"
    client.amap.estimate_route = AsyncMock(return_value={"duration_minutes": 30})  # type: ignore[method-assign]

    duration = asyncio.run(
        client.calculate_route_time(
            origin=(39.9042, 116.4074),
            destination=(31.2304, 121.4737),
            mode="driving",
        )
    )

    assert duration == 30


def test_search_poi() -> None:
    client = MapsClient()
    client.settings.map_api_key = "test-key"
    client.amap.settings.map_api_key = "test-key"
    response_payload = {
        "status": "1",
        "pois": [
            {
                "name": "星巴克",
                "address": "某某路 1 号",
                "location": "116.4074,39.9042",
                "distance": "500",
            }
        ],
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return response_payload

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str, params=None):
            return FakeResponse()

    with patch("app.tools.maps.httpx.AsyncClient", FakeAsyncClient):
        pois = asyncio.run(
            client.search_poi(
                keyword="咖啡",
                location=(39.9042, 116.4074),
                radius=1000,
            )
        )

    assert len(pois) == 1
    assert pois[0]["name"] == "星巴克"
