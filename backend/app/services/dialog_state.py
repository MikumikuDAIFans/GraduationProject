"""Dialog state tracker for multi-turn slot filling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class SlotDefinition:
    """Definition of a slot to be filled."""

    name: str
    required: bool
    prompt: str  # Question to ask when slot is missing
    extractor: Optional[Callable] = None  # Function to extract value from context


@dataclass
class DialogState:
    """Tracks the state of a multi-turn conversation."""

    intent: Optional[str] = None
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[SlotDefinition] = field(default_factory=list)
    turn_count: int = 0
    max_turns: int = 3  # Maximum follow-up turns before giving up
    session_id: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if all required slots are filled."""
        return len(self.missing_slots) == 0

    def next_missing_slot(self) -> Optional[SlotDefinition]:
        """Get the next missing slot to ask about."""
        if self.missing_slots:
            return self.missing_slots.pop(0)
        return None

    def get_remaining_required(self) -> list[str]:
        """Get list of remaining required slot names."""
        return [s.name for s in self.missing_slots if s.required]


# Slot definition templates for common intents
CREATE_EVENT_SLOTS = [
    SlotDefinition("title", required=True, prompt="请问事件的标题是什么？"),
    SlotDefinition("start_time", required=True, prompt="请问什么时候开始？"),
    SlotDefinition("end_time", required=False, prompt="请问什么时候结束？"),
    SlotDefinition("location", required=False, prompt="在哪里进行？"),
]

CREATE_TASK_SLOTS = [
    SlotDefinition("content", required=True, prompt="请问任务的内容是什么？"),
    SlotDefinition("deadline", required=False, prompt="有截止时间吗？"),
    SlotDefinition("priority", required=False, prompt="优先级如何（1-5）？"),
]


class SlotFiller:
    """Manages slot filling for multi-turn conversations."""

    async def process_turn(
        self,
        user_input: str,
        state: DialogState,
        llm_extractor: Optional[Callable] = None,
    ) -> DialogState:
        """Process one turn of conversation, attempting to fill missing slots.

        Args:
            user_input: User's message
            state: Current dialog state
            llm_extractor: Optional async function to extract slot values via LLM

        Returns:
            Updated dialog state
        """
        # If we have an LLM extractor, use it to extract slot values
        if llm_extractor and state.missing_slots:
            missing_names = [s.name for s in state.missing_slots]
            try:
                extracted = await llm_extractor(user_input, missing_names)
                state.slots.update(extracted)
                state.missing_slots = [
                    s for s in state.missing_slots if s.name not in extracted
                ]
            except Exception:
                # If extraction fails, continue with manual slot asking
                pass

        state.turn_count += 1
        return state

    def get_clarification_question(self, state: DialogState) -> Optional[str]:
        """Generate a clarification question for the next missing slot."""
        next_slot = state.next_missing_slot()
        if next_slot:
            return next_slot.prompt
        return None

    def is_max_turns_reached(self, state: DialogState) -> bool:
        """Check if we've exceeded the maximum number of turns."""
        return state.turn_count >= state.max_turns


class DialogStateManager:
    """Manages dialog state persistence and retrieval."""

    def __init__(self):
        self._states: dict[str, DialogState] = {}

    async def get_or_create(self, session_id: str) -> DialogState:
        """Get existing dialog state or create a new one."""
        if session_id in self._states:
            return self._states[session_id]
        state = DialogState(session_id=session_id)
        self._states[session_id] = state
        return state

    async def save(self, state: DialogState) -> None:
        """Save dialog state."""
        if state.session_id:
            self._states[state.session_id] = state

    async def clear(self, session_id: str) -> None:
        """Clear dialog state for a session."""
        self._states.pop(session_id, None)

    def get_required_slots(self, intent: str) -> list[SlotDefinition]:
        """Get the required slots for a given intent."""
        slot_map = {
            "create_event": CREATE_EVENT_SLOTS.copy(),
            "create_task": CREATE_TASK_SLOTS.copy(),
        }
        return slot_map.get(intent, [])
