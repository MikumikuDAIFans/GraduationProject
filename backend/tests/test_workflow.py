"""Tests for LangGraph workflow nodes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.workflow.nodes import WorkflowNodes
from app.workflow.state import WorkflowState


def make_state(**overrides) -> WorkflowState:
    base: WorkflowState = {
        "user_message": "明天下午开会",
        "user_id": "user-1",
        "session_id": "sess-1",
        "intent": None,
        "extracted_slots": {},
        "confidence": 0.0,
        "existing_events": [],
        "existing_tasks": [],
        "habits": [],
        "weather": None,
        "traffic": None,
        "actions": [],
        "conflicts": [],
        "suggestions": [],
        "reply": "",
        "needs_clarification": False,
        "clarification_question": None,
        "retry_count": 0,
    }
    base.update(overrides)
    return base


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestParseIntent:
    def test_parse_intent_sets_fields(self):
        state = make_state(user_message="Remind me to call John at 3pm")
        result = run_async(WorkflowNodes.parse_intent(state))

        assert "intent" in result
        assert "extracted_slots" in result
        assert "confidence" in result

    def test_parse_intent_handles_empty_message(self):
        state = make_state(user_message="")
        result = run_async(WorkflowNodes.parse_intent(state))
        # Should return valid state even with empty message
        assert "intent" in result


class TestCollectContext:
    def test_collect_context_no_services(self):
        state = make_state(
            extracted_slots={"activity": "meeting"},
            event_service=None,
            task_service=None,
            habit_retriever=None,
            weather_service=None,
            maps_service=None,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        assert result.get("existing_events") == []
        assert result.get("existing_tasks") == []
        assert result.get("habits") == []

    def test_collect_context_with_event_service(self):
        mock_event_service = AsyncMock()
        mock_event_service.get_relevant_events.return_value = [
            {"id": "evt-1", "title": "Team Standup"}
        ]
        state = make_state(
            intent="query_events",
            extracted_slots={"time_range": "today"},
            event_service=mock_event_service,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        mock_event_service.get_relevant_events.assert_called_once()
        assert len(result.get("existing_events", [])) == 1

    def test_collect_context_with_task_service(self):
        mock_task_service = AsyncMock()
        mock_task_service.get_active_tasks.return_value = [
            {"id": "task-1", "title": "Write report"}
        ]
        state = make_state(
            intent="query_tasks",
            extracted_slots={},
            task_service=mock_task_service,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        mock_task_service.get_active_tasks.assert_called_once()
        assert len(result.get("existing_tasks", [])) == 1

    def test_collect_context_with_habit_retriever(self):
        mock_habit_retriever = AsyncMock()
        mock_habit_retriever.get_relevant_habits.return_value = [
            {"id": "habit-1", "activity": "gym"}
        ]
        state = make_state(
            intent="schedule_guidance",
            extracted_slots={"activity": "gym"},
            habit_retriever=mock_habit_retriever,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        mock_habit_retriever.get_relevant_habits.assert_called_once()
        assert len(result.get("habits", [])) == 1

    def test_collect_context_empty_activity_skips_habit(self):
        mock_habit_retriever = AsyncMock()
        state = make_state(
            extracted_slots={},
            habit_retriever=mock_habit_retriever,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        mock_habit_retriever.get_relevant_habits.assert_not_called()
        assert result.get("habits") == []

    def test_collect_context_with_weather_and_traffic(self):
        mock_weather = AsyncMock()
        mock_weather.get_weather.return_value = {"temp": 25, "condition": "sunny"}
        mock_maps = AsyncMock()
        mock_maps.estimate_travel_time.return_value = {"duration_minutes": 30}

        state = make_state(
            intent="event_context_advice",
            extracted_slots={"location": "Office"},
            weather_service=mock_weather,
            maps_service=mock_maps,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        assert result.get("weather") is not None
        assert result.get("traffic") is not None

    def test_collect_context_handles_exception(self):
        mock_event_service = AsyncMock()
        mock_event_service.get_relevant_events.side_effect = Exception("API error")
        state = make_state(
            extracted_slots={},
            event_service=mock_event_service,
        )
        result = run_async(WorkflowNodes.collect_context(state))
        # Should have defaults, not crash
        assert result.get("existing_events") == []


class TestScheduleDecision:
    def test_schedule_decision_with_conflict_detector(self):
        mock_detector = MagicMock()
        mock_detector.detect_conflicts.return_value = [{"event1": "evt-1", "event2": "new"}]
        mock_detector.suggest_alternatives.return_value = [{"time": "15:00", "reason": "Free slot"}]
        state = make_state(
            intent="create_event",
            extracted_slots={"new_event": {"title": "Meeting", "start": "2026-04-15T14:00:00"}},
            conflict_detector=mock_detector,
            existing_events=[{"title": "Existing"}],
        )
        result = run_async(WorkflowNodes.schedule_decision(state))
        mock_detector.detect_conflicts.assert_called_once()
        assert len(result.get("conflicts", [])) == 1
        assert len(result.get("suggestions", [])) == 1

    def test_schedule_decision_no_conflicts(self):
        mock_detector = MagicMock()
        mock_detector.detect_conflicts.return_value = []
        state = make_state(
            intent="create_event",
            extracted_slots={"new_event": {"title": "Meeting"}},
            conflict_detector=mock_detector,
            existing_events=[],
        )
        result = run_async(WorkflowNodes.schedule_decision(state))
        mock_detector.detect_conflicts.assert_called_once()
        assert result.get("conflicts") == []

    def test_schedule_decision_task_creation(self):
        state = make_state(
            intent="create_task",
            extracted_slots={"task": {"title": "Write report", "priority": "high"}},
            task_service=MagicMock(),
        )
        result = run_async(WorkflowNodes.schedule_decision(state))
        actions = result.get("actions", [])
        assert len(actions) == 1
        assert actions[0]["type"] == "create_task"

    def test_schedule_decision_no_matching_intent(self):
        state = make_state(
            intent="query_schedule",
            extracted_slots={},
        )
        result = run_async(WorkflowNodes.schedule_decision(state))
        # Should return state unchanged for unrecognized intents
        assert result.get("conflicts") == []


class TestExecuteTools:
    def test_execute_tools_create_event(self):
        mock_event_service = AsyncMock()
        mock_event_service.create_event.return_value = {"id": "evt-1"}
        state = make_state(
            actions=[{
                "type": "create_event",
                "payload": {"title": "Team Meeting", "start": "2026-04-15T14:00:00"},
            }],
            event_service=mock_event_service,
        )
        result = run_async(WorkflowNodes.execute_tools(state))
        mock_event_service.create_event.assert_called_once()

    def test_execute_tools_create_task(self):
        mock_task_service = AsyncMock()
        mock_task_service.create_task.return_value = {"id": "task-1"}
        state = make_state(
            actions=[{
                "type": "create_task",
                "payload": {"title": "Buy groceries", "priority": "medium"},
            }],
            task_service=mock_task_service,
        )
        result = run_async(WorkflowNodes.execute_tools(state))
        mock_task_service.create_task.assert_called_once()

    def test_execute_tools_update_event(self):
        mock_event_service = AsyncMock()
        state = make_state(
            actions=[{
                "type": "update_event",
                "payload": {"event_id": "evt-1", "title": "Updated Meeting"},
            }],
            event_service=mock_event_service,
        )
        run_async(WorkflowNodes.execute_tools(state))
        mock_event_service.update_event.assert_called_once()

    def test_execute_tools_delete_event(self):
        mock_event_service = AsyncMock()
        state = make_state(
            actions=[{
                "type": "delete_event",
                "payload": {"event_id": "evt-1"},
            }],
            event_service=mock_event_service,
        )
        run_async(WorkflowNodes.execute_tools(state))
        mock_event_service.delete_event.assert_called_once_with("evt-1")

    def test_execute_tools_multiple_actions(self):
        mock_event_service = AsyncMock()
        mock_task_service = AsyncMock()
        state = make_state(
            actions=[
                {"type": "create_event", "payload": {"title": "Meeting"}},
                {"type": "create_task", "payload": {"title": "Prep slides"}},
            ],
            event_service=mock_event_service,
            task_service=mock_task_service,
        )
        result = run_async(WorkflowNodes.execute_tools(state))
        assert mock_event_service.create_event.called
        assert mock_task_service.create_task.called

    def test_execute_tools_handles_failure(self):
        mock_event_service = AsyncMock()
        mock_event_service.create_event.side_effect = Exception("DB error")
        state = make_state(
            actions=[{
                "type": "create_event",
                "payload": {"title": "Meeting"},
            }],
            event_service=mock_event_service,
        )
        result = run_async(WorkflowNodes.execute_tools(state))
        # Should not crash, should set error reply
        assert "reply" in result
        assert "出错" in result["reply"]


class TestClarifyAndRetry:
    def test_clarify_sets_reply_when_needs_clarification(self):
        state = make_state(
            needs_clarification=True,
            clarification_question="会议的具体时间",
        )
        result = run_async(WorkflowNodes.clarify_and_retry(state))
        assert "会议的具体时间" in result.get("reply", "")
        assert result.get("retry_count", 0) >= 1

    def test_clarify_does_nothing_without_flag(self):
        state = make_state(
            needs_clarification=False,
            retry_count=0,
        )
        result = run_async(WorkflowNodes.clarify_and_retry(state))
        assert result.get("retry_count", 0) == 0

    def test_clarify_increments_retry_count(self):
        state = make_state(
            needs_clarification=True,
            clarification_question="任务的优先级",
            retry_count=2,
        )
        result = run_async(WorkflowNodes.clarify_and_retry(state))
        assert result.get("retry_count", 0) == 3


class TestRenderResponse:
    def test_render_response_with_actions(self):
        state = make_state(
            intent="create_event",
            actions=[{"type": "create_event", "payload": {"title": "Meeting"}}],
        )
        result = run_async(WorkflowNodes.render_response(state))
        assert "Meeting" in result.get("reply", "")

    def test_render_response_with_conflicts(self):
        state = make_state(
            intent="create_event",
            conflicts=[{"event1": "evt-1", "event2": "evt-2"}],
            suggestions=[{"time": "15:00", "reason": "Free slot"}],
        )
        result = run_async(WorkflowNodes.render_response(state))
        assert "冲突" in result.get("reply", "")
        assert "15:00" in result.get("reply", "")

    def test_render_response_with_habits(self):
        state = make_state(
            intent="create_event",
            habits=[{"description": "You usually exercise at 7am"}],
        )
        result = run_async(WorkflowNodes.render_response(state))
        assert "习惯" in result.get("reply", "")

    def test_render_response_default_query(self):
        state = make_state(intent="query_events")
        result = run_async(WorkflowNodes.render_response(state))
        assert "查询" in result.get("reply", "")

    def test_render_response_handles_exception(self):
        state = make_state()
        # Remove actions key entirely to test default path
        del state["actions"]
        result = run_async(WorkflowNodes.render_response(state))
        # Should handle gracefully with default reply
        assert "reply" in result


class TestRouteAfterDecision:
    def test_route_clarify_when_needs_clarification(self):
        from app.workflow.graph import route_after_decision
        state = make_state(needs_clarification=True)
        assert route_after_decision(state) == "clarify"

    def test_route_execute_when_has_actions(self):
        from app.workflow.graph import route_after_decision
        state = make_state(actions=[{"type": "create_event"}])
        assert route_after_decision(state) == "execute"

    def test_route_render_when_no_actions_no_clarification(self):
        from app.workflow.graph import route_after_decision
        state = make_state(intent="query_schedule", actions=[])
        assert route_after_decision(state) == "render"


class TestWorkflowNodesInit:
    def test_init_with_all_services(self):
        # Use simple objects instead of MagicMock to avoid TypedDict conflicts
        class DummyService:
            pass
        nodes = WorkflowNodes(
            intent_parser=DummyService(),
            event_service=DummyService(),
            task_service=DummyService(),
            habit_retriever=DummyService(),
            conflict_detector=DummyService(),
            weather_service=DummyService(),
            maps_service=DummyService(),
            dialog_manager=DummyService(),
            response_formatter=DummyService(),
        )
        assert nodes.intent_parser is not None
        assert nodes.event_service is not None
        assert nodes.conflict_detector is not None

    def test_init_with_no_services(self):
        nodes = WorkflowNodes()
        assert nodes.intent_parser is None
        assert nodes.event_service is None
        assert nodes.conflict_detector is None
