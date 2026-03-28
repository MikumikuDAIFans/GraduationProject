"""User profile service layer."""

from __future__ import annotations

from app.api.schemas import UserProfileRead, UserProfileUpdate
from app.db.session import get_sessionmaker
from app.repositories.profiles import UserProfileRepository
from app.services.context import ContextService


class UserProfileService:
    """Read and update the local user profile."""

    def __init__(self) -> None:
        self.repository = UserProfileRepository(get_sessionmaker())
        self.context_service = ContextService()

    async def get_profile(self, user_id: str) -> UserProfileRead:
        profile = await self.repository.get_profile(user_id)
        return UserProfileRead.model_validate(profile)

    async def update_profile(self, user_id: str, payload: UserProfileUpdate) -> UserProfileRead:
        data = payload.model_dump(exclude_none=True)

        home_name = data.get("home_location_name")
        if home_name and not data.get("home_location_coords"):
            try:
                geocoded = await self.context_service.geocode(home_name)
                data["home_location_coords"] = geocoded.location
            except Exception:
                pass

        work_name = data.get("work_location_name")
        if work_name and not data.get("work_location_coords"):
            try:
                geocoded = await self.context_service.geocode(work_name)
                data["work_location_coords"] = geocoded.location
            except Exception:
                pass

        profile = await self.repository.update_profile(user_id, data)
        return UserProfileRead.model_validate(profile)
