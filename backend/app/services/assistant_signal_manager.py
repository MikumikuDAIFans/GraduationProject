"""Assistant signal lifecycle manager for proactive flows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select

from app.api.schemas import AssistantProposalCreate, AssistantSignalCreate
from app.db.session import get_sessionmaker
from app.models import AssistantProposal, AssistantSignal, Event, Task
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager


SIGNAL_COOLDOWNS: dict[str, timedelta] = {
    "deadline_risk": timedelta(hours=6),
    "conflict_warning": timedelta(hours=4),
    "daily_morning_review": timedelta(hours=24),
    "daily_night_review": timedelta(hours=24),
    "departure_readiness": timedelta(minutes=30),
    "proposal_followup": timedelta(hours=2),
}
DEFAULT_SIGNAL_COOLDOWN = timedelta(hours=1)
TERMINAL_SIGNAL_STATUSES = {"dismissed", "expired"}


class AssistantSignalManager:
    """Own signal dedup, cooldown, and user-visible status transitions."""

    def __init__(
        self,
        repository: AssistantSignalRepository | None = None,
        *,
        proposal_manager: AssistantProposalManager | None = None,
    ) -> None:
        self.repository = repository or AssistantSignalRepository(get_sessionmaker())
        self.proposal_manager = proposal_manager

    async def create_signal(self, *, user_id: str, payload: AssistantSignalCreate) -> AssistantSignal:
        now = datetime.now(timezone.utc)
        payload_data = payload.model_dump()
        payload_data.setdefault("status", "new")
        payload_data["cooldown_until"] = payload_data.get("cooldown_until") or self._default_cooldown_until(
            payload.signal_type,
            now,
        )

        if payload.dedup_key:
            existing = await self.repository.get_blocking_by_dedup_key(user_id=user_id, dedup_key=payload.dedup_key, now=now)
            if existing is not None:
                logger.info(
                    "assistant signal dedup/cooldown hit user_id={} dedup_key={} signal_id={} status={}",
                    user_id,
                    payload.dedup_key,
                    existing.id,
                    existing.status,
                )
                return existing

        signal = await self.repository.create_signal({"user_id": user_id, **payload_data})
        logger.info(
            "assistant signal created user_id={} signal_id={} type={} status={} dedup_key={} cooldown_until={}",
            user_id,
            signal.id,
            signal.signal_type,
            signal.status,
            signal.dedup_key,
            signal.cooldown_until,
        )
        return signal

    async def list_signals(
        self,
        *,
        user_id: str,
        statuses: list[str] | None = None,
        signal_type: str | None = None,
        limit: int = 50,
    ) -> list[AssistantSignal]:
        return await self.repository.list_signals(
            user_id=user_id,
            statuses=statuses,
            signal_type=signal_type,
            limit=limit,
        )

    async def get_signal(self, *, user_id: str, signal_id: int) -> AssistantSignal:
        signal = await self.repository.get_signal(signal_id, user_id=user_id)
        if signal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal not found")
        return signal

    async def mark_evaluated(self, *, user_id: str, signal_id: int) -> AssistantSignal:
        signal = await self.get_signal(user_id=user_id, signal_id=signal_id)
        self._ensure_mutable(signal)
        updated = await self.repository.update_signal(
            signal.id,
            user_id=user_id,
            payload={"status": "evaluated", "evaluated_at": datetime.now(timezone.utc)},
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal not found")
        self._log_transition(signal, updated, reason="evaluate")
        return updated

    async def mark_proposal_created(self, *, user_id: str, signal_id: int) -> AssistantSignal:
        signal = await self.get_signal(user_id=user_id, signal_id=signal_id)
        self._ensure_mutable(signal)
        updated = await self.repository.update_signal(
            signal.id,
            user_id=user_id,
            payload={"status": "proposal_created", "proposal_created_at": datetime.now(timezone.utc)},
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal not found")
        self._log_transition(signal, updated, reason="proposal_created")
        return updated

    async def create_proposal_from_signal(self, *, user_id: str, signal_id: int) -> AssistantProposal:
        signal = await self.get_signal(user_id=user_id, signal_id=signal_id)
        self._ensure_mutable(signal)
        proposal_manager = self._get_proposal_manager()
        proposal = await proposal_manager.create_proposal(
            user_id=user_id,
            payload=await self._proposal_payload_for_signal(user_id=user_id, signal=signal),
        )
        await self.mark_proposal_created(user_id=user_id, signal_id=signal.id)
        return proposal

    async def dismiss_signal(self, *, user_id: str, signal_id: int) -> AssistantSignal:
        signal = await self.get_signal(user_id=user_id, signal_id=signal_id)
        if signal.status == "dismissed":
            return signal
        if signal.status == "expired":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="signal is expired")
        now = datetime.now(timezone.utc)
        updated = await self.repository.update_signal(
            signal.id,
            user_id=user_id,
            payload={
                "status": "dismissed",
                "dismissed_at": now,
                "cooldown_until": signal.cooldown_until or self._default_cooldown_until(signal.signal_type, now),
            },
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal not found")
        self._log_transition(signal, updated, reason="dismiss")
        return updated

    def _ensure_mutable(self, signal: AssistantSignal) -> None:
        if signal.status in TERMINAL_SIGNAL_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"signal is {signal.status}")

    def _default_cooldown_until(self, signal_type: str, now: datetime) -> datetime:
        return now + SIGNAL_COOLDOWNS.get(signal_type, DEFAULT_SIGNAL_COOLDOWN)

    def _get_proposal_manager(self) -> AssistantProposalManager:
        if self.proposal_manager is None:
            self.proposal_manager = AssistantProposalManager()
        return self.proposal_manager

    async def _proposal_payload_for_signal(self, *, user_id: str, signal: AssistantSignal) -> AssistantProposalCreate:
        proposal_type = {
            "deadline_risk": "deadline_recovery",
            "conflict_warning": "reschedule_plan",
            "daily_morning_review": "daily_plan_followup",
            "daily_night_review": "daily_review_followup",
            "departure_readiness": "departure_readiness",
            "proposal_followup": "proposal_followup",
        }.get(signal.signal_type, "signal_followup")
        summary = await self._proposal_summary_for_signal(user_id=user_id, signal=signal)
        return AssistantProposalCreate(
            proposal_type=proposal_type,
            trigger_type="assistant_signal",
            status="pending",
            dedup_key=f"signal_proposal:{signal.id}:{signal.signal_type}",
            priority=self._proposal_priority(signal),
            summary=summary,
            payload_json={
                "source": "assistant_signal",
                "signal": {
                    "id": signal.id,
                    "signal_type": signal.signal_type,
                    "severity": signal.severity,
                    "target_type": signal.target_type,
                    "target_id": signal.target_id,
                    "context": signal.context_json or {},
                },
                "options": [
                    {
                        "option_id": "A",
                        "title": "确认并稍后继续协商",
                        "summary": summary,
                        "actions": [
                            {
                                "type": "acknowledge_signal",
                                "payload": {
                                    "signal_id": signal.id,
                                    "signal_type": signal.signal_type,
                                    "message": summary,
                                },
                            }
                        ],
                    }
                ],
            },
            recommended_option_id="A",
            is_time_sensitive=signal.signal_type in {"deadline_risk", "conflict_warning", "departure_readiness"},
            related_task_id=signal.target_id if signal.target_type == "task" else None,
            related_event_id=signal.target_id if signal.target_type == "event" else None,
            source_signal_id=signal.id,
        )

    async def _proposal_summary_for_signal(self, *, user_id: str, signal: AssistantSignal) -> str:
        if signal.signal_type == "daily_night_review":
            return await self._daily_night_review_summary(user_id=user_id, signal=signal)
        return self._proposal_summary(signal)

    async def _daily_night_review_summary(self, *, user_id: str, signal: AssistantSignal) -> str:
        context = signal.context_json or {}
        raw_date = context.get("local_date")
        try:
            target_date = date.fromisoformat(str(raw_date)) if raw_date else datetime.now().date()
        except ValueError:
            target_date = datetime.now().date()

        day_start = datetime.combine(target_date, time.min)
        day_end = day_start + timedelta(days=1)
        events: list[Event] = []
        tasks: list[Task] = []
        proposals: list[AssistantProposal] = []
        try:
            async with self.repository.session_factory() as session:
                events = list(
                    (
                        await session.scalars(
                            select(Event)
                            .where(
                                Event.user_id == user_id,
                                Event.start_time >= day_start,
                                Event.start_time < day_end,
                                Event.status != "canceled",
                            )
                            .order_by(Event.start_time.asc(), Event.id.asc())
                            .limit(5)
                        )
                    ).all()
                )
                tasks = list(
                    (
                        await session.scalars(
                            select(Task)
                            .where(
                                Task.user_id == user_id,
                                Task.status.notin_(["done", "completed", "archived"]),
                            )
                            .order_by(Task.priority.asc(), Task.id.asc())
                            .limit(5)
                        )
                    ).all()
                )
                proposals = list(
                    (
                        await session.scalars(
                            select(AssistantProposal)
                            .where(
                                AssistantProposal.user_id == user_id,
                                AssistantProposal.status == "pending",
                            )
                            .order_by(AssistantProposal.created_at.desc(), AssistantProposal.id.desc())
                            .limit(5)
                        )
                    ).all()
                )
        except Exception as exc:  # pragma: no cover - summary fallback should not block proposal creation
            logger.bind(component="assistant.signal").warning(
                "Failed to build daily night review snapshot: {error}",
                error=str(exc),
            )

        def _event_label(event: Event) -> str:
            start_time = getattr(event, "start_time", None)
            prefix = start_time.strftime("%H:%M") if isinstance(start_time, datetime) else "时间待定"
            return f"{prefix} {event.title}"

        event_text = "；".join(_event_label(event) for event in events) or "暂无已登记日程"
        task_text = "；".join(task.content for task in tasks) or "暂无未完成任务"
        proposal_text = "；".join(proposal.summary for proposal in proposals[:3]) or "暂无待确认方案"
        return (
            "睡前复盘："
            f"今日日程完成核对：{event_text}。"
            f"未完成任务：{task_text}。"
            f"pending proposal 跟进：{proposal_text}。"
            "可回复：今天这两个都完成了；政治课完成了，复习没做；先不要安排。"
        )

    def _proposal_summary(self, signal: AssistantSignal) -> str:
        context = signal.context_json or {}
        if signal.signal_type == "deadline_risk":
            return f"任务「{context.get('content') or signal.target_id}」临近截止，需要协商安排。"
        if signal.signal_type == "conflict_warning":
            return f"日程「{context.get('event_a_title') or signal.target_id}」可能与其他安排冲突，需要确认调整方案。"
        if signal.signal_type == "departure_readiness":
            return f"「{context.get('title') or signal.target_id}」即将到出发时间，需要临行确认。"
        if signal.signal_type == "proposal_followup":
            original_summary = str(context.get("proposal_summary") or signal.target_id or "").strip()
            fallback_label = f"P{signal.target_id}" if signal.target_id else "这个方案"
            label = str(context.get("protocol_label") or fallback_label).strip()
            if original_summary:
                return (
                    f"待确认方案跟进：{label}「{original_summary}」已经等待超过 2 小时。"
                    "可回复：按方案A安排；改成4点开始；先不要安排。"
                )
            return "待确认方案跟进：有方案已经等待超过 2 小时。可回复：按方案A安排；修改方案；先不要安排。"
        if signal.signal_type == "daily_night_review":
            return str(context.get("message") or "睡前复盘：请确认今天完成情况与需要顺延的事项。")
        if signal.signal_type == "daily_morning_review":
            return str(context.get("message") or "晨间计划确认：请查看今天安排是否需要调整。")
        return f"主动信号 {signal.signal_type} 需要跟进。"

    def _proposal_priority(self, signal: AssistantSignal) -> int:
        if signal.severity == "urgent":
            return 3
        if signal.severity == "negotiate":
            return 2
        return 1

    def _log_transition(self, before: AssistantSignal, after: AssistantSignal, *, reason: str) -> None:
        if before.status == after.status:
            return
        logger.info(
            "assistant signal transition user_id={} signal_id={} {}->{} reason={} dedup_key={}",
            after.user_id,
            after.id,
            before.status,
            after.status,
            reason,
            after.dedup_key,
        )
