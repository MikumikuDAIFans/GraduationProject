"""Clarification specialist for ambiguous task/event requests."""

from __future__ import annotations

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState


class TaskOrEventClarifierSpecialist:
    name = "task_or_event_clarifier"

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        understanding = state.understanding
        if understanding is None:
            state.clarification_question = "我还没有理解这件事。你想把它作为一次性日程，还是作为需要持续跟进的任务？"
            return state
        orchestration_question = self._build_orchestration_clarification(state)
        if orchestration_question:
            state.clarification_question = orchestration_question
            state.metadata["clarification_source"] = "orchestration"
            return state
        if understanding.orchestration is not None:
            state.metadata["clarification_source"] = "specialized_fallback"

        if understanding.goal_type == "event":
            ambiguity_set = set(understanding.ambiguities)
            if "batch_event_date_missing" in ambiguity_set:
                state.clarification_question = "你想批量操作日程，但还缺日期范围。请告诉我是今天、明天，还是某个具体日期。"
                return state
            if "batch_event_target_too_large" in ambiguity_set:
                state.clarification_question = "这批日程数量有点多。请把范围缩小到某一天、某类日程，或分批确认。"
                return state
            if "batch_reschedule_shift_missing" in ambiguity_set:
                state.clarification_question = "我可以批量移动这些日程，但需要一个明确的移动规则，比如“整体推迟一天”或“提前两天”。"
                return state
            if "medical_location_conflict" in ambiguity_set:
                state.clarification_question = "你是要去校医院，还是校外医院？如果地点还有其他细节，也请一起告诉我。"
                return state
            if "target_event_ambiguous" in ambiguity_set:
                candidates = understanding.slots.get("candidate_titles") or []
                suffix = f"我看到可能相关的是：{'、'.join(candidates)}。" if candidates else ""
                state.clarification_question = f"我还不能确定你要操作哪一个日程。{suffix}请告诉我更具体的日程名称或时间。"
                return state
            if "target_event_not_found" in ambiguity_set:
                state.clarification_question = "我没有在当前日程里找到你要操作的目标。请告诉我更具体的日程名称、时间或地点。"
                return state
            if "reschedule_time_missing" in ambiguity_set:
                state.clarification_question = "你想调整这个日程，但还缺新的时间。请告诉我希望改到哪天几点，或者给一个可选时间段。"
                return state
            if "dating_request_too_vague" in understanding.ambiguities:
                state.clarification_question = (
                    "这更像一个还没成形的日程想法。你希望我把它当成一次性日程来安排，"
                    "还是先帮你一起规划？请告诉我大概日期、时间段、地点，以及预计持续多久。"
                )
                return state
            missing = set(understanding.missing_fields)
            if "start_time" in missing:
                state.clarification_question = "我可以帮你安排这个日程，但还缺具体开始时间或可选时间段。你希望放在哪天、哪个时间段？"
            elif "title" in missing:
                state.clarification_question = "这件事的日程标题还不清楚。你想让我把它记成什么事项？"
            elif "end_time_or_duration" in missing:
                state.clarification_question = "这个日程大概持续多久？如果你愿意，我也可以先按 1 小时给你出方案。"
            else:
                state.clarification_question = "这个日程还有关键信息不确定。你能补充时间、地点或持续时长吗？"
            return state

        if understanding.goal_type == "task":
            ambiguity_set = set(understanding.ambiguities)
            if understanding.intent == "plan_task_schedule":
                if "target_task_ambiguous" in ambiguity_set:
                    candidates = understanding.slots.get("candidate_titles") or []
                    suffix = f"我看到你可能是在继续这些任务：{'、'.join(candidates)}。" if candidates else ""
                    state.clarification_question = f"我还不能确定你想继续规划哪一个任务。{suffix}请直接说任务名，或者用“这个任务”。"
                    return state
                if "target_task_not_found" in ambiguity_set:
                    state.clarification_question = "我没能把这次排程绑定到一个明确任务上。请告诉我是哪一个任务，或者先确认前一个相关方案。"
                    return state
                if "schedule_time_missing" in ambiguity_set:
                    state.clarification_question = "我知道你是在继续规划这个任务了，但还缺具体时段。请告诉我想放在哪天、几点到几点。"
                    return state
            if "target_task_ambiguous" in ambiguity_set:
                candidates = understanding.slots.get("candidate_titles") or []
                suffix = f"我看到可能相关的是：{'、'.join(candidates)}。" if candidates else ""
                state.clarification_question = f"我还不能确定你要操作哪一个任务。{suffix}请告诉我更具体的任务名称。"
                return state
            if "target_task_not_found" in ambiguity_set:
                state.clarification_question = "我没有在当前任务里找到你要操作的目标。请告诉我更具体的任务名称或截止时间。"
                return state
            if "generic_study_task" in understanding.ambiguities:
                state.clarification_question = (
                    "我会把“复习”当成一个需要拆成日程块跟进的任务处理。"
                    "你要复习什么科目或内容？目标截止时间是什么？希望每天复习、隔天复习，还是集中安排？"
                )
                return state
            state.clarification_question = "这是一个任务还是一次性日程还不够明确。你希望我持续跟进它，还是只安排一个具体时间块？"
            return state

        state.clarification_question = "你希望把这件事当成一次性日程，还是需要拆成多个日程组合成的任务？"
        return state

    def _build_orchestration_clarification(self, state: ConductorState) -> str | None:
        understanding = state.understanding
        if understanding is None or understanding.orchestration is None:
            return None
        if "medical_location_conflict" in set(understanding.ambiguities):
            return "你是要去校医院，还是校外医院？如果地点还有其他细节，也请一起告诉我。"
        orchestration = understanding.orchestration
        if orchestration.conversation_mode != "clarification":
            return None

        missing = list(orchestration.missing_information or understanding.missing_fields or [])
        if orchestration.user_goal == "unknown" and "goal_type" in missing:
            return (
                "我还没确定你想让我产出什么结果。"
                "请告诉我是要创建/调整日程、拆解并安排任务，还是只基于现有事项给你建议；"
                "如果有时间、地点、截止时间或偏好，也一起补充。"
            )

        if orchestration.user_goal in {"cancel_event", "reschedule_event", "complete_event", "update_event"}:
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "target_event": "要操作的具体日程",
                    "new_start_time": "新的日期和具体时间，或一个可选时间段",
                },
            )
            if requested_parts:
                action_labels = {
                    "cancel_event": "取消日程",
                    "reschedule_event": "改期日程",
                    "complete_event": "完成日程",
                    "update_event": "更新日程",
                }
                action_label = action_labels.get(orchestration.user_goal, "更新日程")
                candidate_labels = orchestration.target_scope.candidate_labels
                suffix = f"我看到可能相关的是：{'、'.join(candidate_labels)}。" if candidate_labels else ""
                return (
                    f"我先把这理解成{action_label}请求。{suffix}"
                    f"为了生成可确认的{action_label}方案，还需要补充：{requested_parts}。"
                )

        if orchestration.user_goal == "schedule_blocks" and orchestration.proposal_shape == "task_schedule_plan":
            label = orchestration.target_scope.label or "这个任务"
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "target_task": "要继续规划的具体任务",
                    "time_preferences": "希望安排到哪天、几点到几点，或可接受的时间段",
                },
            )
            if requested_parts:
                candidate_labels = orchestration.target_scope.candidate_labels
                suffix = f"我看到可能相关的是：{'、'.join(candidate_labels)}。" if candidate_labels else ""
                return (
                    f"我先把“{label}”理解成继续规划任务请求。{suffix}"
                    f"为了生成可确认的任务排程方案，还需要补充：{requested_parts}。"
                )

        if orchestration.user_goal in {"complete_task", "update_target"}:
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "target_task": "要操作的具体任务",
                },
            )
            if requested_parts:
                action_label = "完成任务" if orchestration.user_goal == "complete_task" else "更新任务"
                candidate_labels = orchestration.target_scope.candidate_labels
                suffix = f"我看到可能相关的是：{'、'.join(candidate_labels)}。" if candidate_labels else ""
                return (
                    f"我先把这理解成{action_label}请求。{suffix}"
                    f"为了生成可确认的{action_label}方案，还需要补充：{requested_parts}。"
                )

        if orchestration.user_goal in {"cancel_events_batch", "reschedule_events_batch"}:
            label = orchestration.target_scope.label or "这批日程"
            if "batch_event_target_too_large" in set(understanding.ambiguities):
                count = understanding.slots.get("candidate_count")
                candidate_labels = orchestration.target_scope.candidate_labels
                preview = f"，包括：{'、'.join(candidate_labels)} 等" if candidate_labels else ""
                count_text = f"{count} 个" if count else "较多"
                return (
                    f"我先把“{label}”理解成批量操作请求，但这次会影响 {count_text}日程{preview}，范围过大。"
                    "请缩小到某一类事项、指定更小的时间范围，或分批确认；在你明确拆分前我不会执行任何取消或改期。"
                )
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "target_event": "要操作的日期或日期范围",
                    "target_date": "要操作的日期或日期范围",
                    "batch_shift_days": "整体移动规则，比如推迟一天、提前两天，或改到某个日期",
                },
            )
            action_label = "批量改期" if orchestration.user_goal == "reschedule_events_batch" else "批量取消"
            if requested_parts:
                return f"我先把“{label}”理解成{action_label}请求。为了生成可确认的批量方案，还需要补充：{requested_parts}。"

        if orchestration.user_goal == "create_task" and orchestration.proposal_shape == "task_creation":
            label = orchestration.target_scope.label or understanding.slots.get("content") or "这个任务"
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "subject": "复习的科目或具体内容",
                    "deadline_or_time_window": "目标截止时间或希望完成的时间范围",
                    "rhythm": "每天、隔天还是集中安排的节奏",
                    "content": "任务内容",
                },
            )
            if requested_parts:
                return (
                    f"我先把“{label}”理解成一个需要持续跟进的任务。"
                    f"为了给你生成可确认的任务/排程方案，还需要补充：{requested_parts}。"
                )

        if (
            orchestration.user_goal == "create_event"
            and orchestration.proposal_shape == "event_creation"
            and "dating_request_too_vague" not in set(understanding.ambiguities)
        ):
            label = orchestration.target_scope.label or understanding.slots.get("title") or "这个日程"
            requested_parts = self._format_missing_parts(
                missing,
                {
                    "title": "日程标题",
                    "start_time": "开始时间或可选时间段",
                    "end_time_or_duration": "结束时间或预计持续多久",
                    "location_name": "地点",
                    "intent_detail": "具体事项",
                },
            )
            if requested_parts:
                return (
                    f"我先把“{label}”理解成一个待安排日程。"
                    f"为了给你生成可确认的日程方案，还需要补充：{requested_parts}。"
                )

        return None

    def _format_missing_parts(self, missing: list[str], labels: dict[str, str]) -> str:
        parts = [labels[item] for item in missing if item in labels]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return "、".join(parts[:-1]) + f"，以及{parts[-1]}"
