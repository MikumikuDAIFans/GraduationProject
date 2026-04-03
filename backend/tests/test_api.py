from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.api.routes import assistant as assistant_routes
from app.api.router import api_router


class FakeAssistantService:
    def __init__(self) -> None:
        self.session_id = 1
        self.session_title = "New chat"
        self.messages = [
            {
                "id": 1,
                "session_id": 1,
                "role": "user",
                "content": "Hello",
                "tool_calls_json": None,
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": 2,
                "session_id": 1,
                "role": "assistant",
                "content": "Minimal assistant is online.",
                "tool_calls_json": None,
                "created_at": datetime.now(timezone.utc),
            },
        ]

    async def send_message(self, user_id: str, payload):
        return {
            "session_id": self.session_id,
            "reply": "Minimal assistant is online.",
            "actions": [],
        }

    async def get_session(self, user_id: str, session_id: int):
        return {
            "id": self.session_id,
            "user_id": user_id,
            "session_type": "chat",
            "title": self.session_title,
            "is_archived": False,
            "context_json": {"status": "test"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": list(self.messages),
        }

    async def create_session(self, user_id: str, payload):
        self.session_id += 1
        self.session_title = payload.title or f"New chat {self.session_id}"
        self.messages = []
        return {
            "id": self.session_id,
            "user_id": user_id,
            "session_type": "chat",
            "title": self.session_title,
            "is_archived": False,
            "context_json": {"status": "test"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": [],
        }

    async def list_sessions(self, user_id: str, limit: int = 20):
        del limit
        return {
            "items": [
                {
                    "id": self.session_id,
                    "user_id": user_id,
                    "session_type": "chat",
                    "title": self.session_title,
                    "is_archived": False,
                    "context_json": {"status": "test"},
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "messages": list(self.messages),
                }
            ],
            "total": 1,
        }

    async def archive_session(self, user_id: str, session_id: int):
        del user_id, session_id
        return {"success": True}

    async def clear_session_messages(self, user_id: str, session_id: int):
        del user_id, session_id
        self.messages = []
        return {"success": True}

    async def get_inbox(self, user_id: str):
        return {
            "items": [
                {
                    "id": "task-1",
                    "kind": "task_replan",
                    "title": "Task Replan Needed",
                    "description": "Write thesis chapter still has 60 minutes remaining.",
                    "priority": 3,
                    "thread_id": "task-1",
                    "read": False,
                    "archived": False,
                    "entry_count": None,
                    "updated_at": None,
                    "action_label": "Review Plan",
                    "action_message": "现在进展如何，接下来怎么安排",
                    "related_task_id": 1,
                    "related_event_id": None,
                    "meta": {},
                }
            ],
            "total": 1,
            "unread_total": 1,
        }

    async def get_current_session(self, user_id: str):
        return {
            "session": {
                "id": self.session_id,
                "user_id": user_id,
                "session_type": "chat",
                "title": self.session_title,
                "is_archived": False,
                "context_json": {"status": "test"},
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "messages": list(self.messages),
            },
            "inbox": {
                "items": [
                    {
                        "id": "task-1",
                        "kind": "task_replan",
                        "title": "Task Replan Needed",
                        "description": "Write thesis chapter still has 60 minutes remaining.",
                        "priority": 3,
                        "thread_id": "task-1",
                        "read": False,
                        "archived": False,
                        "entry_count": None,
                        "updated_at": None,
                        "action_label": "Review Plan",
                        "action_message": "现在进展如何，接下来怎么安排",
                        "related_task_id": 1,
                        "related_event_id": None,
                        "meta": {},
                    }
                ],
                "total": 1,
                "unread_total": 1,
            },
        }

    async def get_summary(self, user_id: str):
        return {
            "generated_at": datetime.now(timezone.utc),
            "unread_followups": 1,
            "cards": [
                {
                    "id": "followups",
                    "title": "Assistant Follow-ups",
                    "value": "1",
                    "description": "Unread proactive assistant threads waiting for review.",
                    "tone": "warning",
                    "action_label": "Open Inbox",
                    "action_message": "现在进展如何，接下来怎么安排",
                }
            ],
        }

    async def mark_inbox_item(self, user_id: str, item_id: str, action: str):
        archived = action == "archive"
        return {
            "items": [] if archived else [
                {
                    "id": item_id,
                    "kind": "task_replan",
                    "title": "Task Replan Needed",
                    "description": "Write thesis chapter still has 60 minutes remaining.",
                    "priority": 3,
                    "thread_id": "task-1",
                    "read": True,
                    "archived": False,
                    "entry_count": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "action_label": "Review Plan",
                    "action_message": "现在进展如何，接下来怎么安排",
                    "related_task_id": 1,
                    "related_event_id": None,
                    "meta": {},
                }
            ],
            "total": 0 if archived else 1,
            "unread_total": 0,
        }


class FakeEventService:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

    async def list_events(self, user_id: str, start=None, end=None):
        return list(self.items)

    async def create_event(self, user_id: str, payload):
        item = {
            "id": 1,
            "user_id": user_id,
            "title": payload.title,
            "description": payload.description,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "location_name": payload.location_name,
            "location_coords": payload.location_coords,
            "event_type": payload.event_type,
            "source": payload.source,
            "is_fixed": payload.is_fixed,
            "buffer_before": payload.buffer_before,
            "buffer_after": payload.buffer_after,
            "travel_mode": payload.travel_mode,
            "travel_duration_minutes": payload.travel_duration_minutes,
            "departure_time": payload.departure_time,
            "status": payload.status,
            "linked_task_id": payload.linked_task_id,
            "external_event_id": payload.external_event_id,
            "external_calendar_id": payload.external_calendar_id,
            "external_etag": payload.external_etag,
            "sync_status": payload.sync_status,
            "last_synced_at": payload.last_synced_at,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        self.items.append(item)
        return item

    async def get_event(self, user_id: str, event_id: int):
        return self.items[0]

    async def update_event(self, user_id: str, event_id: int, payload):
        item = dict(self.items[0])
        if payload.title is not None:
            item["title"] = payload.title
        item["updated_at"] = datetime.now(timezone.utc)
        self.items[0] = item
        return item

    async def delete_event(self, user_id: str, event_id: int):
        return None


class FakeTaskService:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = [
            {
                "id": 1,
                "user_id": "local-user",
                "content": "Draft thesis outline",
                "description": None,
                "estimated_duration_minutes": 60,
                "priority": 2,
                "deadline": None,
                "status": "open",
                "can_split": True,
                "preferred_period": None,
                "linked_event_id": None,
                "scheduled_minutes": 0,
                "scheduled_blocks_count": 0,
                "remaining_minutes": 60,
                "completion_ratio": 0.0,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ]

    async def list_tasks(self, user_id: str):
        return list(self.items)

    async def create_task(self, user_id: str, payload):
        return self.items[0]

    async def update_task(self, user_id: str, task_id: int, payload):
        item = dict(self.items[0])
        if payload.status is not None:
            item["status"] = payload.status
        if payload.priority is not None:
            item["priority"] = payload.priority
        item["updated_at"] = datetime.now(timezone.utc)
        self.items[0] = item
        return item

    async def delete_task(self, user_id: str, task_id: int):
        return None


class FakeReminderService:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = [
            {
                "id": 1,
                "user_id": "local-user",
                "target_type": "event",
                "target_id": 1,
                "remind_type": "event_start",
                "remind_at": datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc),
                "delivery_channel": "in_app",
                "message": "Event starts soon",
                "status": "pending",
                "sent_at": None,
                "created_at": datetime.now(timezone.utc),
            }
        ]

    async def list_reminders(self, user_id: str):
        return list(self.items)

    async def mark_read(self, user_id: str, reminder_id: int):
        item = dict(self.items[0])
        item["status"] = "read"
        self.items[0] = item
        return item


class FakeSuggestionService:
    async def get_today_suggestions(self, user_id: str):
        return {
            "items": [
                {
                    "type": "task_slot",
                    "title": "Suggested slot for Draft thesis outline",
                    "description": "Use this slot for the task.",
                    "start_time": datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
                    "end_time": datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
                    "related_task_id": 1,
                    "related_event_id": None,
                    "confidence": 0.8,
                }
            ],
            "total": 1,
        }

    async def get_next_suggestions(self, user_id: str):
        return {
            "items": [
                {
                    "type": "task_slot",
                    "title": "Suggested slot for Draft thesis outline",
                    "description": "Use this slot for the task.",
                    "start_time": datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
                    "end_time": datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc),
                    "related_task_id": 1,
                    "related_event_id": None,
                    "confidence": 0.76,
                }
            ],
            "total": 1,
        }


class FakeContextService:
    async def geocode(self, address: str, city: str | None = None):
        return {
            "formatted_address": address,
            "location": "116.397,39.908",
            "province": "Beijing",
            "city": "Beijing",
            "district": "Dongcheng",
        }

    async def estimate_travel(self, origin: str, destination: str, city: str | None = None, mode: str = "driving"):
        return {
            "origin": origin,
            "destination": destination,
            "origin_location": "116.397,39.908",
            "destination_location": "116.410,39.920",
            "mode": mode,
            "duration_seconds": 1200,
            "duration_minutes": 20.0,
            "distance_meters": 5600,
            "distance_km": 5.6,
        }

    async def weather_now(self, location: str):
        return {
            "location": location,
            "obs_time": "2026-03-26T10:00:00+08:00",
            "temp": "18",
            "feels_like": "18",
            "text": "Sunny",
            "wind_dir": "North",
            "wind_scale": "2",
            "humidity": "33",
            "precip": "0.0",
            "vis": "30",
        }


class FakeProfileService:
    def __init__(self) -> None:
        self.payload = {
            "id": 1,
            "username": "local-user",
            "display_name": "Local User",
            "timezone": "Asia/Shanghai",
            "home_location_name": "北京天安门",
            "home_location_coords": "116.397463,39.909187",
            "work_location_name": "北京大学",
            "work_location_coords": "116.310918,39.992873",
            "transport_preference": "driving",
            "wake_up_time": "07:30",
            "sleep_time": "23:30",
            "preferences_json": {"focus_block_minutes": 60},
            "google_calendar_status": "disconnected",
            "google_calendar_connected_at": None,
            "google_calendar_last_sync_at": None,
            "google_calendar_error": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    async def get_profile(self, user_id: str):
        return dict(self.payload)

    async def update_profile(self, user_id: str, payload):
        for key, value in payload.model_dump(exclude_none=True).items():
            self.payload[key] = value
        return dict(self.payload)


class FakeGoogleCalendarService:
    async def get_status(self, user_id: str):
        return {
            "enabled": True,
            "status": "disconnected",
            "connected": False,
            "calendar_id": "primary",
            "redirect_uri": "http://127.0.0.1:8888/auth/callback",
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
            "has_refresh_token": False,
            "auth_url": "https://example.com/google-auth",
        }

    async def start_auth(self, user_id: str):
        return {
            "auth_url": "https://example.com/google-auth",
            "state": "test-state",
        }

    async def complete_auth(self, user_id: str, *, code: str, state: str | None):
        return {
            "status": "connected",
            "connected": True,
            "calendar_id": "primary",
            "connected_at": datetime.now(timezone.utc),
        }

    async def sync(self, user_id: str, *, start=None, end=None):
        return {
            "status": "ok",
            "pushed": 1,
            "imported": 1,
            "updated": 0,
            "skipped": 0,
            "deleted": 0,
            "last_sync_at": datetime.now(timezone.utc),
            "details": [],
        }


def build_client() -> tuple[TestClient, FakeAssistantService, FakeEventService, FakeTaskService, FakeReminderService, FakeSuggestionService, FakeContextService, FakeProfileService, FakeGoogleCalendarService]:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    assistant_service = FakeAssistantService()
    event_service = FakeEventService()
    task_service = FakeTaskService()
    reminder_service = FakeReminderService()
    suggestion_service = FakeSuggestionService()
    context_service = FakeContextService()
    profile_service = FakeProfileService()
    google_calendar_service = FakeGoogleCalendarService()

    app.dependency_overrides[deps.get_assistant_service] = lambda: assistant_service
    app.dependency_overrides[deps.get_event_service] = lambda: event_service
    app.dependency_overrides[deps.get_task_service] = lambda: task_service
    app.dependency_overrides[deps.get_reminder_service] = lambda: reminder_service
    app.dependency_overrides[deps.get_suggestion_service] = lambda: suggestion_service
    app.dependency_overrides[deps.get_context_service] = lambda: context_service
    app.dependency_overrides[deps.get_profile_service] = lambda: profile_service
    app.dependency_overrides[deps.get_google_calendar_service] = lambda: google_calendar_service

    client = TestClient(app)
    return client, assistant_service, event_service, task_service, reminder_service, suggestion_service, context_service, profile_service, google_calendar_service


def test_health_endpoint() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    response = client.get("/api/health")
    ai_response = client.get("/api/health/ai")
    perf_response = client.get("/api/health/performance")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert ai_response.status_code == 200
    assert "enabled" in ai_response.json()
    assert perf_response.status_code == 200
    assert "avg_request_ms" in perf_response.json()


def test_events_create_and_list() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    created = client.post(
        "/api/events",
        json={
            "title": "Weekly review",
            "description": "Review progress",
            "is_fixed": False,
        },
    )
    listed = client.get("/api/events")

    assert created.status_code == 201
    assert created.json()["title"] == "Weekly review"
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_tasks_update_and_reminders_read() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    task_response = client.patch(
        "/api/tasks/1",
        json={"status": "done", "priority": 1},
    )
    reminder_response = client.post("/api/reminders/1/read")

    assert task_response.status_code == 200
    assert task_response.json()["status"] == "done"
    assert reminder_response.status_code == 200
    assert reminder_response.json()["status"] == "read"


def test_assistant_message_and_session() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    message_response = client.post("/api/assistant/message", json={"message": "Help me arrange tomorrow"})
    create_response = client.post("/api/assistant/sessions", json={"title": "Fresh chat"})
    list_response = client.get("/api/assistant/sessions")
    session_response = client.get("/api/assistant/sessions/1")
    clear_response = client.delete("/api/assistant/sessions/1/messages")
    archive_session_response = client.post("/api/assistant/sessions/1/archive")
    inbox_response = client.get("/api/assistant/inbox")
    current_response = client.get("/api/assistant/current")
    summary_response = client.get("/api/assistant/summary")
    read_response = client.post("/api/assistant/inbox/task-1", params={"action": "read"})
    archive_response = client.post("/api/assistant/inbox/task-1", params={"action": "archive"})

    assert message_response.status_code == 200
    assert message_response.json()["session_id"] == 1
    assert create_response.status_code == 200
    assert create_response.json()["title"] == "Fresh chat"
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert session_response.status_code == 200
    assert "title" in session_response.json()
    assert clear_response.status_code == 200
    assert clear_response.json()["success"] is True
    assert archive_session_response.status_code == 200
    assert archive_session_response.json()["success"] is True
    assert inbox_response.status_code == 200
    assert inbox_response.json()["total"] == 1
    assert inbox_response.json()["unread_total"] == 1
    assert current_response.status_code == 200
    assert current_response.json()["session"]["id"] >= 1
    assert summary_response.status_code == 200
    assert summary_response.json()["unread_followups"] == 1
    assert read_response.status_code == 200
    assert read_response.json()["items"][0]["read"] is True
    assert read_response.json()["unread_total"] == 0
    assert archive_response.status_code == 200
    assert archive_response.json()["total"] == 0


def test_assistant_voice_and_speak_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    async def fake_process_input(data: bytes) -> str:
        assert data == b"audio-bytes"
        return "voice transcript"

    async def fake_synthesize(text: str) -> bytes:
        assert text == "hello audio"
        return b"fake-mp3"

    monkeypatch.setattr(assistant_routes.whisper_adapter, "process_input", fake_process_input)
    monkeypatch.setattr(assistant_routes.tts_adapter, "synthesize", fake_synthesize)

    voice_response = client.post(
        "/api/assistant/voice",
        files={"audio": ("voice.wav", b"audio-bytes", "audio/wav")},
    )
    speak_response = client.post("/api/assistant/speak", json={"text": "hello audio"})

    assert voice_response.status_code == 200
    assert voice_response.json()["transcript"] == "voice transcript"
    assert speak_response.status_code == 200
    assert speak_response.content == b"fake-mp3"


def test_suggestions_endpoints() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    today_response = client.get("/api/suggestions/today")
    next_response = client.get("/api/suggestions/next")

    assert today_response.status_code == 200
    assert today_response.json()["total"] == 1
    assert next_response.status_code == 200
    assert next_response.json()["items"][0]["type"] == "task_slot"


def test_context_endpoints() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    geocode_response = client.get("/api/context/geocode", params={"address": "Tiananmen"})
    travel_response = client.get(
        "/api/context/travel",
        params={"origin": "Campus", "destination": "Library"},
    )
    weather_response = client.get(
        "/api/context/weather/now",
        params={"location": "116.397,39.908"},
    )

    assert geocode_response.status_code == 200
    assert geocode_response.json()["location"] == "116.397,39.908"
    assert travel_response.status_code == 200
    assert travel_response.json()["duration_minutes"] == 20.0
    assert weather_response.status_code == 200
    assert weather_response.json()["text"] == "Sunny"


def test_profile_endpoints() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    get_response = client.get("/api/profile")
    update_response = client.put(
        "/api/profile",
        json={
            "display_name": "Student User",
            "transport_preference": "walking",
        },
    )

    assert get_response.status_code == 200
    assert get_response.json()["username"] == "local-user"
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Student User"
    assert update_response.json()["transport_preference"] == "walking"


def test_google_calendar_endpoints() -> None:
    client, _, _, _, _, _, _, _, _ = build_client()

    status_response = client.get("/api/google-calendar/status")
    start_response = client.get("/api/google-calendar/auth/start")
    callback_response = client.get(
        "/api/google-calendar/auth/callback",
        params={"code": "mock-code", "state": "test-state"},
    )
    sync_response = client.post("/api/google-calendar/sync")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "disconnected"
    assert start_response.status_code == 200
    assert start_response.json()["state"] == "test-state"
    assert callback_response.status_code == 200
    assert callback_response.json()["connected"] is True
    assert sync_response.status_code == 200
    assert sync_response.json()["pushed"] == 1
