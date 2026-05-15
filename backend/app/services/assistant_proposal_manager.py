"""Proposal lifecycle manager for the assistant redesign."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from loguru import logger

from app.api.schemas import AssistantProposalCreate
from app.assistant_agents.action_executor import AssistantActionExecutor
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import AssistantProposal
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.services.assistant_runtime_text import AssistantTextRuntime, TIME_TOKEN_PATTERN


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
        self.settings = get_settings()
        self.text_runtime = AssistantTextRuntime()

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
        session_id: int | None = None,
        statuses: list[str] | None = None,
        proposal_type: str | None = None,
        limit: int = 50,
    ) -> list[AssistantProposal]:
        await self.expire_due_proposals(user_id=user_id, limit=100)
        return await self.repository.list_proposals(
            user_id=user_id,
            session_id=session_id,
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
                return await self._recover_or_resume_execution_pending(
                    user_id=user_id,
                    proposal=proposal,
                    option_id=option_id,
                )
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

        new_payload = self._build_revised_payload(proposal=proposal, message=message)
        new_payload["revision_request"] = message
        new_payload["superseded_proposal_id"] = proposal.id
        summary = self._build_revised_summary(proposal=proposal, payload_json=new_payload)

        revised = await self.repository.create_proposal(
            {
                "user_id": user_id,
                "session_id": proposal.session_id,
                "thread_state_id": proposal.thread_state_id,
                "proposal_type": proposal.proposal_type,
                "trigger_type": "user_message",
                "status": "pending",
                "priority": proposal.priority,
                "summary": summary,
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

    def _build_revised_payload(self, *, proposal: AssistantProposal, message: str) -> dict[str, Any]:
        payload = deepcopy(proposal.payload_json or {})
        revision = self._extract_event_revision(payload_json=payload, message=message)
        if revision is None:
            return payload

        options = payload.get("options")
        if not isinstance(options, list):
            return payload

        changed = False
        revised_options: list[Any] = []
        for option in options:
            if not isinstance(option, dict):
                revised_options.append(option)
                continue
            option_copy = deepcopy(option)
            actions = option_copy.get("actions")
            if not isinstance(actions, list):
                revised_options.append(option_copy)
                continue
            option_changed = False
            revised_actions: list[Any] = []
            for action in actions:
                if not isinstance(action, dict):
                    revised_actions.append(action)
                    continue
                action_copy = deepcopy(action)
                action_type = action_copy.get("type")
                action_payload = action_copy.get("payload")
                if isinstance(action_payload, dict) and action_type == "create_event":
                    action_payload = dict(action_payload)
                    self._apply_event_revision_to_payload(action_payload, revision)
                    action_copy["payload"] = action_payload
                    changed = True
                    option_changed = True
                elif isinstance(action_payload, dict) and action_type == "reschedule_event":
                    action_payload = dict(action_payload)
                    update = dict(action_payload.get("update") or {})
                    self._apply_event_revision_to_payload(update, revision)
                    action_payload["update"] = update
                    action_copy["payload"] = action_payload
                    changed = True
                    option_changed = True
                revised_actions.append(action_copy)
            if option_changed:
                option_copy["summary"] = self._replace_time_in_text(option_copy.get("summary"), revision)
                option_copy["title"] = option_copy.get("title") or "按修改后的方案执行"
            option_copy["actions"] = revised_actions
            revised_options.append(option_copy)

        if changed:
            payload["options"] = revised_options
            payload["revision"] = {"type": "event_payload_update", **revision}
        return payload

    def _extract_event_revision(self, *, payload_json: dict[str, Any], message: str) -> dict[str, str] | None:
        revision: dict[str, str] = {}
        time_revision = self._extract_revision_event_time(payload_json=payload_json, message=message)
        if time_revision:
            revision.update(time_revision)
        title = self._extract_revision_event_title(message)
        if title:
            revision["title"] = title
        location_name = self._extract_revision_event_location(message)
        if location_name:
            revision["location_name"] = location_name
        return revision or None

    def _apply_event_revision_to_payload(self, payload: dict[str, Any], revision: dict[str, str]) -> None:
        for key in ("start_time", "end_time", "title", "location_name"):
            if revision.get(key):
                payload[key] = revision[key]

    def _extract_revision_event_time(self, *, payload_json: dict[str, Any], message: str) -> dict[str, str] | None:
        original = self._first_event_timing(payload_json)
        if original is None:
            return None
        old_start, old_end = original
        reference = self._revision_reference(message=message, old_start=old_start)
        if re.search(r"缩短\s*半小时|提前\s*半小时\s*结束|少\s*半小时", message):
            duration = old_end - old_start if old_end > old_start else timedelta(minutes=60)
            end_time = old_start + max(duration - timedelta(minutes=30), timedelta(minutes=30))
            return {"start_time": old_start.isoformat(), "end_time": end_time.isoformat()}
        if re.search(r"(?:开到|结束到|结束时间\s*(?:改到|改成|到)?\s*[\d一二两三四五六七八九十]{1,3}\s*(?:点|时))", message):
            end_time = self._extract_single_time(message, reference=reference)
            if end_time is None:
                return None
            if end_time <= old_start:
                end_time = end_time + timedelta(hours=12)
                if end_time <= old_start:
                    end_time = end_time + timedelta(days=1)
            return {"start_time": old_start.isoformat(), "end_time": end_time.isoformat()}
        start_time, end_time = self.text_runtime._extract_time_range(message, reference=reference)
        start_time = start_time or self._extract_single_time(message, reference=reference)
        if start_time is None:
            return None
        duration = old_end - old_start if old_end > old_start else timedelta(minutes=60)
        end_time = end_time or start_time + duration
        return {"start_time": start_time.isoformat(), "end_time": end_time.isoformat()}

    def _extract_revision_event_title(self, message: str) -> str | None:
        patterns = [
            r"(?:标题|名称|名字)\s*(?:改成|改为|改叫|设为|叫)\s*[“\"]?(?P<title>[^，。,；;.!！?？“”\"]{2,40})",
            r"(?:改名为|命名为|叫做|叫)\s*[“\"]?(?P<title>[^，。,；;.!！?？“”\"]{2,40})",
            r"(?:标题|名称|名字)\s*[：:]\s*[“\"](?P<title>[^”\"]{2,40})[”\"]",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if not match:
                continue
            title = self._clean_revision_text(match.group("title"))
            if title:
                return title
        return None

    def _extract_revision_event_location(self, message: str) -> str | None:
        patterns = [
            r"(?:地点|位置|地方)\s*(?:改到|改成|改为|换到|设为|在|到)\s*[“\"]?(?P<location>[^，。,；;.!！?？“”\"]{2,40})",
            r"(?:换到|移到)\s*[“\"]?(?P<location>[^，。,；;.!！?？“”\"]{2,40})",
            r"(?:改到|挪到)\s*[“\"]?(?P<location>[^，。,；;.!！?？“”\"]{2,40})(?:开会|见面|碰头|集合|讨论|复习|上课|答辩|演示|汇报|参加|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if not match:
                continue
            location = self._clean_revision_text(match.group("location"))
            location = re.sub(r"(开会|见面|碰头|集合|讨论|复习|上课|答辩|演示|汇报|参加)$", "", location).strip()
            if location and not self._looks_like_time_or_date(location):
                return location
        return None

    def _clean_revision_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip(" ，。,；;.!！?？“”\"'")
        return cleaned or None

    def _looks_like_time_or_date(self, value: str) -> bool:
        return bool(
            re.search(
                r"大后天|后天|明天|今天|今晚|上午|下午|晚上|凌晨|早上|中午|"
                r"\d{1,2}\s*(?:点|时|月|日|号)|\d{4}-\d{1,2}-\d{1,2}",
                value,
            )
        )

    def _first_event_timing(self, payload_json: dict[str, Any]) -> tuple[datetime, datetime] | None:
        options = payload_json.get("options")
        if not isinstance(options, list):
            return None
        for option in options:
            if not isinstance(option, dict):
                continue
            actions = option.get("actions")
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                payload = action.get("payload")
                if not isinstance(payload, dict):
                    continue
                if action.get("type") == "create_event":
                    start_raw = payload.get("start_time")
                    end_raw = payload.get("end_time")
                elif action.get("type") == "reschedule_event":
                    update = payload.get("update")
                    if not isinstance(update, dict):
                        continue
                    start_raw = update.get("start_time")
                    end_raw = update.get("end_time")
                else:
                    continue
                if not start_raw or not end_raw:
                    continue
                try:
                    return datetime.fromisoformat(str(start_raw)), datetime.fromisoformat(str(end_raw))
                except ValueError:
                    continue
        return None

    def _revision_reference(self, *, message: str, old_start: datetime) -> datetime:
        if self._message_has_date_reference(message):
            return datetime.now(ZoneInfo(self.settings.app_timezone))
        return old_start

    def _message_has_date_reference(self, message: str) -> bool:
        return bool(
            re.search(
                r"大后天|后天|明天|今天|今晚|明早|明晚|下下周|下周|本周|这周|周[一二三四五六日天末]|星期[一二三四五六日天]|(?:\d{4}[年/-])?\d{1,2}[月/-]\d{1,2}日?",
                message,
            )
        )

    def _extract_single_time(self, message: str, *, reference: datetime) -> datetime | None:
        base_date = self.text_runtime._extract_target_date(message, reference.date())
        token_match = TIME_TOKEN_PATTERN.search(message)
        if token_match:
            start_time, period = self.text_runtime._parse_time_token(token_match.group(0), base_date)
            if start_time:
                if period is None and reference.hour >= 12 and 1 <= start_time.hour < 12:
                    start_time = start_time.replace(hour=start_time.hour + 12)
                return start_time
        digit_match = re.search(
            r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|今晚|今早|明早|明晚)?\s*"
            r"(?P<hour>\d{1,2})\s*(?:点|时)(?P<minute>半|\d{1,2}分?)?",
            message,
        )
        if not digit_match:
            return None
        hour = int(digit_match.group("hour"))
        period = digit_match.group("period")
        minute_raw = digit_match.group("minute") or ""
        minute = 30 if minute_raw == "半" else int(minute_raw.replace("分", "") or 0)
        hour = self.text_runtime._apply_period(hour, period)
        if period is None and reference.hour >= 12 and 1 <= hour < 12:
            hour += 12
        return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)

    def _build_revised_summary(self, *, proposal: AssistantProposal, payload_json: dict[str, Any]) -> str:
        revision = payload_json.get("revision") if isinstance(payload_json, dict) else None
        summary_parts: list[str] = []
        if isinstance(revision, dict) and revision.get("start_time") and revision.get("end_time"):
            try:
                start_time = datetime.fromisoformat(str(revision["start_time"]))
                end_time = datetime.fromisoformat(str(revision["end_time"]))
                summary_parts.append(f"时间 {start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}")
            except ValueError:
                pass
        if isinstance(revision, dict) and revision.get("title"):
            summary_parts.append(f"标题“{revision['title']}”")
        if isinstance(revision, dict) and revision.get("location_name"):
            summary_parts.append(f"地点 {revision['location_name']}")
        if summary_parts:
            return f"{proposal.summary}（已修改：{'，'.join(summary_parts)}）"
        return f"{proposal.summary}（修改中）"

    def _replace_time_in_text(self, value: Any, revision: dict[str, str]) -> Any:
        if not isinstance(value, str):
            return value
        try:
            start_time = datetime.fromisoformat(revision["start_time"])
            end_time = datetime.fromisoformat(revision["end_time"])
        except (KeyError, ValueError):
            return value
        replacement = f"{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}"
        if re.search(r"\d{2}-\d{2}\s+\d{2}:\d{2}-\d{2}:\d{2}", value):
            return re.sub(r"\d{2}-\d{2}\s+\d{2}:\d{2}-\d{2}:\d{2}", replacement, value)
        return f"{value}（改到 {replacement}）"

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

    async def _recover_or_resume_execution_pending(
        self,
        *,
        user_id: str,
        proposal: AssistantProposal,
        option_id: str,
    ) -> AssistantProposal:
        payload_json = proposal.payload_json or {}
        execution = payload_json.get("execution") if isinstance(payload_json, dict) else None
        if isinstance(execution, dict):
            result = execution.get("result")
            if isinstance(result, dict) and result.get("status") == "executed":
                update_payload: dict[str, Any] = {
                    "status": "executed",
                    "execution_error": None,
                    "executed_at": datetime.now(timezone.utc),
                }
                if result.get("related_task_id") is not None:
                    update_payload["related_task_id"] = result.get("related_task_id")
                if result.get("related_event_id") is not None:
                    update_payload["related_event_id"] = result.get("related_event_id")
                updated = await self.repository.update_proposal(proposal.id, user_id=user_id, payload=update_payload)
                if updated is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
                self._log_transition(proposal, updated, reason="execution_recovered")
                return updated

        started_at = proposal.execution_started_at
        if started_at is not None:
            now = datetime.now(timezone.utc)
            comparable_started = started_at
            if comparable_started.tzinfo is None:
                comparable_started = comparable_started.replace(tzinfo=timezone.utc)
            if now - comparable_started < timedelta(seconds=15):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="proposal execution is already pending")

        return await self._execute_confirmed_proposal(
            user_id=user_id,
            proposal=proposal,
            option_id=option_id,
            is_retry=True,
        )

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
