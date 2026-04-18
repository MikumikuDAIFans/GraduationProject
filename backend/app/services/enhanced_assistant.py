"""Enhanced assistant service integrating vector store, habit learning, and conflict detection."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from loguru import logger
from pydantic import ValidationError

from app.core.vector_store import VectorStore
from app.main import get_vector_store
from app.repositories.habits import HabitRepository
from app.schemas.assistant_actions import AssistantAction, AssistantResponse, ClarifyAction, CreateEventAction
from app.services.conflict_detector import ConflictDetector
from app.services.dialog_state import DialogStateManager, DialogState
from app.services.habit_collector import HabitCollector
from app.services.habit_retriever import HabitRetriever
from app.db.session import get_sessionmaker


class EnhancedAssistantMixin:
    """Mixin that adds V6 capabilities to the existing AssistantService."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vector_store = get_vector_store()
        self.habit_retriever = HabitRetriever(self.vector_store)
        self.conflict_detector = ConflictDetector()
        self.dialog_manager = DialogStateManager()
        self._habit_collector: Optional[HabitCollector] = None

    def _get_habit_collector(self) -> HabitCollector:
        """Lazy-initialize the habit collector."""
        if self._habit_collector is None:
            self._habit_collector = HabitCollector(
                self.vector_store,
                HabitRepository(next(get_sessionmaker())()),
            )
        return self._habit_collector

    async def process_with_enhancements(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> AssistantResponse:
        """Process user message with V6 enhancements:
        1. Multi-turn dialog state management
        2. Habit-based suggestions
        3. Conflict detection for proposed events
        4. Conversational habit collection
        """
        # 1. Get or create dialog state
        if session_id:
            state = await self.dialog_manager.get_or_create(session_id)
        else:
            session_id = f"session_{datetime.utcnow().isoformat()}"
            state = await self.dialog_manager.get_or_create(session_id)

        # 2. Check if we're in a slot-filling conversation
        if not state.is_complete() and state.intent:
            # Process this turn to fill missing slots
            state = await self._process_slot_filling(state, message)

            if not state.is_complete():
                # Still missing slots, ask for clarification
                question = self.dialog_manager.get_clarification_question(state)
                await self.dialog_manager.save(state)

                return AssistantResponse(
                    reply=question or "请提供更多信息",
                    actions=[
                        ClarifyAction(
                            missing_fields=state.get_remaining_required(),
                            question=question or "请提供更多信息",
                        )
                    ],
                    session_id=session_id,
                    waiting_for_input=True,
                )

            # All slots filled, proceed with action
            await self.dialog_manager.clear(session_id)

        # 3. Collect habits conversationally
        try:
            await self._get_habit_collector().on_user_statement(message, user_id)
        except Exception as e:
            logger.warning(f"Conversational habit collection failed: {e}")

        # 4. Delegate to parent service for actual processing
        # This will be called by the wrapper
        return await self._process_with_parent(user_id, message, session_id)

    async def _process_slot_filling(
        self,
        state: DialogState,
        message: str,
    ) -> DialogState:
        """Process one turn of slot filling."""
        # Simple keyword-based extraction (Phase 1)
        # Phase 2 will use LLM-based extraction
        for slot_def in list(state.missing_slots):
            # Check if the message contains time-related keywords
            if slot_def.name in ["start_time", "deadline"]:
                time_match = self._extract_time_from_text(message)
                if time_match:
                    state.slots[slot_def.name] = time_match
                    state.missing_slots.remove(slot_def)
            elif slot_def.name == "title" and len(message) > 2:
                state.slots[slot_def.name] = message
                state.missing_slots.remove(slot_def)
            elif slot_def.name == "content" and len(message) > 2:
                state.slots[slot_def.name] = message
                state.missing_slots.remove(slot_def)

        state.turn_count += 1
        return state

    @staticmethod
    def _extract_time_from_text(text: str) -> Optional[str]:
        """Simple time extraction from text (Phase 1 implementation)."""
        import re

        # Match patterns like "明天下午3点", "下周一10:30"
        patterns = [
            r"(\d{1,2}):(\d{2})",  # 10:30
            r"(\d{1,2})点",  # 3点
            r"(今天|明天|后天|下周一|下周二|下周三|下周四|下周五|周六|周日)",  # Relative dates
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    async def _process_with_parent(
        self,
        user_id: str,
        message: str,
        session_id: str,
    ) -> AssistantResponse:
        """Delegate to parent service and enhance the response."""
        # Call parent's process_message method
        # This assumes the parent class has a process_message method
        try:
            parent_response = await self.process_message(user_id, message, session_id)
        except AttributeError:
            # Fallback if parent doesn't have process_message
            parent_response = AssistantResponse(reply="处理中...", actions=[])

        # Enhance with habit-based suggestions
        try:
            suggestions = await self.habit_retriever.suggest_time(
                activity=message[:50],
                user_id=user_id,
            )
            if suggestions:
                logger.info(f"Habit suggestion for '{message[:30]}': {suggestions}")
        except Exception as e:
            logger.warning(f"Habit suggestion failed: {e}")

        return parent_response

    async def check_proposed_event_conflicts(
        self,
        event_data: dict[str, Any],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Check if a proposed event conflicts with existing events."""
        # Get all events for the user on the same day
        from app.db.session import get_sessionmaker
        from app.repositories.events import EventRepository
        from datetime import timedelta

        async with get_sessionmaker()() as session:
            event_repo = EventRepository(session)
            events = await event_repo.get_by_date(user_id, event_data.get("date"))

        if not events:
            return []

        # Create a mock event object for conflict detection
        class MockEvent:
            def __init__(self, data):
                self.id = data.get("id", 0)
                self.start_time = data.get("start_time")
                self.end_time = data.get("end_time")
                self.buffer_before = data.get("buffer_before", 0)
                self.buffer_after = data.get("buffer_after", 0)
                self.location_coords = data.get("location_coords")

        mock_event = MockEvent(event_data)
        all_events = [mock_event] + events

        conflicts = self.conflict_detector.detect_conflicts(all_events)

        conflict_results = []
        for conflict in conflicts:
            conflict_results.append({
                "conflicting_event_id": conflict.event_b_id,
                "conflict_type": conflict.conflict_type,
                "overlap_minutes": conflict.overlap_minutes,
            })

        return conflict_results

    async def suggest_alternative_times(
        self,
        event_data: dict[str, Any],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Suggest alternative times for a conflicted event."""
        from app.db.session import get_sessionmaker
        from app.repositories.events import EventRepository
        from datetime import timedelta

        async with get_sessionmaker()() as session:
            event_repo = EventRepository(session)
            events = await event_repo.get_by_date(user_id, event_data.get("date"))

        if not events:
            return []

        class MockEvent:
            def __init__(self, data):
                self.id = data.get("id", 0)
                self.start_time = data.get("start_time")
                self.end_time = data.get("end_time")

        mock_event = MockEvent(event_data)
        alternatives = self.conflict_detector.suggest_alternatives(mock_event, events)

        return alternatives
