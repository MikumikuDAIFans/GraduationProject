"""User profile routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

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
    profile = await service.update_profile(user_id=user_id, payload=payload)
    await broadcast_workspace_update(user_id)
    return profile
