"""Pydantic schemas for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ReadModel(APIBaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class HealthRead(ReadModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    database_path: str
    database_ready: bool


class OperationResult(ReadModel):
    status: str = "ok"
    message: str
    id: int | None = None


class EventBase(APIBaseModel):
    title: str
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location_name: str | None = None
    location_address: str | None = None
    location_coords: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    event_type: str | None = None
    source: str | None = None
    is_fixed: bool = False
    buffer_before: int | None = None
    buffer_after: int | None = None
    travel_mode: str | None = None
    travel_duration_minutes: int | None = None
    departure_time: datetime | None = None
    status: str | None = None
    linked_task_id: int | None = None
    external_event_id: str | None = None
    external_calendar_id: str | None = None
    external_etag: str | None = None
    sync_status: str | None = None
    last_synced_at: datetime | None = None


class EventCreate(EventBase):
    title: str


class EventUpdate(APIBaseModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location_name: str | None = None
    location_address: str | None = None
    location_coords: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    event_type: str | None = None
    source: str | None = None
    is_fixed: bool | None = None
    buffer_before: int | None = None
    buffer_after: int | None = None
    travel_mode: str | None = None
    travel_duration_minutes: int | None = None
    departure_time: datetime | None = None
    status: str | None = None
    linked_task_id: int | None = None
    external_event_id: str | None = None
    external_calendar_id: str | None = None
    external_etag: str | None = None
    sync_status: str | None = None
    last_synced_at: datetime | None = None


class EventRead(EventBase, ReadModel):
    id: int
    user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TaskBase(APIBaseModel):
    content: str
    description: str | None = None
    estimated_duration_minutes: int | None = None
    priority: int | None = None
    deadline: datetime | None = None
    status: str | None = None
    can_split: bool | None = None
    preferred_period: str | None = None
    linked_event_id: int | None = None


class TaskCreate(TaskBase):
    content: str


class TaskUpdate(APIBaseModel):
    content: str | None = None
    description: str | None = None
    estimated_duration_minutes: int | None = None
    priority: int | None = None
    deadline: datetime | None = None
    status: str | None = None
    can_split: bool | None = None
    preferred_period: str | None = None
    linked_event_id: int | None = None


class TaskRead(TaskBase, ReadModel):
    id: int
    user_id: str
    scheduled_minutes: int = 0
    scheduled_blocks_count: int = 0
    remaining_minutes: int | None = None
    completion_ratio: float | None = None
    completed_minutes: int = 0
    completed_blocks_count: int = 0
    execution_ratio: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReminderBase(APIBaseModel):
    target_type: str
    target_id: int
    remind_type: str
    remind_at: datetime
    delivery_channel: str | None = None
    message: str | None = None
    status: str | None = None
    sent_at: datetime | None = None


class ReminderRead(ReminderBase, ReadModel):
    id: int
    user_id: str
    created_at: datetime | None = None


class ReminderList(ReadModel):
    items: list[ReminderRead] = Field(default_factory=list)
    total: int = 0


class AssistantMessageCreate(APIBaseModel):
    session_id: int | None = None
    message: str


class AssistantAction(ReadModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AssistantResponse(ReadModel):
    session_id: int
    reply: str
    actions: list[AssistantAction] = Field(default_factory=list)


class VoiceAssistantResponse(AssistantResponse):
    transcript: str


class SpeechSynthesisRequest(APIBaseModel):
    text: str


class AssistantInboxItem(ReadModel):
    id: str
    kind: str
    title: str
    description: str
    priority: int = 1
    thread_id: str | None = None
    read: bool = False
    archived: bool = False
    entry_count: int | None = None
    updated_at: datetime | None = None
    action_label: str | None = None
    action_message: str | None = None
    related_task_id: int | None = None
    related_event_id: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AssistantInboxRead(ReadModel):
    items: list[AssistantInboxItem] = Field(default_factory=list)
    total: int = 0
    unread_total: int = 0


class AssistantMessageRead(ReadModel):
    id: int
    session_id: int
    role: str
    content: str
    tool_calls_json: list[dict[str, Any]] | None = None
    created_at: datetime


class AssistantSessionRead(ReadModel):
    id: int
    user_id: str
    session_type: str | None = None
    context_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[AssistantMessageRead] = Field(default_factory=list)


class AssistantCurrentSessionRead(ReadModel):
    session: AssistantSessionRead
    inbox: AssistantInboxRead


class AssistantSummaryCard(ReadModel):
    id: str
    title: str
    value: str
    description: str
    tone: str = "neutral"
    action_label: str | None = None
    action_message: str | None = None
    thread_id: str | None = None
    related_task_id: int | None = None
    related_event_id: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AssistantSummaryRead(ReadModel):
    generated_at: datetime
    unread_followups: int = 0
    cards: list[AssistantSummaryCard] = Field(default_factory=list)


class SuggestionRead(ReadModel):
    type: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    related_task_id: int | None = None
    related_event_id: int | None = None
    confidence: float | None = None
    split_group: str | None = None
    segment_index: int | None = None
    segment_total: int | None = None
    estimated_minutes: int | None = None


class SuggestionList(ReadModel):
    items: list[SuggestionRead] = Field(default_factory=list)
    total: int = 0


class GeocodeRead(ReadModel):
    formatted_address: str
    location: str
    province: str | None = None
    city: str | list[str] | None = None
    district: str | None = None


class TravelEstimateRead(ReadModel):
    origin: str
    destination: str
    origin_location: str
    destination_location: str
    mode: str
    duration_seconds: int
    duration_minutes: float
    distance_meters: int
    distance_km: float


class WeatherNowRead(ReadModel):
    location: str
    obs_time: str | None = None
    temp: str | None = None
    feels_like: str | None = None
    text: str | None = None
    wind_dir: str | None = None
    wind_scale: str | None = None
    humidity: str | None = None
    precip: str | None = None
    vis: str | None = None


class UserProfileRead(ReadModel):
    id: int
    username: str
    display_name: str | None = None
    timezone: str
    home_location_name: str | None = None
    home_location_coords: str | None = None
    work_location_name: str | None = None
    work_location_coords: str | None = None
    transport_preference: str | None = None
    wake_up_time: str | None = None
    sleep_time: str | None = None
    preferences_json: dict[str, Any] | None = None
    google_calendar_status: str = "disconnected"
    google_calendar_connected_at: datetime | None = None
    google_calendar_last_sync_at: datetime | None = None
    google_calendar_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserProfileUpdate(APIBaseModel):
    display_name: str | None = None
    timezone: str | None = None
    home_location_name: str | None = None
    home_location_coords: str | None = None
    work_location_name: str | None = None
    work_location_coords: str | None = None
    transport_preference: str | None = None
    wake_up_time: str | None = None
    sleep_time: str | None = None
    preferences_json: dict[str, Any] | None = None


class GoogleCalendarStatusRead(ReadModel):
    enabled: bool
    status: str
    connected: bool
    calendar_id: str
    redirect_uri: str | None = None
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    has_refresh_token: bool = False
    auth_url: str | None = None


class GoogleCalendarAuthStartRead(ReadModel):
    auth_url: str
    state: str


class GoogleCalendarAuthCallbackRead(ReadModel):
    status: str
    connected: bool
    calendar_id: str
    connected_at: datetime | None = None


class GoogleCalendarSyncRead(ReadModel):
    status: str
    pushed: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    last_sync_at: datetime | None = None
    details: list[str] = Field(default_factory=list)
