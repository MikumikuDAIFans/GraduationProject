"""Map and weather context routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import ContextService, get_context_service
from app.api.schemas import GeocodeRead, TravelEstimateRead, WeatherNowRead

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/geocode", response_model=GeocodeRead)
async def geocode_address(
    address: str = Query(..., min_length=1),
    city: str | None = Query(default=None),
    service: ContextService = Depends(get_context_service),
) -> GeocodeRead:
    return await service.geocode(address=address, city=city)


@router.get("/travel", response_model=TravelEstimateRead)
async def estimate_travel(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
    city: str | None = Query(default=None),
    mode: str = Query(default="driving"),
    service: ContextService = Depends(get_context_service),
) -> TravelEstimateRead:
    return await service.estimate_travel(
        origin=origin,
        destination=destination,
        city=city,
        mode=mode,
    )


@router.get("/weather/now", response_model=WeatherNowRead)
async def weather_now(
    location: str = Query(..., min_length=1),
    service: ContextService = Depends(get_context_service),
) -> WeatherNowRead:
    return await service.weather_now(location=location)
