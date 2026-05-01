"""User profile routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
import time
from loguru import logger

from app.api.live_updates import broadcast_workspace_update
from app.api.deps import UserProfileService, get_current_user_id, get_profile_service
from app.api.schemas import UserProfileRead, UserProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=UserProfileRead)
async def get_profile(
    user_id: str = Depends(get_current_user_id),
    service: UserProfileService = Depends(get_profile_service),
) -> UserProfileRead:
    return await service.get_profile(user_id=user_id)


@router.put("", response_model=UserProfileRead)
async def update_profile(
    payload: UserProfileUpdate,
    user_id: str = Depends(get_current_user_id),
    service: UserProfileService = Depends(get_profile_service),
) -> UserProfileRead:
    start_time = time.perf_counter()
    profile = await service.update_profile(user_id=user_id, payload=payload)
    biz_time = time.perf_counter() - start_time

    bc_start = time.perf_counter()
    await broadcast_workspace_update(user_id)
    bc_time = time.perf_counter() - bc_start

    logger.bind(component="profile").info(
        "PUT /api/profile profiling | Biz: {biz:.2f}ms | BroadcastTrigger: {bc:.2f}ms",
        biz=biz_time * 1000, bc=bc_time * 1000
    )
    return profile
