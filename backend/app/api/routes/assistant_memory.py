"""Assistant long-term memory routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user_id
from app.api.schemas import (
    AssistantMemoryCandidateCreate,
    AssistantMemoryCandidateListRead,
    AssistantMemoryCandidateRead,
    AssistantMemoryRead,
)
from app.services.assistant_memory import AssistantMemoryService


router = APIRouter(prefix="/assistant/memory", tags=["assistant-memory"])


def get_memory_service() -> AssistantMemoryService:
    return AssistantMemoryService()


@router.get("", response_model=AssistantMemoryRead)
async def get_memory(
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryRead:
    return await service.read_memory(user_id=user_id)


@router.get("/candidates", response_model=AssistantMemoryCandidateListRead)
async def list_memory_candidates(
    status: list[str] | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryCandidateListRead:
    candidates = await service.list_candidates(
        user_id=user_id,
        statuses=status,
        memory_type=memory_type,
        limit=limit,
    )
    return AssistantMemoryCandidateListRead(
        items=[AssistantMemoryCandidateRead.model_validate(candidate) for candidate in candidates],
        total=len(candidates),
    )


@router.post("/candidates", response_model=AssistantMemoryCandidateRead)
async def create_memory_candidate(
    payload: AssistantMemoryCandidateCreate,
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryCandidateRead:
    candidate = await service.create_candidate(user_id=user_id, payload=payload)
    return AssistantMemoryCandidateRead.model_validate(candidate)


@router.get("/candidates/{candidate_id}", response_model=AssistantMemoryCandidateRead)
async def get_memory_candidate(
    candidate_id: int,
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryCandidateRead:
    candidate = await service.get_candidate(user_id=user_id, candidate_id=candidate_id)
    return AssistantMemoryCandidateRead.model_validate(candidate)


@router.post("/candidates/{candidate_id}/confirm", response_model=AssistantMemoryCandidateRead)
async def confirm_memory_candidate(
    candidate_id: int,
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryCandidateRead:
    candidate = await service.confirm_candidate(user_id=user_id, candidate_id=candidate_id)
    return AssistantMemoryCandidateRead.model_validate(candidate)


@router.post("/candidates/{candidate_id}/reject", response_model=AssistantMemoryCandidateRead)
async def reject_memory_candidate(
    candidate_id: int,
    user_id: str = Depends(get_current_user_id),
    service: AssistantMemoryService = Depends(get_memory_service),
) -> AssistantMemoryCandidateRead:
    candidate = await service.reject_candidate(user_id=user_id, candidate_id=candidate_id)
    return AssistantMemoryCandidateRead.model_validate(candidate)
