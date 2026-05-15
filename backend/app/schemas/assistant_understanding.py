"""Schemas for LLM-powered assistant understanding."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MessageIntent = Literal[
    "create_event",
    "create_task",
    "reschedule_event",
    "cancel_event",
    "mark_event_completed",
    "mark_task_completed",
    "schedule_guidance",
    "progress_followup",
    "event_context_advice",
    "unknown",
]

MessageGoalType = Literal[
    "event",
    "task",
    "schedule_guidance",
    "progress_followup",
    "event_context_advice",
    "unknown",
]


class MessageUnderstandingPayload(BaseModel):
    """Validated top-level semantic understanding returned by an LLM."""

    model_config = ConfigDict(extra="ignore")

    intent: MessageIntent
    goal_type: MessageGoalType
    title: str | None = None
    location_name: str | None = None
    task_content: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str | None = None

    @field_validator("title", "location_name", "task_content", "reasoning_summary", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("expected string or null")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("missing_fields", "ambiguities", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("expected list")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("expected string list")
            text = item.strip()
            if text:
                cleaned.append(text)
        return cleaned


def validate_message_understanding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized dict or raise if the LLM payload is not schema-compliant."""

    return MessageUnderstandingPayload.model_validate(payload).model_dump()
