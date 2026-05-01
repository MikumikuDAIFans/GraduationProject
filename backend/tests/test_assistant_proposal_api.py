from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import assistant_proposals


def _proposal(**overrides):
    data = {
        "id": 1,
        "user_id": "local-user",
        "session_id": None,
        "thread_state_id": None,
        "proposal_type": "event_creation",
        "trigger_type": "user_message",
        "status": "pending",
        "dedup_key": None,
        "priority": 1,
        "summary": "明天下午 3 点去学校和同学见面",
        "payload_json": {"options": [{"option_id": "A", "title": "15:00-16:00"}]},
        "recommended_option_id": "A",
        "selected_option_id": None,
        "is_time_sensitive": False,
        "related_task_id": None,
        "related_event_id": None,
        "source_signal_id": None,
        "supersedes_proposal_id": None,
        "expires_at": None,
        "followup_after": None,
        "confirmed_at": None,
        "execution_started_at": None,
        "execution_error": None,
        "executed_at": None,
        "archived_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeProposalManager:
    def __init__(self) -> None:
        self.item = _proposal()
        self.confirmed_with: str | None = None

    async def list_proposals(self, *, user_id: str, statuses=None, proposal_type=None, limit: int = 50):
        del user_id, statuses, proposal_type, limit
        return [self.item]

    async def get_proposal(self, *, user_id: str, proposal_id: int):
        del user_id, proposal_id
        return self.item

    async def confirm_proposal(self, *, user_id: str, proposal_id: int, option_id: str):
        del user_id, proposal_id
        self.confirmed_with = option_id
        self.item = _proposal(status="executed", selected_option_id=option_id, executed_at=datetime.now(timezone.utc))
        return self.item

    async def reject_proposal(self, *, user_id: str, proposal_id: int):
        del user_id, proposal_id
        self.item = _proposal(status="rejected")
        return self.item

    async def revise_proposal(self, *, user_id: str, proposal_id: int, message: str):
        del user_id, proposal_id
        self.item = _proposal(id=2, status="pending", summary=message, supersedes_proposal_id=1)
        return self.item

    async def retry_proposal(self, *, user_id: str, proposal_id: int):
        del user_id, proposal_id
        self.item = _proposal(status="execution_pending", selected_option_id="A")
        return self.item

    async def expire_proposal(self, *, user_id: str, proposal_id: int):
        del user_id, proposal_id
        self.item = _proposal(status="expired")
        return self.item


def _client(fake: FakeProposalManager) -> TestClient:
    app = FastAPI()
    app.include_router(assistant_proposals.router)
    app.dependency_overrides[assistant_proposals.get_proposal_manager] = lambda: fake
    return TestClient(app)


def test_list_and_confirm_proposals_api() -> None:
    fake = FakeProposalManager()
    client = _client(fake)

    listed = client.get("/assistant/proposals")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["summary"].startswith("明天")

    confirmed = client.post("/assistant/proposals/1/confirm", json={"option_id": "A"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "executed"
    assert confirmed.json()["selected_option_id"] == "A"
    assert fake.confirmed_with == "A"


def test_revise_retry_and_expire_proposals_api() -> None:
    fake = FakeProposalManager()
    client = _client(fake)

    revised = client.post("/assistant/proposals/1/revise", json={"message": "改到明天上午"})
    assert revised.status_code == 200
    assert revised.json()["id"] == 2
    assert revised.json()["supersedes_proposal_id"] == 1

    retrying = client.post("/assistant/proposals/2/retry")
    assert retrying.status_code == 200
    assert retrying.json()["status"] == "execution_pending"

    expired = client.post("/assistant/proposals/2/expire")
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
