"""Suggestion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SuggestionService, get_current_user_id, get_suggestion_service
from app.api.schemas import SuggestionList

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("/today", response_model=SuggestionList)
async def get_today_suggestions(
    user_id: str = Depends(get_current_user_id),
    service: SuggestionService = Depends(get_suggestion_service),
) -> SuggestionList:
    return await service.get_today_suggestions(user_id=user_id)


@router.get("/next", response_model=SuggestionList)
async def get_next_suggestions(
    user_id: str = Depends(get_current_user_id),
    service: SuggestionService = Depends(get_suggestion_service),
) -> SuggestionList:
    return await service.get_next_suggestions(user_id=user_id)
