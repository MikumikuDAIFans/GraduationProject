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

        if understanding.goal_type == "event":
            ambiguity_set = set(understanding.ambiguities)
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
