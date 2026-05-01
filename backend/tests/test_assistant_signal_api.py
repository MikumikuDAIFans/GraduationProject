from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import assistant_signals


def _signal(**overrides):
    data = {
        "id": 1,
        "user_id": "local-user",
        "signal_type": "daily_morning_review",
        "severity": "info",
        "status": "new",
        "dedup_key": "daily_morning_review:local-user:2026-05-01",
        "target_type": None,
        "target_id": None,
        "context_json": {"source": "debug_heartbeat"},
        "source_job": "debug_heartbeat",
        "cooldown_until": datetime.now(timezone.utc),
        "evaluated_at": None,
        "proposal_created_at": None,
        "dismissed_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeSignalManager:
    def __init__(self) -> None:
        self.item = _signal()

    async def list_signals(self, *, user_id: str, statuses=None, signal_type=None, limit: int = 50):
        del user_id, statuses, signal_type, limit
        return [self.item]

    async def get_signal(self, *, user_id: str, signal_id: int):
        del user_id, signal_id
        return self.item

    async def dismiss_signal(self, *, user_id: str, signal_id: int):
        del user_id, signal_id
        self.item = _signal(status="dismissed", dismissed_at=datetime.now(timezone.utc))
        return self.item

    async def create_signal(self, *, user_id: str, payload):
        del user_id
        self.item = _signal(signal_type=payload.signal_type, dedup_key=payload.dedup_key)
        return self.item


def _client(fake: FakeSignalManager) -> TestClient:
    app = FastAPI()
    app.include_router(assistant_signals.router)
    app.dependency_overrides[assistant_signals.get_signal_manager] = lambda: fake
    return TestClient(app)


def test_list_and_dismiss_signals_api() -> None:
    fake = FakeSignalManager()
    client = _client(fake)

    listed = client.get("/assistant/signals")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["signal_type"] == "daily_morning_review"

    dismissed = client.post("/assistant/signals/1/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"


def test_heartbeat_debug_creates_signal_only() -> None:
    fake = FakeSignalManager()
    client = _client(fake)

    response = client.post(
        "/assistant/heartbeat/run",
        json={"signal_type": "deadline_risk", "dedup_key": "deadline_risk:task:1:2026-05-01"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created_or_reused_signal"]["signal_type"] == "deadline_risk"
    assert "signal only" in body["message"]
