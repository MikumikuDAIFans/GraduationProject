"""Proposal lifecycle manager for the assistant redesign."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from loguru import logger

from app.api.schemas import AssistantProposalCreate
from app.assistant_agents.action_executor import AssistantActionExecutor
from app.db.session import get_sessionmaker
from app.models import AssistantProposal
from app.repositories.assistant_proposals import AssistantProposalRepository


TERMINAL_PROPOSAL_STATUSES = {"rejected", "expired", "superseded", "archived"}
DEFAULT_PROPOSAL_TTL = timedelta(hours=24)


class AssistantProposalManager:
    """Own proposal state transitions and confirmed execution handoff."""

    def __init__(
        self,
        repository: AssistantProposalRepository | None = None,
        *,
        executor: AssistantActionExecutor | None = None,
        execute_on_confirm: bool = True,
    ) -> None:
        self.repository = repository or AssistantProposalRepository(get_sessionmaker())
        self.executor = executor
        self.execute_on_confirm = execute_on_confirm

    async def create_proposal(self, *, user_id: str, payload: AssistantProposalCreate) -> AssistantProposal:
        payload_data = payload.model_dump()
        if payload_data.get("status") in {None, "draft", "pending"} and payload_data.get("expires_at") is None:
            payload_data["expires_at"] = datetime.now(timezone.utc) + DEFAULT_PROPOSAL_TTL

        if payload.dedup_key:
            existing = await self.repository.get_active_by_dedup_key(user_id=user_id, dedup_key=payload.dedup_key)
            if existing is not None:
                existing = await self._expire_if_due(user_id=user_id, proposal=existing)
                if existing.status != "expired":
                    logger.info(
                        "assistant proposal dedup hit user_id={} dedup_key={} proposal_id={} status={}",
                        user_id,
                        payload.dedup_key,
                        existing.id,
                        existing.status,
                    )
                    return existing

        proposal = await self.repository.create_proposal({"user_id": user_id, **payload_data})
        logger.info(
            "assistant proposal created user_id={} proposal_id={} type={} status={} dedup_key={}",
            user_id,
            proposal.id,
            proposal.proposal_type,
            proposal.status,
            proposal.dedup_key,
        )
        return proposal

    async def list_proposals(
        self,
        *,
        user_id: str,
        statuses: list[str] | None = None,
        proposal_type: str | None = None,
        limit: int = 50,
    ) -> list[AssistantProposal]:
        await self.expire_due_proposals(user_id=user_id, limit=100)
        return await self.repository.list_proposals(
            user_id=user_id,
            statuses=statuses,
            proposal_type=proposal_type,
            limit=limit,
        )

    async def get_proposal(self, *, user_id: str, proposal_id: int) -> AssistantProposal:
        proposal = await self.repository.get_proposal(proposal_id, user_id=user_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        return proposal

    async def confirm_proposal(self, *, user_id: str, proposal_id: int, option_id: str) -> AssistantProposal:
        proposal = await self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        proposal = await self._expire_if_due(user_id=user_id, proposal=proposal)
        self._ensure_confirmable(proposal)
        self._ensure_option_exists(proposal, option_id)

        if proposal.status in {"accepted", "execution_pending", "executed"}:
            if proposal.selected_option_id and proposal.selected_option_id != option_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal already confirmed with another option")
            if proposal.status == "executed" or not self.execute_on_confirm:
                return proposal
            if proposal.status == "execution_pending":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal execution is already pending")
            return await self._execute_confirmed_proposal(user_id=user_id, proposal=proposal, option_id=option_id)

        if not self.execute_on_confirm:
            payload_json = self._execution_snapshot(proposal.payload_json or {}, option_id)
            updated = await self.repository.update_proposal(
                proposal.id,
                user_id=user_id,
                payload={
                    "status": "accepted",
                    "selected_option_id": option_id,
                    "confirmed_at": datetime.now(timezone.utc),
                    "payload_json": payload_json,
                },
            )
            if updated is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
            self._log_transition(proposal, updated, reason="confirm")
            return updated

        payload_json = self._execution_snapshot(proposal.payload_json or {}, option_id)
        updated = await self.repository.update_proposal(
            proposal.id,
            user_id=user_id,
            payload={
                "status": "accepted",
                "selected_option_id": option_id,
                "confirmed_at": datetime.now(timezone.utc),
                "payload_json": payload_json,
            },
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(proposal, updated, reason="confirm")
        return await self._execute_confirmed_proposal(user_id=user_id, proposal=updated, option_id=option_id)

    async def reject_proposal(self, *, user_id: str, proposal_id: int) -> AssistantProposal:
        proposal = await self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        proposal = await self._expire_if_due(user_id=user_id, proposal=proposal)
        if proposal.status in {"execution_pending", "executed"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal is already executing or executed")
        if proposal.status == "rejected":
            return proposal
        updated = await self.repository.update_proposal(proposal.id, user_id=user_id, payload={"status": "rejected"})
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(proposal, updated, reason="reject")
        return updated

    async def revise_proposal(self, *, user_id: str, proposal_id: int, message: str) -> AssistantProposal:
        proposal = await self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        proposal = await self._expire_if_due(user_id=user_id, proposal=proposal)
        if proposal.status in {"execution_pending", "executed"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal is already executing or executed")
        if proposal.status in TERMINAL_PROPOSAL_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"proposal is {proposal.status}")

        new_payload = deepcopy(proposal.payload_json or {})
        new_payload["revision_request"] = message
        new_payload["superseded_proposal_id"] = proposal.id

        revised = await self.repository.create_proposal(
            {
                "user_id": user_id,
                "session_id": proposal.session_id,
                "thread_state_id": proposal.thread_state_id,
                "proposal_type": proposal.proposal_type,
                "trigger_type": "user_message",
                "status": "pending",
                "priority": proposal.priority,
                "summary": f"{proposal.summary}（修改中）",
                "payload_json": new_payload,
                "recommended_option_id": proposal.recommended_option_id,
                "is_time_sensitive": proposal.is_time_sensitive,
                "related_task_id": proposal.related_task_id,
                "related_event_id": proposal.related_event_id,
                "source_signal_id": proposal.source_signal_id,
                "supersedes_proposal_id": proposal.id,
                "expires_at": proposal.expires_at,
                "followup_after": proposal.followup_after,
            }
        )
        superseded = await self.repository.update_proposal(proposal.id, user_id=user_id, payload={"status": "superseded"})
        if superseded is not None:
            self._log_transition(proposal, superseded, reason="revise")
        return revised

    async def retry_proposal(self, *, user_id: str, proposal_id: int) -> AssistantProposal:
        proposal = await self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        if proposal.status != "execution_failed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="only execution_failed proposals can be retried")
        if not proposal.selected_option_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal has no selected option")

        if not self.execute_on_confirm:
            payload_json = deepcopy(proposal.payload_json or {})
            execution = dict(payload_json.get("execution") or {})
            execution["status"] = "pending"
            execution["selected_option_id"] = proposal.selected_option_id
            execution["last_error"] = None
            execution["retry_count"] = int(execution.get("retry_count") or 0) + 1
            payload_json["execution"] = execution

            updated = await self.repository.update_proposal(
                proposal.id,
                user_id=user_id,
                payload={
                    "status": "execution_pending",
                    "execution_started_at": datetime.now(timezone.utc),
                    "execution_error": None,
                    "payload_json": payload_json,
                },
            )
            if updated is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
            self._log_transition(proposal, updated, reason="retry")
            return updated

        return await self._execute_confirmed_proposal(
            user_id=user_id,
            proposal=proposal,
            option_id=proposal.selected_option_id,
            is_retry=True,
        )

    async def expire_proposal(self, *, user_id: str, proposal_id: int) -> AssistantProposal:
        proposal = await self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        if proposal.status in {"executed", "archived"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal cannot be expired")
        updated = await self.repository.update_proposal(proposal.id, user_id=user_id, payload={"status": "expired"})
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(proposal, updated, reason="manual_expire")
        return updated

    async def expire_due_proposals(self, *, user_id: str | None = None, limit: int = 100) -> list[AssistantProposal]:
        now = datetime.now(timezone.utc)
        due = await self.repository.list_due_for_expiry(now=now, user_id=user_id, limit=limit)
        expired: list[AssistantProposal] = []
        for proposal in due:
            updated = await self.repository.update_proposal(proposal.id, user_id=proposal.user_id, payload={"status": "expired"})
            if updated is not None:
                self._log_transition(proposal, updated, reason="expiry")
                expired.append(updated)
        return expired

    def _ensure_confirmable(self, proposal: AssistantProposal) -> None:
        if proposal.status in TERMINAL_PROPOSAL_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"proposal is {proposal.status}")
        if proposal.status == "execution_failed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal failed execution; use retry")

    async def _expire_if_due(self, *, user_id: str, proposal: AssistantProposal) -> AssistantProposal:
        if proposal.status in TERMINAL_PROPOSAL_STATUSES or proposal.status in {"execution_pending", "executed"}:
            return proposal
        if not self._is_expired(proposal):
            return proposal
        updated = await self.repository.update_proposal(proposal.id, user_id=user_id, payload={"status": "expired"})
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(proposal, updated, reason="expiry")
        return updated

    def _is_expired(self, proposal: AssistantProposal) -> bool:
        if proposal.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        expires_at = proposal.expires_at
        if expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return expires_at <= now

    def _ensure_option_exists(self, proposal: AssistantProposal, option_id: str) -> None:
        options = (proposal.payload_json or {}).get("options") or []
        if not any(option.get("option_id") == option_id for option in options if isinstance(option, dict)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="option not found")

    def _execution_snapshot(self, payload_json: dict[str, Any], option_id: str) -> dict[str, Any]:
        payload = deepcopy(payload_json)
        execution = dict(payload.get("execution") or {})
        execution.setdefault("attempts", [])
        execution["status"] = "pending"
        execution["selected_option_id"] = option_id
        execution["last_error"] = None
        payload["execution"] = execution
        return payload

    async def _execute_confirmed_proposal(
        self,
        *,
        user_id: str,
        proposal: AssistantProposal,
        option_id: str,
        is_retry: bool = False,
    ) -> AssistantProposal:
        pending_started_at = datetime.now(timezone.utc)
        pending_payload = self._mark_execution_pending(proposal.payload_json or {}, option_id, is_retry=is_retry)
        pending = await self.repository.update_proposal(
            proposal.id,
            user_id=user_id,
            payload={
                "status": "execution_pending",
                "execution_started_at": pending_started_at,
                "execution_error": None,
                "payload_json": pending_payload,
            },
        )
        if pending is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(proposal, pending, reason="execution_start")
        executor = self._get_executor()

        try:
            result = await executor.execute(user_id=user_id, proposal=pending, option_id=option_id)
        except HTTPException as exc:
            failed = self._mark_execution_failed(pending.payload_json or {}, option_id, error=str(exc.detail))
            failed_proposal = await self.repository.update_proposal(
                proposal.id,
                user_id=user_id,
                payload={
                    "status": "execution_failed",
                    "execution_error": str(exc.detail),
                    "payload_json": failed,
                },
            )
            if failed_proposal is not None:
                self._log_transition(pending, failed_proposal, reason="execution_failed")
            logger.warning(
                "assistant proposal execution failed user_id={} proposal_id={} option_id={} error={}",
                user_id,
                proposal.id,
                option_id,
                exc.detail,
            )
            raise
        except Exception as exc:
            failed = self._mark_execution_failed(pending.payload_json or {}, option_id, error=str(exc))
            failed_proposal = await self.repository.update_proposal(
                proposal.id,
                user_id=user_id,
                payload={
                    "status": "execution_failed",
                    "execution_error": str(exc),
                    "payload_json": failed,
                },
            )
            if failed_proposal is not None:
                self._log_transition(pending, failed_proposal, reason="execution_failed")
            logger.exception(
                "assistant proposal execution failed user_id={} proposal_id={} option_id={}",
                user_id,
                proposal.id,
                option_id,
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="proposal execution failed") from exc

        executed_at = datetime.now(timezone.utc)
        executed_payload = self._mark_execution_succeeded(pending.payload_json or {}, option_id, result)
        update_payload: dict[str, Any] = {
            "status": "executed",
            "execution_error": None,
            "executed_at": executed_at,
            "payload_json": executed_payload,
        }
        if result.get("related_task_id") is not None:
            update_payload["related_task_id"] = result.get("related_task_id")
        if result.get("related_event_id") is not None:
            update_payload["related_event_id"] = result.get("related_event_id")
        executed = await self.repository.update_proposal(proposal.id, user_id=user_id, payload=update_payload)
        if executed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        self._log_transition(pending, executed, reason="execution_success")
        return executed

    def _mark_execution_pending(self, payload_json: dict[str, Any], option_id: str, *, is_retry: bool) -> dict[str, Any]:
        payload = deepcopy(payload_json)
        execution = dict(payload.get("execution") or {})
        execution.setdefault("attempts", [])
        execution["status"] = "pending"
        execution["selected_option_id"] = option_id
        execution["last_error"] = None
        if is_retry:
            execution["retry_count"] = int(execution.get("retry_count") or 0) + 1
        else:
            execution.setdefault("retry_count", 0)
        payload["execution"] = execution
        return payload

    def _get_executor(self) -> AssistantActionExecutor:
        if not self.execute_on_confirm:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal execution is disabled")
        if self.executor is None:
            self.executor = AssistantActionExecutor()
        return self.executor

    def _mark_execution_succeeded(
        self,
        payload_json: dict[str, Any],
        option_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        payload = deepcopy(payload_json)
        execution = dict(payload.get("execution") or {})
        attempts = list(execution.get("attempts") or [])
        attempts.append(
            {
                "status": "executed",
                "option_id": option_id,
                "result": result,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        execution["attempts"] = attempts
        execution["status"] = "executed"
        execution["selected_option_id"] = option_id
        execution["last_error"] = None
        execution["result"] = result
        payload["execution"] = execution
        return payload

    def _mark_execution_failed(self, payload_json: dict[str, Any], option_id: str, *, error: str) -> dict[str, Any]:
        payload = deepcopy(payload_json)
        execution = dict(payload.get("execution") or {})
        attempts = list(execution.get("attempts") or [])
        attempts.append(
            {
                "status": "failed",
                "option_id": option_id,
                "error": error,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        execution["attempts"] = attempts
        execution["status"] = "failed"
        execution["selected_option_id"] = option_id
        execution["last_error"] = error
        payload["execution"] = execution
        return payload

    def _log_transition(self, before: AssistantProposal, after: AssistantProposal, *, reason: str) -> None:
        if before.status == after.status:
            return
        logger.info(
            "assistant proposal transition user_id={} proposal_id={} {}->{} reason={} dedup_key={}",
            after.user_id,
            after.id,
            before.status,
            after.status,
            reason,
            after.dedup_key,
        )
