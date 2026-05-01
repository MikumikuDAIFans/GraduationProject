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
            if understanding.intent in {"reschedule_event", "cancel_event", "mark_event_completed"}:
                proposal = self._build_event_update_proposal(context, understanding.slots)
            else:
                proposal = self._build_event_proposal(understanding.slots, assumptions=understanding.assumptions)
            if proposal:
                state.proposals.append(proposal)
        elif understanding.goal_type == "task":
            if understanding.intent == "mark_task_completed":
                proposal = self._build_task_update_proposal(understanding.slots)
            else:
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

    def _build_event_update_proposal(self, context: AssistantAgentContext, slots: dict) -> ProposalDraft | None:
        action_type = slots.get("action_type")
        event_id = slots.get("target_id")
        title = slots.get("target_title") or "这个日程"
        if not action_type or not event_id:
            return None

        if action_type == "reschedule_event":
            start_raw = slots.get("new_start_time")
            if not start_raw:
                return None
            start_time = datetime.fromisoformat(start_raw)
            end_raw = slots.get("new_end_time")
            end_time = datetime.fromisoformat(end_raw) if end_raw else self._derive_rescheduled_end(context, event_id, start_time)
            update_payload = {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            }
            summary = f"建议把日程“{title}”改到 {start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}"
            return ProposalDraft(
                proposal_type="event_reschedule",
                summary=summary,
                recommended_option_id="A",
                is_time_sensitive=True,
                related_event_id=int(event_id),
                payload_json={"source": "conductor_v1", "target_title": title},
                options=[
                    ProposalOptionDraft(
                        option_id="A",
                        title="按建议重排日程",
                        summary=summary,
                        actions=[
                            {
                                "type": "reschedule_event",
                                "payload": {"event_id": int(event_id), "update": update_payload},
                            }
                        ],
                        rationale="我只会在你确认后修改原日程时间。",
                    )
                ],
            )

        if action_type == "cancel_event":
            summary = f"建议取消日程“{title}”"
            return ProposalDraft(
                proposal_type="event_cancel",
                summary=summary,
                recommended_option_id="A",
                is_time_sensitive=True,
                related_event_id=int(event_id),
                payload_json={"source": "conductor_v1", "target_title": title},
                options=[
                    ProposalOptionDraft(
                        option_id="A",
                        title="取消这个日程",
                        summary=summary,
                        actions=[{"type": "cancel_event", "payload": {"event_id": int(event_id)}}],
                        rationale="取消会保留历史记录，不会物理删除。",
                    )
                ],
            )

        if action_type == "mark_event_completed":
            summary = f"建议把日程“{title}”标记为完成"
            return ProposalDraft(
                proposal_type="event_status_update",
                summary=summary,
                recommended_option_id="A",
                is_time_sensitive=False,
                related_event_id=int(event_id),
                payload_json={"source": "conductor_v1", "target_title": title},
                options=[
                    ProposalOptionDraft(
                        option_id="A",
                        title="标记日程完成",
                        summary=summary,
                        actions=[{"type": "mark_event_completed", "payload": {"event_id": int(event_id)}}],
                        rationale="确认后会更新完成状态，并触发关联任务进度回算。",
                    )
                ],
            )
        return None

    def _build_task_update_proposal(self, slots: dict) -> ProposalDraft | None:
        task_id = slots.get("target_id")
        title = slots.get("target_title") or "这个任务"
        if not task_id:
            return None
        summary = f"建议把任务“{title}”标记为完成"
        return ProposalDraft(
            proposal_type="task_status_update",
            summary=summary,
            recommended_option_id="A",
            is_time_sensitive=False,
            related_task_id=int(task_id),
            payload_json={"source": "conductor_v1", "target_title": title},
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="标记任务完成",
                    summary=summary,
                    actions=[{"type": "mark_task_completed", "payload": {"task_id": int(task_id)}}],
                    rationale="确认后会把任务状态改为完成。",
                )
            ],
        )

    def _derive_rescheduled_end(self, context: AssistantAgentContext, event_id: int, start_time: datetime) -> datetime:
        for event in context.events:
            if getattr(event, "id", None) != event_id:
                continue
            old_start = getattr(event, "start_time", None)
            old_end = getattr(event, "end_time", None)
            if old_start is not None and old_end is not None:
                duration = old_end - old_start
                if duration.total_seconds() > 0:
                    return start_time + duration
        return start_time + timedelta(minutes=60)
