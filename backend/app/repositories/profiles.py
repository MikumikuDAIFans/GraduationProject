"""User profile repository."""

from __future__ import annotations

from app.models import UserProfile
from app.repositories.base import AsyncRepository


class UserProfileRepository(AsyncRepository[UserProfile]):
    """Persistence helpers for the local user profile."""

    model = UserProfile

    async def get_profile(self, user_id: str) -> UserProfile:
        return await self.get_or_create_user(user_id)

    async def update_profile(self, user_id: str, payload: dict) -> UserProfile:
        profile = await self.get_or_create_user(user_id)
        return await self.update(profile, payload)
