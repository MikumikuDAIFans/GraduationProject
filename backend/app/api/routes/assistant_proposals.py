"""Assistant proposal routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_current_user_id
from app.api.live_updates import broadcast_workspace_update
from app.api.schemas import (
    AssistantProposalConfirmRequest,
    AssistantProposalListRead,
    AssistantProposalRead,
    AssistantProposalReviseRequest,
)
from app.services.assistant_proposal_manager import AssistantProposalManager


router = APIRouter(prefix="/assistant/proposals", tags=["assistant"])


def get_proposal_manager() -> AssistantProposalManager:
    return AssistantProposalManager()


@router.get("", response_model=AssistantProposalListRead)
async def list_proposals(
    statuses: list[str] | None = Query(default=None, alias="status"),
    session_id: int | None = Query(default=None, ge=1),
    proposal_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalListRead:
    items = await manager.list_proposals(
        user_id=user_id,
        session_id=session_id,
        statuses=statuses,
        proposal_type=proposal_type,
        limit=limit,
    )
    return AssistantProposalListRead(items=list(items), total=len(items))


@router.get("/{proposal_id}", response_model=AssistantProposalRead)
async def get_proposal(
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    return await manager.get_proposal(user_id=user_id, proposal_id=proposal_id)


@router.post("/{proposal_id}/confirm", response_model=AssistantProposalRead)
async def confirm_proposal(
    payload: AssistantProposalConfirmRequest,
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    proposal = await manager.confirm_proposal(user_id=user_id, proposal_id=proposal_id, option_id=payload.option_id)
    await broadcast_workspace_update(user_id)
    return proposal


@router.post("/{proposal_id}/reject", response_model=AssistantProposalRead)
async def reject_proposal(
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    return await manager.reject_proposal(user_id=user_id, proposal_id=proposal_id)


@router.post("/{proposal_id}/revise", response_model=AssistantProposalRead)
async def revise_proposal(
    payload: AssistantProposalReviseRequest,
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    return await manager.revise_proposal(user_id=user_id, proposal_id=proposal_id, message=payload.message)


@router.post("/{proposal_id}/retry", response_model=AssistantProposalRead)
async def retry_proposal(
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    proposal = await manager.retry_proposal(user_id=user_id, proposal_id=proposal_id)
    await broadcast_workspace_update(user_id)
    return proposal


@router.post("/{proposal_id}/expire", response_model=AssistantProposalRead)
async def expire_proposal(
    proposal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantProposalManager = Depends(get_proposal_manager),
) -> AssistantProposalRead:
    return await manager.expire_proposal(user_id=user_id, proposal_id=proposal_id)
