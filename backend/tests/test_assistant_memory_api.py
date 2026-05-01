from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import assistant_memory


def _candidate(**overrides):
    data = {
        "id": 1,
        "user_id": "local-user",
        "memory_type": "preferences",
        "source_specialist": "memory",
        "status": "proposed",
        "confidence": 0.8,
        "proposed_change_json": {"operation": "append_entry", "content": "偏好上午深度工作"},
        "reason": "explicit request",
        "dedup_key": "memory:preferences:test",
        "confirmed_at": None,
        "rejected_at": None,
        "written_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeMemoryService:
    def __init__(self) -> None:
        self.item = _candidate()

    async def read_memory(self, *, user_id: str):
        del user_id
        return {
            "user_id": "local-user",
            "root": "/tmp/memory/local-user",
            "files": [
                {
                    "memory_type": "preferences",
                    "path": "/tmp/memory/local-user/preferences.md",
                    "exists": False,
                    "line_count": 0,
                    "updated_at": None,
                    "preview": [],
                }
            ],
        }

    async def list_candidates(self, *, user_id: str, statuses=None, memory_type=None, limit: int = 50):
        del user_id, statuses, memory_type, limit
        return [self.item]

    async def create_candidate(self, *, user_id: str, payload):
        del user_id
        self.item = _candidate(memory_type=payload.memory_type, proposed_change_json=payload.proposed_change_json)
        return self.item

    async def get_candidate(self, *, user_id: str, candidate_id: int):
        del user_id, candidate_id
        return self.item

    async def confirm_candidate(self, *, user_id: str, candidate_id: int):
        del user_id, candidate_id
        self.item = _candidate(status="written", written_at=datetime.now(timezone.utc))
        return self.item

    async def reject_candidate(self, *, user_id: str, candidate_id: int):
        del user_id, candidate_id
        self.item = _candidate(status="rejected", rejected_at=datetime.now(timezone.utc))
        return self.item


def _client(fake: FakeMemoryService) -> TestClient:
    app = FastAPI()
    app.include_router(assistant_memory.router)
    app.dependency_overrides[assistant_memory.get_memory_service] = lambda: fake
    return TestClient(app)


def test_memory_api_lists_creates_and_confirms_candidates() -> None:
    fake = FakeMemoryService()
    client = _client(fake)

    memory = client.get("/assistant/memory")
    assert memory.status_code == 200
    assert memory.json()["files"][0]["memory_type"] == "preferences"

    created = client.post(
        "/assistant/memory/candidates",
        json={
            "memory_type": "places",
            "proposed_change_json": {"operation": "append_entry", "content": "学校 = 北京大学东门"},
        },
    )
    assert created.status_code == 200
    assert created.json()["memory_type"] == "places"

    listed = client.get("/assistant/memory/candidates")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    confirmed = client.post("/assistant/memory/candidates/1/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "written"


def test_memory_api_rejects_candidate() -> None:
    fake = FakeMemoryService()
    client = _client(fake)

    rejected = client.post("/assistant/memory/candidates/1/reject")

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
