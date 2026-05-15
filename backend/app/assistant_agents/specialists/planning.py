"""Planning specialist that builds in-memory proposal drafts."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

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
                proposal = self._build_event_proposal(context, understanding.slots, assumptions=understanding.assumptions)
            if proposal:
                state.proposals.append(proposal)
        elif understanding.goal_type == "task":
            if understanding.intent == "mark_task_completed":
                proposal = self._build_task_update_proposal(context, understanding.slots)
            elif understanding.intent == "plan_task_schedule":
                proposal = self._build_task_schedule_proposal(understanding.slots)
            else:
                proposal = self._build_task_proposal(understanding.slots)
            if proposal:
                state.proposals.append(proposal)
        return state

    def _build_event_proposal(self, context: AssistantAgentContext, slots: dict, *, assumptions: list[str]) -> ProposalDraft | None:
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
        diagnostics = self._event_planning_diagnostics(
            context=context,
            title=title,
            start_time=start_time,
            end_time=end_time,
            location_name=location_name,
        )
        if diagnostics.get("departure_time"):
            payload["departure_time"] = diagnostics["departure_time"].isoformat()
        if diagnostics.get("travel_duration_minutes"):
            payload["travel_duration_minutes"] = diagnostics["travel_duration_minutes"]

        summary = f"建议创建日程“{title}”：{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}"
        if location_name:
            summary += f"，地点：{location_name}"
        if diagnostics["risk_summaries"]:
            summary += "；" + "；".join(diagnostics["risk_summaries"])
        rationale = "结束时间未明确，先按 1小时估算，可在确认前修改。" if "default_event_duration_60_minutes" in assumptions else None
        options = self._build_event_options(
            base_payload=payload,
            base_summary=summary,
            base_rationale=rationale,
            diagnostics=diagnostics,
            start_time=start_time,
            end_time=end_time,
        )
        return ProposalDraft(
            proposal_type="event_creation",
            summary=summary,
            recommended_option_id=options[0].option_id if options else "A",
            is_time_sensitive=True,
            payload_json={"source": "conductor_v1", "assumptions": assumptions, "diagnostics": diagnostics["payload"]},
            options=options,
        )

    def _build_event_options(
        self,
        *,
        base_payload: dict,
        base_summary: str,
        base_rationale: str | None,
        diagnostics: dict,
        start_time: datetime,
        end_time: datetime,
    ) -> list[ProposalOptionDraft]:
        duration = end_time - start_time
        if diagnostics["direct_conflicts"]:
            conflict = diagnostics["direct_conflicts"][0]
            adjusted_start = end_time
            adjusted_end = adjusted_start + duration
            adjusted_payload = dict(base_payload)
            adjusted_payload["start_time"] = adjusted_start.isoformat()
            adjusted_payload["end_time"] = adjusted_end.isoformat()
            conflict_title = conflict["title"]
            return [
                ProposalOptionDraft(
                    option_id="A",
                    title="后移新日程以避开当前时段",
                    summary=(
                        f"方案A：将“{base_payload['title']}”调整至 "
                        f"{adjusted_start.strftime('%H:%M')}-{adjusted_end.strftime('%H:%M')}，"
                        f"原日程“{conflict_title}”保持不变。"
                    ),
                    actions=[{"type": "create_event", "payload": adjusted_payload}],
                    rationale=f"与{conflict_title}存在时间冲突，先给出不修改原日程的候选方案。",
                ),
                ProposalOptionDraft(
                    option_id="B",
                    title="维持原时间并提示处理冲突",
                    summary=(
                        f"方案B：维持原时间 {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}，"
                        f"但需要你另行取消或调整“{conflict_title}”。"
                    ),
                    actions=[{"type": "create_event", "payload": base_payload}],
                    rationale=f"该方案会继续与{conflict_title}冲突，确认前需要你明确接受这个风险。",
                ),
            ]

        if diagnostics.get("travel_buffer_risk"):
            delayed_start = diagnostics["travel_buffer_risk"]["suggested_start"]
            delayed_end = delayed_start + duration
            delayed_payload = dict(base_payload)
            delayed_payload["start_time"] = delayed_start.isoformat()
            delayed_payload["end_time"] = delayed_end.isoformat()
            return [
                ProposalOptionDraft(
                    option_id="A",
                    title="推迟到通勤缓冲更充足的时间",
                    summary=(
                        f"方案A：将“{base_payload['title']}”推迟至 "
                        f"{delayed_start.strftime('%H:%M')}-{delayed_end.strftime('%H:%M')}，"
                        "出发缓冲更充足。"
                    ),
                    actions=[{"type": "create_event", "payload": delayed_payload}],
                    rationale=diagnostics["travel_buffer_risk"]["summary"],
                ),
                ProposalOptionDraft(
                    option_id="B",
                    title="维持原时间但接受通勤风险",
                    summary=(
                        f"方案B：维持原时间 {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}，"
                        "但出发缓冲不足。"
                    ),
                    actions=[{"type": "create_event", "payload": base_payload}],
                    rationale=diagnostics["travel_buffer_risk"]["summary"],
                ),
            ]

        return [
            ProposalOptionDraft(
                option_id="A",
                title="按建议创建日程",
                summary=base_summary,
                actions=[{"type": "create_event", "payload": base_payload}],
                rationale=base_rationale or diagnostics.get("travel_rationale") or diagnostics.get("adjacent_rationale"),
            )
        ]

    def _event_planning_diagnostics(
        self,
        *,
        context: AssistantAgentContext,
        title: str,
        start_time: datetime,
        end_time: datetime,
        location_name: str | None,
    ) -> dict:
        direct_conflicts = self._find_direct_conflicts(context.events, start_time=start_time, end_time=end_time)
        risk_summaries: list[str] = []
        payload: dict = {"direct_conflicts": [], "travel_risks": [], "adjacent_warnings": []}

        for conflict in direct_conflicts:
            risk_summaries.append(f"与{conflict['title']}存在时间冲突")
            payload["direct_conflicts"].append(conflict)

        departure_time = None
        travel_duration = None
        travel_rationale = None
        travel_buffer_risk = None
        origin_event = self._previous_event(context.events, start_time)
        explicit_origin = self._explicit_origin_name(context.user_message)
        origin_name = explicit_origin or (getattr(origin_event, "location_name", None) if origin_event else self._default_origin_name(context))
        if location_name and origin_name and origin_name != location_name:
            payload["commute_origin"] = origin_name
            payload["commute_destination"] = location_name
            travel_duration = self._travel_minutes(context, origin_name=origin_name, destination_name=location_name)
            if travel_duration is not None:
                safety_minutes = self._safety_buffer_minutes(context)
                departure_time = start_time - timedelta(minutes=travel_duration + safety_minutes)
                travel_rationale = (
                    f"从{origin_name}到{location_name}预计约 {travel_duration} 分钟，"
                    f"建议 {departure_time.strftime('%H:%M')} 出发。"
                )
                risk_summaries.append(f"建议{departure_time.strftime('%H:%M')}出发")
                payload["travel_risks"].append(
                    {
                        "origin": origin_name,
                        "destination": location_name,
                        "travel_duration_minutes": travel_duration,
                        "safety_buffer_minutes": safety_minutes,
                        "departure_time": departure_time.isoformat(),
                    }
                )
                if origin_event and getattr(origin_event, "end_time", None) and origin_event.end_time > departure_time:
                    suggested_start = self._round_up_to_quarter(start_time + timedelta(minutes=travel_duration + safety_minutes))
                    travel_buffer_risk = {
                        "summary": (
                            f"出发缓冲不足，{getattr(origin_event, 'title', '上一日程')} "
                            f"{origin_event.end_time.strftime('%H:%M')} 才结束；建议将{title}推迟至 "
                            f"{suggested_start.strftime('%H:%M')}或更晚。"
                        ),
                        "suggested_start": suggested_start,
                    }
                    risk_summaries.append(f"出发缓冲不足，建议将{title}推迟至{suggested_start.strftime('%H:%M')}或更晚")
            elif explicit_origin:
                travel_rationale = f"我会按从{origin_name}出发理解这次行程；当前缺少通勤估算，确认前不会创建出发提醒。"
                risk_summaries.append(f"出发地按{origin_name}处理")

        adjacent_rationale = None
        adjacent_warning = self._adjacent_warning(context.events, start_time=start_time, location_name=location_name)
        if adjacent_warning:
            adjacent_rationale = adjacent_warning
            risk_summaries.append(adjacent_warning)
            payload["adjacent_warnings"].append(adjacent_warning)

        return {
            "direct_conflicts": direct_conflicts,
            "risk_summaries": risk_summaries,
            "departure_time": departure_time,
            "travel_duration_minutes": travel_duration,
            "travel_rationale": travel_rationale,
            "travel_buffer_risk": travel_buffer_risk,
            "adjacent_rationale": adjacent_rationale,
            "payload": payload,
        }

    @staticmethod
    def _find_direct_conflicts(events: list, *, start_time: datetime, end_time: datetime) -> list[dict]:
        conflicts: list[dict] = []
        for event in events:
            existing_start = getattr(event, "start_time", None)
            existing_end = getattr(event, "end_time", None)
            if not existing_start or not existing_end:
                continue
            if start_time < existing_end and end_time > existing_start:
                conflicts.append(
                    {
                        "event_id": getattr(event, "id", None),
                        "title": getattr(event, "title", None) or "已有日程",
                        "start_time": existing_start.isoformat(),
                        "end_time": existing_end.isoformat(),
                        "location_name": getattr(event, "location_name", None),
                    }
                )
        return conflicts

    @staticmethod
    def _previous_event(events: list, start_time: datetime):
        previous = None
        for event in events:
            end_time = getattr(event, "end_time", None)
            if end_time and end_time <= start_time and (previous is None or end_time > previous.end_time):
                previous = event
        return previous

    @staticmethod
    def _round_up_to_quarter(value: datetime) -> datetime:
        minute = ((value.minute + 14) // 15) * 15
        if minute >= 60:
            return value.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return value.replace(minute=minute, second=0, microsecond=0)

    @staticmethod
    def _safety_buffer_minutes(context: AssistantAgentContext) -> int:
        value = (context.external_context or {}).get("travel_safety_buffer_minutes", 10)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10

    @staticmethod
    def _default_origin_name(context: AssistantAgentContext) -> str | None:
        profile = context.profile
        if profile is None:
            return None
        return getattr(profile, "home_location_name", None) or getattr(profile, "work_location_name", None)

    @staticmethod
    def _explicit_origin_name(message: str | None) -> str | None:
        if not message:
            return None
        match = re.search(r"从\s*([\u4e00-\u9fa5A-Za-z0-9]{1,12})\s*(?:出发)?(?:去|到)", message)
        if not match:
            return None
        return match.group(1).strip()

    @staticmethod
    def _travel_minutes(context: AssistantAgentContext, *, origin_name: str, destination_name: str) -> int | None:
        estimates = (context.external_context or {}).get("travel_estimates")
        if isinstance(estimates, dict):
            for key in (
                f"{origin_name}->{destination_name}",
                f"{origin_name}到{destination_name}",
                f"{origin_name}-{destination_name}",
                destination_name,
            ):
                value = estimates.get(key)
                if value is not None:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return None
        default_commute = (context.external_context or {}).get("default_commute")
        if isinstance(default_commute, dict) and default_commute.get("duration_minutes") is not None:
            try:
                return int(round(float(default_commute["duration_minutes"])))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _adjacent_warning(events: list, *, start_time: datetime, location_name: str | None) -> str | None:
        for event in events:
            existing_end = getattr(event, "end_time", None)
            if existing_end != start_time:
                continue
            existing_location = getattr(event, "location_name", None)
            if location_name and existing_location and location_name != existing_location:
                return "两条日程之间无间隔，若涉及地点变更建议预留缓冲时间"
        return None

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

    def _build_task_schedule_proposal(self, slots: dict) -> ProposalDraft | None:
        task_id = slots.get("target_id")
        title = slots.get("target_title")
        schedule_blocks = slots.get("schedule_blocks") or []
        if not task_id or not title or not isinstance(schedule_blocks, list) or not schedule_blocks:
            return None

        actions: list[dict] = []
        block_summaries: list[str] = []
        block_total = len(schedule_blocks)
        for index, block in enumerate(schedule_blocks, start=1):
            block_date = block.get("date")
            start = block.get("start")
            end = block.get("end")
            if not block_date or not start or not end:
                return None
            start_time = datetime.fromisoformat(f"{block_date}T{start}:00")
            end_time = datetime.fromisoformat(f"{block_date}T{end}:00")
            event_title = f"{title}（第{index}/{block_total}段）" if block_total > 1 else title
            actions.append(
                {
                    "type": "create_event",
                    "payload": {
                        "title": event_title,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "linked_task_id": int(task_id),
                        "event_type": "focus_block",
                    },
                }
            )
            block_summaries.append(f"{start_time.strftime('%m-%d %H:%M')}-{end_time.strftime('%H:%M')}")

        summary = f"建议围绕任务“{title}”先安排 {block_total} 个专注时段：{'；'.join(block_summaries)}"
        return ProposalDraft(
            proposal_type="task_schedule_plan",
            summary=summary,
            recommended_option_id="A",
            is_time_sensitive=True,
            related_task_id=int(task_id),
            payload_json={
                "source": "conductor_v2",
                "proposal_shape": "task_schedule_plan",
                "schedule_block_count": block_total,
            },
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="按建议安排任务时段",
                    summary=summary,
                    actions=actions,
                    rationale="我会把这些时段作为和当前任务关联的专注块，确认前不会写入。",
                )
            ],
        )

    def _build_event_update_proposal(self, context: AssistantAgentContext, slots: dict) -> ProposalDraft | None:
        action_type = slots.get("action_type")
        if slots.get("target_scope") == "batch":
            return self._build_batch_event_update_proposal(context, slots)

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
            end_time = datetime.fromisoformat(end_raw) if end_raw else self._derive_rescheduled_end(context, int(event_id), start_time)
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
            event = self._find_event(context, int(event_id))
            if self._is_task_focus_block(event, title):
                summary = f"建议处理任务切片“{title}”：可本次跳过不补排，或取消后待补排"
                return ProposalDraft(
                    proposal_type="event_cancel",
                    summary=summary,
                    recommended_option_id="A",
                    is_time_sensitive=True,
                    related_event_id=int(event_id),
                    related_task_id=self._event_linked_task_id(event),
                    payload_json={
                        "source": "conductor_v1",
                        "target_title": title,
                        "requires_reschedule_choice": True,
                    },
                    options=[
                        ProposalOptionDraft(
                            option_id="A",
                            title="本次跳过，不补排",
                            summary=f"跳过任务切片“{title}”，不另行补排",
                            actions=[{"type": "cancel_event", "payload": {"event_id": int(event_id)}}],
                            rationale="确认后只取消这个切片，父任务不会被标记完成。",
                        ),
                        ProposalOptionDraft(
                            option_id="B",
                            title="取消，并待后续补排",
                            summary=f"取消任务切片“{title}”，后续再安排补排时间",
                            actions=[
                                {"type": "cancel_event", "payload": {"event_id": int(event_id)}},
                                {
                                    "type": "acknowledge_signal",
                                    "payload": {
                                        "signal_type": "task_block_reschedule_needed",
                                        "message": f"任务切片“{title}”已选择取消后待补排。",
                                    },
                                },
                            ],
                            rationale="确认后先取消这个切片，并保留需要后续补排的执行记录；父任务不会被标记完成。",
                        ),
                    ],
                )

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

    def _find_event(self, context: AssistantAgentContext, event_id: int):
        for event in context.events:
            if getattr(event, "id", None) == event_id:
                return event
        return None

    def _event_linked_task_id(self, event) -> int | None:
        if event is None:
            return None
        value = getattr(event, "linked_task_id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _is_task_focus_block(self, event, title: str) -> bool:
        if self._event_linked_task_id(event) is not None:
            return True
        if event is not None and getattr(event, "event_type", None) == "focus_block":
            return True
        return bool("复习" in title or "（第" in title and "段）" in title)

    def _build_batch_event_update_proposal(self, context: AssistantAgentContext, slots: dict) -> ProposalDraft | None:
        action_type = slots.get("action_type")
        target_ids = [int(event_id) for event_id in slots.get("target_ids", []) if event_id is not None]
        if not action_type or not target_ids:
            return None
        target_titles = [str(title) for title in slots.get("target_titles", []) if title]
        count = len(target_ids)
        target_date = slots.get("target_date")
        title_preview = "、".join(target_titles[:3])
        if len(target_titles) > 3:
            title_preview += "等"

        if action_type == "cancel_event":
            summary = f"建议取消 {target_date} 的 {count} 个日程"
            if title_preview:
                summary += f"：{title_preview}"
            return ProposalDraft(
                proposal_type="event_batch_cancel",
                summary=summary,
                recommended_option_id="A",
                is_time_sensitive=True,
                payload_json={
                    "source": "conductor_v1",
                    "target_scope": "batch",
                    "target_date": target_date,
                    "target_event_ids": target_ids,
                    "target_titles": target_titles,
                    "batch_action_count": count,
                },
                options=[
                    ProposalOptionDraft(
                        option_id="A",
                        title="取消这批日程",
                        summary=summary,
                        actions=[{"type": "cancel_event", "payload": {"event_id": event_id}} for event_id in target_ids],
                        rationale="确认后会逐个取消这些日程；取消会保留历史记录，不会物理删除。",
                    )
                ],
            )

        if action_type == "reschedule_event":
            shift_days = slots.get("batch_shift_days")
            destination_date_raw = slots.get("batch_destination_date")
            if shift_days is None and not destination_date_raw:
                return None
            try:
                shift_days_int = int(shift_days) if shift_days is not None else None
                destination_date = datetime.fromisoformat(destination_date_raw).date() if destination_date_raw else None
            except (TypeError, ValueError):
                return None
            events_by_id = {getattr(event, "id", None): event for event in context.events}
            actions: list[dict] = []
            for event_id in target_ids:
                event = events_by_id.get(event_id)
                if event is None:
                    return None
                old_start = getattr(event, "start_time", None)
                old_end = getattr(event, "end_time", None)
                if old_start is None or old_end is None:
                    return None
                if destination_date is not None:
                    new_start = datetime.combine(destination_date, old_start.timetz()).replace(tzinfo=old_start.tzinfo)
                    new_end = new_start + (old_end - old_start)
                elif shift_days_int is not None:
                    new_start = old_start + timedelta(days=shift_days_int)
                    new_end = old_end + timedelta(days=shift_days_int)
                else:
                    return None
                actions.append(
                    {
                        "type": "reschedule_event",
                        "payload": {
                            "event_id": event_id,
                            "update": {
                                "start_time": new_start.isoformat(),
                                "end_time": new_end.isoformat(),
                            },
                        },
                    }
                )
            if destination_date is not None:
                summary = f"建议把 {target_date} 的 {count} 个日程整体改到 {destination_date.isoformat()}"
                option_title = "改期这批日程"
            else:
                direction = "推迟" if shift_days_int and shift_days_int > 0 else "提前"
                day_count = abs(shift_days_int or 0)
                summary = f"建议把 {target_date} 的 {count} 个日程整体{direction} {day_count} 天"
                option_title = "整体顺延这批日程"
            if title_preview:
                summary += f"：{title_preview}"
            payload_json = {
                "source": "conductor_v1",
                "target_scope": "batch",
                "target_date": target_date,
                "target_event_ids": target_ids,
                "target_titles": target_titles,
                "batch_action_count": count,
            }
            if shift_days_int is not None:
                payload_json["batch_shift_days"] = shift_days_int
            if destination_date is not None:
                payload_json["batch_destination_date"] = destination_date.isoformat()
            return ProposalDraft(
                proposal_type="event_batch_reschedule",
                summary=summary,
                recommended_option_id="A",
                is_time_sensitive=True,
                payload_json=payload_json,
                options=[
                    ProposalOptionDraft(
                        option_id="A",
                        title=option_title,
                        summary=summary,
                        actions=actions,
                        rationale="确认后会逐个保留原时间段，只移动日期。",
                    )
                ],
            )
        return None

    def _build_task_update_proposal(self, context: AssistantAgentContext, slots: dict) -> ProposalDraft | None:
        task_id = slots.get("target_id")
        title = slots.get("target_title") or "这个任务"
        if not task_id:
            return None
        task_id_int = int(task_id)
        linked_completion_events = self._linked_events_to_complete_for_task(context, task_id_int)
        if linked_completion_events:
            count = len(linked_completion_events)
            summary = f"建议把任务“{title}”及 {count} 个执行块标记为完成"
            actions = [
                {"type": "mark_event_completed", "payload": {"event_id": int(getattr(event, "id"))}}
                for event in linked_completion_events
                if getattr(event, "id", None) is not None
            ]
            actions.append({"type": "mark_task_completed", "payload": {"task_id": task_id_int}})
            rationale = "确认后会先逐个完成关联执行块，再把父任务标记完成。"
        else:
            summary = f"建议把任务“{title}”标记为完成"
            actions = [{"type": "mark_task_completed", "payload": {"task_id": task_id_int}}]
            rationale = "确认后会把任务状态改为完成。"
        return ProposalDraft(
            proposal_type="task_status_update",
            summary=summary,
            recommended_option_id="A",
            is_time_sensitive=False,
            related_task_id=task_id_int,
            payload_json={"source": "conductor_v1", "target_title": title},
            options=[
                ProposalOptionDraft(
                    option_id="A",
                    title="标记任务完成",
                    summary=summary,
                    actions=actions,
                    rationale=rationale,
                )
            ],
        )

    def _linked_events_to_complete_for_task(self, context: AssistantAgentContext, task_id: int) -> list:
        if not re.search(r"(?:都|全部|全都|这三天|这些|每个).{0,8}(?:完成|做完|结束)", context.user_message):
            return []
        events = [
            event
            for event in context.events
            if getattr(event, "linked_task_id", None) == task_id
            and (getattr(event, "status", None) or "planned") not in {"completed", "canceled", "cancelled"}
        ]
        return sorted(events, key=lambda event: getattr(event, "start_time", datetime.max) or datetime.max)

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
