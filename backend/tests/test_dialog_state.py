"""Tests for the dialog state management service."""

from __future__ import annotations

import asyncio

import pytest

from app.services.dialog_state import (
    CREATE_EVENT_SLOTS,
    CREATE_TASK_SLOTS,
    DialogState,
    DialogStateManager,
    SlotDefinition,
    SlotFiller,
)


class TestSlotDefinition:
    """Test SlotDefinition creation."""

    def test_create_required_slot(self):
        slot = SlotDefinition("title", required=True, prompt="标题是什么？")
        assert slot.name == "title"
        assert slot.required is True
        assert slot.prompt == "标题是什么？"

    def test_create_optional_slot(self):
        slot = SlotDefinition("location", required=False, prompt="在哪里？")
        assert slot.required is False


class TestDialogState:
    """Test DialogState creation and management."""

    def test_create_dialog_state(self):
        state = DialogState(session_id="sess-1")
        assert state.session_id == "sess-1"
        assert state.slots == {}
        assert state.missing_slots == []
        assert state.turn_count == 0
        assert state.is_complete() is True

    def test_is_complete_with_missing_slots(self):
        state = DialogState(
            session_id="sess-1",
            missing_slots=[SlotDefinition("title", required=True, prompt="标题？")],
        )
        assert state.is_complete() is False

    def test_next_missing_slot(self):
        slot1 = SlotDefinition("title", required=True, prompt="标题？")
        slot2 = SlotDefinition("time", required=True, prompt="时间？")
        state = DialogState(session_id="sess-1", missing_slots=[slot1, slot2])

        next_slot = state.next_missing_slot()
        assert next_slot == slot1
        assert len(state.missing_slots) == 1

    def test_next_missing_slot_when_empty(self):
        state = DialogState(session_id="sess-1")
        assert state.next_missing_slot() is None

    def test_get_remaining_required(self):
        state = DialogState(
            session_id="sess-1",
            missing_slots=[
                SlotDefinition("title", required=True, prompt="标题？"),
                SlotDefinition("location", required=False, prompt="地点？"),
            ],
        )
        remaining = state.get_remaining_required()
        assert "title" in remaining
        assert "location" not in remaining

    def test_max_turns_default(self):
        state = DialogState(session_id="sess-1")
        assert state.max_turns == 3


class TestSlotFiller:
    """Test slot filling functionality."""

    def test_process_turn_without_llm(self):
        filler = SlotFiller()
        state = DialogState(
            session_id="sess-1",
            missing_slots=[SlotDefinition("title", required=True, prompt="标题？")],
        )
        # Run async function synchronously
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(filler.process_turn("你好", state))
        finally:
            loop.close()
        assert result.turn_count == 1
        # Without LLM extractor, slots shouldn't be auto-filled
        assert len(result.missing_slots) == 1

    def test_get_clarification_question(self):
        filler = SlotFiller()
        state = DialogState(
            session_id="sess-1",
            missing_slots=[SlotDefinition("title", required=True, prompt="标题是什么？")],
        )
        question = filler.get_clarification_question(state)
        assert question == "标题是什么？"

    def test_get_clarification_when_complete(self):
        filler = SlotFiller()
        state = DialogState(session_id="sess-1")
        assert filler.get_clarification_question(state) is None

    def test_max_turns_reached(self):
        filler = SlotFiller()
        state = DialogState(session_id="sess-1", turn_count=3, max_turns=3)
        assert filler.is_max_turns_reached(state) is True

    def test_max_turns_not_reached(self):
        filler = SlotFiller()
        state = DialogState(session_id="sess-1", turn_count=2, max_turns=3)
        assert filler.is_max_turns_reached(state) is False


class TestDialogStateManager:
    """Test dialog state persistence and retrieval."""

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_get_or_create_new(self):
        manager = DialogStateManager()
        state = self._run_async(manager.get_or_create("new-session"))
        assert state.session_id == "new-session"

    def test_get_or_create_existing(self):
        manager = DialogStateManager()
        state1 = self._run_async(manager.get_or_create("sess-1"))
        state2 = self._run_async(manager.get_or_create("sess-1"))
        assert state1 is state2

    def test_save_and_retrieve(self):
        manager = DialogStateManager()
        state = DialogState(session_id="sess-1", intent="create_event")
        self._run_async(manager.save(state))
        retrieved = self._run_async(manager.get_or_create("sess-1"))
        assert retrieved.intent == "create_event"

    def test_clear(self):
        manager = DialogStateManager()
        self._run_async(manager.get_or_create("sess-1"))
        self._run_async(manager.clear("sess-1"))
        state = self._run_async(manager.get_or_create("sess-1"))
        # After clear, should create a fresh state
        assert state.intent is None

    def test_get_required_slots_create_event(self):
        manager = DialogStateManager()
        slots = manager.get_required_slots("create_event")
        assert len(slots) > 0
        assert slots[0].name == "title"

    def test_get_required_slots_create_task(self):
        manager = DialogStateManager()
        slots = manager.get_required_slots("create_task")
        assert len(slots) > 0
        assert slots[0].name == "content"

    def test_get_required_slots_unknown_intent(self):
        manager = DialogStateManager()
        slots = manager.get_required_slots("unknown_intent")
        assert slots == []


class TestPredefinedSlots:
    """Test predefined slot templates."""

    def test_create_event_slots_structure(self):
        assert len(CREATE_EVENT_SLOTS) >= 2
        names = [s.name for s in CREATE_EVENT_SLOTS]
        assert "title" in names
        assert "start_time" in names

    def test_create_task_slots_structure(self):
        assert len(CREATE_TASK_SLOTS) >= 1
        names = [s.name for s in CREATE_TASK_SLOTS]
        assert "content" in names
