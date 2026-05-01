"""Planning specialist that builds in-memory proposal drafts."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.assistant_agents.contracts import (
    AssistantAgentContext,
    ConductorState,
    ProposalDraft,
    ProposalOptionDraft,
)


class PlanningSpecialist:
    name = "planning"

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        understanding = state.understanding
        if understanding is None or not understanding.can_propose_without_clarification:
            return state

        if understanding.goal_type == "event":
            proposal = self._build_event_proposal(understanding.slots, assumptions=understanding.assumptions)
            if proposal:
                state.proposals.append(proposal)
        elif understanding.goal_type == "task":
            proposal = self._build_task_proposal(understanding.slots)
            if proposal:
                state.proposals.append(proposal)
        return state

    def _build_event_proposal(self, slots: dict, *, assumptions: list[str]) -> ProposalDraft | None:
        title = slots.get("title")
        start_raw = slots.get("start_time")
        if not title or not start_raw:
            return None
        start_time = datetime.fromisoformat(start_raw)
        end_raw = slots.get("end_time")
        end_time = datetime.fromisoformat(end_raw) if end_raw else start_time + timedelta(minutes=60)
        location_name = slots.get("location_name")
        payload = {
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "location_name": location_name,
            "event_type": "general",
        }
        summary = f"建议创建日程“{title}”：{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}"
        if location_name:
            summary += f"，地点：{location_name}"
        rationale = "结束时间未明确，先按 1 小时估算，可在确认前修改。" if "default_event_duration_60_minutes" in assumptions else None
        return ProposalDraft(
            proposal_type="event_creation",
            summary=summary,
            recommended_option_id="A",
            is_time_sensitive=True,
            payload_json={"source": "conductor_v1", "assumptions": assumptions},
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="按建议创建日程",
                    summary=summary,
                    actions=[{"type": "create_event", "payload": payload}],
                    rationale=rationale,
                )
            ],
        )

    def _build_task_proposal(self, slots: dict) -> ProposalDraft | None:
        content = slots.get("content")
        if not content:
            return None
        payload = {
            "content": content,
            "description": slots.get("description"),
            "deadline": slots.get("deadline"),
            "estimated_duration_minutes": slots.get("estimated_duration_minutes"),
            "priority": slots.get("priority") or 3,
            "can_split": bool(slots.get("can_split")),
            "preferred_period": slots.get("preferred_period"),
            "status": "pending",
        }
        summary = f"建议先创建任务“{content}”，进入待排程/待跟进状态"
        if slots.get("deadline"):
            summary += f"，截止时间：{slots['deadline']}"
        return ProposalDraft(
            proposal_type="task_creation",
            summary=summary,
            recommended_option_id="A",
            is_time_sensitive=False,
            payload_json={"source": "conductor_v1", "assumptions": ["task_can_start_as_pending_schedule"]},
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="创建任务并等待后续排程",
                    summary=summary,
                    actions=[{"type": "create_task", "payload": payload}],
                    rationale="任务可以先进入待排程状态，后续再拆成日程块确认执行。",
                )
            ],
        )
