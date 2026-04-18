"""Pydantic schemas for assistant action validation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class CreateEventAction(BaseModel):
    """Action to create a new event."""

    type: Literal["create_event"]
    payload: dict = Field(..., description="Event creation parameters")

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict) -> dict:
        required = ["title", "start_time"]
        for field_name in required:
            if field_name not in v:
                raise ValueError(f"Missing required field: {field_name}")
        return v


class CreateTaskAction(BaseModel):
    """Action to create a new task."""

    type: Literal["create_task"]
    payload: dict = Field(..., description="Task creation parameters")

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict) -> dict:
        if "content" not in v:
            raise ValueError("Missing required field: content")
        return v


class QueryEventsAction(BaseModel):
    """Action to query existing events."""

    type: Literal["query_events"]
    payload: dict = Field(default_factory=lambda: {"range": "today"})


class ClarifyAction(BaseModel):
    """Action to request clarification from user."""

    type: Literal["clarify"]
    missing_fields: list[str] = Field(..., description="Fields that need clarification")
    question: str = Field(..., description="Question to ask the user")


class UpdateEventAction(BaseModel):
    """Action to update an existing event."""

    type: Literal["update_event"]
    payload: dict = Field(..., description="Event update parameters")

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict) -> dict:
        if "event_id" not in v:
            raise ValueError("Missing required field: event_id")
        return v


class DeleteEventAction(BaseModel):
    """Action to delete an event."""

    type: Literal["delete_event"]
    payload: dict = Field(..., description="Event deletion parameters")

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict) -> dict:
        if "event_id" not in v:
            raise ValueError("Missing required field: event_id")
        return v


# Union type for all possible actions
AssistantAction = Union[
    CreateEventAction,
    CreateTaskAction,
    QueryEventsAction,
    ClarifyAction,
    UpdateEventAction,
    DeleteEventAction,
]


class AssistantResponse(BaseModel):
    """Validated response from the assistant LLM."""

    reply: str = Field(..., description="Natural language reply to the user")
    actions: list[AssistantAction] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    waiting_for_input: bool = Field(False, description="Whether the system is waiting for user input")

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: list[AssistantAction]) -> list[AssistantAction]:
        """Ensure actions are mutually exclusive where needed."""
        has_clarify = any(isinstance(a, ClarifyAction) for a in v)
        has_execution = any(isinstance(a, (CreateEventAction, CreateTaskAction, UpdateEventAction, DeleteEventAction)) for a in v)

        if has_clarify and has_execution:
            raise ValueError("Cannot have both clarify and execution actions")

        return v
