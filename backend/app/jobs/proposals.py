"""Assistant proposal maintenance jobs."""

from __future__ import annotations

import asyncio

from app.core.celery_app import celery_app
from app.services.assistant_proposal_manager import AssistantProposalManager


@celery_app.task(name="app.jobs.proposals.expire_due_assistant_proposals")
def expire_due_assistant_proposals() -> dict[str, int]:
    """Expire pending assistant proposals that have passed their expiry time."""
    return asyncio.run(_expire_due_assistant_proposals())


async def _expire_due_assistant_proposals() -> dict[str, int]:
    manager = AssistantProposalManager(execute_on_confirm=False)
    expired = await manager.expire_due_proposals(limit=200)
    return {"expired_count": len(expired)}
