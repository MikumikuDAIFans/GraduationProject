from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantProposalCreate
from app.db.base import Base
from app.repositories.assistant_proposals import AssistantProposalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager


async def _make_manager(tmp_path: Path) -> tuple[AssistantProposalManager, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_proposal_revise.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repository = AssistantProposalRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AssistantProposalManager(repository, execute_on_confirm=False), engine


def test_revise_creates_child_and_supersedes_original(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="task_schedule_plan",
                    summary="安排复习",
                    dedup_key="task:review-plan",
                    payload_json={"options": [{"option_id": "A", "title": "今晚复习"}]},
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到明天上午",
            )
            old = await manager.get_proposal(user_id="local-user", proposal_id=original.id)

            assert old.status == "superseded"
            assert revised.status == "pending"
            assert revised.supersedes_proposal_id == original.id
            assert revised.payload_json["revision_request"] == "改到明天上午"
            assert revised.payload_json["superseded_proposal_id"] == original.id
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_event_creation_rewrites_action_time(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="建议创建日程“论文组会”：05-07 15:00-16:30",
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "title": "按建议创建日程",
                                "summary": "建议创建日程“论文组会”：05-07 15:00-16:30",
                                "actions": [
                                    {
                                        "type": "create_event",
                                        "payload": {
                                            "title": "论文组会",
                                            "start_time": "2026-05-07T15:00:00",
                                            "end_time": "2026-05-07T16:30:00",
                                            "location_name": "学校",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到5月8日下午4点",
            )

            action = revised.payload_json["options"][0]["actions"][0]
            assert revised.payload_json["revision"]["type"] == "event_payload_update"
            assert action["payload"]["start_time"] == "2026-05-08T16:00:00"
            assert action["payload"]["end_time"] == "2026-05-08T17:30:00"
            assert "05-08 16:00-17:30" in revised.summary
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_event_creation_rewrites_title_and_location(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="建议创建日程“论文组会”：05-07 15:00-16:30",
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "title": "按建议创建日程",
                                "summary": "建议创建日程“论文组会”：05-07 15:00-16:30",
                                "actions": [
                                    {
                                        "type": "create_event",
                                        "payload": {
                                            "title": "论文组会",
                                            "start_time": "2026-05-07T15:00:00",
                                            "end_time": "2026-05-07T16:30:00",
                                            "location_name": "学校",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="标题改成毕业论文讨论，地点改到图书馆三楼",
            )

            payload = revised.payload_json["options"][0]["actions"][0]["payload"]
            assert revised.payload_json["revision"]["title"] == "毕业论文讨论"
            assert revised.payload_json["revision"]["location_name"] == "图书馆三楼"
            assert payload["title"] == "毕业论文讨论"
            assert payload["location_name"] == "图书馆三楼"
            assert "标题“毕业论文讨论”" in revised.summary
            assert "地点 图书馆三楼" in revised.summary
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_event_creation_does_not_mistake_quoted_location_for_title(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="建议创建日程“论文组会”：05-07 15:00-16:30",
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "title": "按建议创建日程",
                                "summary": "建议创建日程“论文组会”：05-07 15:00-16:30",
                                "actions": [
                                    {
                                        "type": "create_event",
                                        "payload": {
                                            "title": "论文组会",
                                            "start_time": "2026-05-07T15:00:00",
                                            "end_time": "2026-05-07T16:30:00",
                                            "location_name": "学校",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="地点改到“图书馆三楼”",
            )

            payload = revised.payload_json["options"][0]["actions"][0]["payload"]
            assert "title" not in revised.payload_json["revision"]
            assert revised.payload_json["revision"]["location_name"] == "图书馆三楼"
            assert payload["title"] == "论文组会"
            assert payload["location_name"] == "图书馆三楼"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_event_reschedule_rewrites_update_location_without_mistaking_time_for_location(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_reschedule",
                    summary="建议把日程“论文组会”改到 05-07 15:00-16:30",
                    related_event_id=12,
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "title": "按建议重排日程",
                                "summary": "建议把日程“论文组会”改到 05-07 15:00-16:30",
                                "actions": [
                                    {
                                        "type": "reschedule_event",
                                        "payload": {
                                            "event_id": 12,
                                            "update": {
                                                "start_time": "2026-05-07T15:00:00",
                                                "end_time": "2026-05-07T16:30:00",
                                            },
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到下午4点，地点改到图书馆",
            )

            update = revised.payload_json["options"][0]["actions"][0]["payload"]["update"]
            assert update["start_time"] == "2026-05-07T16:00:00"
            assert update["end_time"] == "2026-05-07T17:30:00"
            assert update["location_name"] == "图书馆"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_event_reschedule_rewrites_update_time(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            original = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_reschedule",
                    summary="建议把日程“论文组会”改到 05-07 15:00-16:30",
                    related_event_id=12,
                    payload_json={
                        "options": [
                            {
                                "option_id": "A",
                                "title": "按建议重排日程",
                                "summary": "建议把日程“论文组会”改到 05-07 15:00-16:30",
                                "actions": [
                                    {
                                        "type": "reschedule_event",
                                        "payload": {
                                            "event_id": 12,
                                            "update": {
                                                "start_time": "2026-05-07T15:00:00",
                                                "end_time": "2026-05-07T16:30:00",
                                            },
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )

            revised = await manager.revise_proposal(
                user_id="local-user",
                proposal_id=original.id,
                message="改到下午4点",
            )

            action = revised.payload_json["options"][0]["actions"][0]
            update = action["payload"]["update"]
            assert update["start_time"] == "2026-05-07T16:00:00"
            assert update["end_time"] == "2026-05-07T17:30:00"
            assert revised.related_event_id == 12
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_revise_expired_proposal_is_rejected(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager, engine = await _make_manager(tmp_path)
        try:
            proposal = await manager.create_proposal(
                user_id="local-user",
                payload=AssistantProposalCreate(
                    proposal_type="event_creation",
                    summary="过期安排",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    payload_json={"options": [{"option_id": "A", "title": "15:00"}]},
                ),
            )

            with pytest.raises(HTTPException) as exc_info:
                await manager.revise_proposal(user_id="local-user", proposal_id=proposal.id, message="改一下")

            assert exc_info.value.status_code == 409
            assert (await manager.get_proposal(user_id="local-user", proposal_id=proposal.id)).status == "expired"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
