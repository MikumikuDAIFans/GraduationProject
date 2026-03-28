"""Assistant routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import AssistantService, get_assistant_service, get_current_user_id
from app.api.schemas import AssistantCurrentSessionRead, AssistantInboxRead, AssistantMessageCreate, AssistantResponse, AssistantSessionRead, AssistantSummaryRead

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/message", response_model=AssistantResponse)
async def send_message(
    payload: AssistantMessageCreate,
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantResponse:
    return await service.send_message(user_id=user_id, payload=payload)


@router.get("/sessions/{session_id}", response_model=AssistantSessionRead)
async def get_session(
    session_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSessionRead:
    return await service.get_session(user_id=user_id, session_id=session_id)


@router.get("/inbox", response_model=AssistantInboxRead)
async def get_inbox(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantInboxRead:
    return await service.get_inbox(user_id=user_id)


@router.get("/current", response_model=AssistantCurrentSessionRead)
async def get_current_session(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantCurrentSessionRead:
    return await service.get_current_session(user_id=user_id)


@router.get("/summary", response_model=AssistantSummaryRead)
async def get_summary(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSummaryRead:
    return await service.get_summary(user_id=user_id)


@router.post("/inbox/{item_id}", response_model=AssistantInboxRead)
async def update_inbox_item(
    item_id: str = Path(...),
    action: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantInboxRead:
    return await service.mark_inbox_item(user_id=user_id, item_id=item_id, action=action)
