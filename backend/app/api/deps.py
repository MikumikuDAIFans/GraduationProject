"""Dependency injection helpers for the API layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from fastapi import Header

from app.api.schemas import (
    AssistantCurrentSessionRead,
    AssistantInboxRead,
    AssistantSummaryRead,
    AssistantMessageCreate,
    AssistantResponse,
    AssistantSessionRead,
    EventCreate,
    EventRead,
    EventUpdate,
    GeocodeRead,
    GoogleCalendarAuthCallbackRead,
    GoogleCalendarAuthStartRead,
    GoogleCalendarStatusRead,
    GoogleCalendarSyncRead,
    ReminderRead,
    SuggestionList,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    TravelEstimateRead,
    UserProfileRead,
    UserProfileUpdate,
    WeatherNowRead,
)
from app.services.context import ContextService as DefaultContextService
from app.services.assistant import AssistantService as DefaultAssistantService
from app.services.events import EventService as DefaultEventService
from app.services.google_calendar import GoogleCalendarService as DefaultGoogleCalendarService
from app.services.profiles import UserProfileService as DefaultUserProfileService
from app.services.reminders import ReminderService as DefaultReminderService
from app.services.suggestions import SuggestionService as DefaultSuggestionService
from app.services.tasks import TaskService as DefaultTaskService


def get_current_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    """Return the active user identifier.

    This is a placeholder for the future auth layer. For now we allow an
    override header and fall back to a stable local-user value.
    """

    return x_user_id or "local-user"


class AssistantService(Protocol):
    async def send_message(self, user_id: str, payload: AssistantMessageCreate) -> AssistantResponse | dict[str, Any]: ...
    async def get_session(self, user_id: str, session_id: int) -> AssistantSessionRead | dict[str, Any] | None: ...
    async def get_inbox(self, user_id: str) -> AssistantInboxRead | dict[str, Any]: ...
    async def get_current_session(self, user_id: str) -> AssistantCurrentSessionRead | dict[str, Any]: ...
    async def mark_inbox_item(self, user_id: str, item_id: str, action: str) -> AssistantInboxRead | dict[str, Any]: ...
    async def get_summary(self, user_id: str) -> AssistantSummaryRead | dict[str, Any]: ...


class EventService(Protocol):
    async def list_events(self, user_id: str, start: datetime | None = None, end: datetime | None = None) -> list[EventRead | dict[str, Any]]: ...
    async def create_event(self, user_id: str, payload: EventCreate) -> EventRead | dict[str, Any]: ...
    async def get_event(self, user_id: str, event_id: int) -> EventRead | dict[str, Any] | None: ...
    async def update_event(self, user_id: str, event_id: int, payload: EventUpdate) -> EventRead | dict[str, Any] | None: ...
    async def delete_event(self, user_id: str, event_id: int) -> None: ...


class GoogleCalendarService(Protocol):
    async def get_status(self, user_id: str) -> GoogleCalendarStatusRead | dict[str, Any]: ...
    async def start_auth(self, user_id: str) -> GoogleCalendarAuthStartRead | dict[str, Any]: ...
    async def complete_auth(self, user_id: str, *, code: str, state: str | None) -> GoogleCalendarAuthCallbackRead | dict[str, Any]: ...
    async def sync(self, user_id: str, *, start: datetime | None = None, end: datetime | None = None) -> GoogleCalendarSyncRead | dict[str, Any]: ...


class TaskService(Protocol):
    async def list_tasks(self, user_id: str) -> list[TaskRead | dict[str, Any]]: ...
    async def create_task(self, user_id: str, payload: TaskCreate) -> TaskRead | dict[str, Any]: ...
    async def update_task(self, user_id: str, task_id: int, payload: TaskUpdate) -> TaskRead | dict[str, Any] | None: ...
    async def delete_task(self, user_id: str, task_id: int) -> None: ...


class ReminderService(Protocol):
    async def list_reminders(self, user_id: str) -> list[ReminderRead | dict[str, Any]]: ...
    async def mark_read(self, user_id: str, reminder_id: int) -> ReminderRead | dict[str, Any] | None: ...


class SuggestionService(Protocol):
    async def get_today_suggestions(self, user_id: str) -> SuggestionList | dict[str, Any]: ...
    async def get_next_suggestions(self, user_id: str) -> SuggestionList | dict[str, Any]: ...


class ContextService(Protocol):
    async def geocode(self, address: str, city: str | None = None) -> GeocodeRead | dict[str, Any]: ...
    async def estimate_travel(self, origin: str, destination: str, city: str | None = None, mode: str = "driving") -> TravelEstimateRead | dict[str, Any]: ...
    async def weather_now(self, location: str) -> WeatherNowRead | dict[str, Any]: ...


class UserProfileService(Protocol):
    async def get_profile(self, user_id: str) -> UserProfileRead | dict[str, Any]: ...
    async def update_profile(self, user_id: str, payload: UserProfileUpdate) -> UserProfileRead | dict[str, Any]: ...


def get_event_service() -> EventService:
    return DefaultEventService()


def get_assistant_service() -> AssistantService:
    return DefaultAssistantService()


def get_google_calendar_service() -> GoogleCalendarService:
    return DefaultGoogleCalendarService()


def get_task_service() -> TaskService:
    return DefaultTaskService()


def get_reminder_service() -> ReminderService:
    return DefaultReminderService()


def get_suggestion_service() -> SuggestionService:
    return DefaultSuggestionService()


def get_context_service() -> ContextService:
    return DefaultContextService()


def get_profile_service() -> UserProfileService:
    return DefaultUserProfileService()
