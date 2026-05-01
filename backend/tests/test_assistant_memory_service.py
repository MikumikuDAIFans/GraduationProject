from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import AssistantMemoryCandidateCreate
from app.db.base import Base
from app.repositories.assistant_memory_candidates import AssistantMemoryCandidateRepository
from app.services.assistant_memory import AssistantMemoryService


async def _make_service(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assistant_memory.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = AssistantMemoryCandidateRepository(session_factory)
    service = AssistantMemoryService(repository, root=tmp_path / "memory")
    return service, engine


def test_memory_candidate_confirm_writes_markdown(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, engine = await _make_service(tmp_path)
        try:
            candidate = await service.create_candidate(
                user_id="local-user",
                payload=AssistantMemoryCandidateCreate(
                    memory_type="places",
                    confidence=0.9,
                    proposed_change_json={
                        "operation": "append_entry",
                        "title": "学校",
                        "content": "学校 = 北京大学东门，坐标 116.310918,39.992873",
                    },
                    reason="用户明确要求记住学校位置",
                    dedup_key="memory:places:school",
                ),
            )

            assert candidate.status == "proposed"

            written = await service.confirm_candidate(user_id="local-user", candidate_id=candidate.id)
            memory = await service.read_memory(user_id="local-user")
            places_path = Path(memory.files[1].path)
            text = places_path.read_text(encoding="utf-8")

            assert written.status == "written"
            assert "学校 = 北京大学东门" in text
            assert "candidate_id:" in text
            assert memory.files[1].memory_type == "places"
            assert memory.files[1].exists is True
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_memory_candidate_dedup_reuses_active_candidate(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, engine = await _make_service(tmp_path)
        try:
            payload = AssistantMemoryCandidateCreate(
                memory_type="preferences",
                proposed_change_json={"operation": "append_entry", "content": "偏好上午安排深度任务"},
                dedup_key="memory:preferences:deep-work",
            )
            first = await service.create_candidate(user_id="local-user", payload=payload)
            second = await service.create_candidate(user_id="local-user", payload=payload)

            assert second.id == first.id
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_rejected_memory_candidate_is_not_written(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, engine = await _make_service(tmp_path)
        try:
            candidate = await service.create_candidate(
                user_id="local-user",
                payload=AssistantMemoryCandidateCreate(
                    memory_type="habits",
                    proposed_change_json={"operation": "append_entry", "content": "通常晚上复盘"},
                ),
            )
            rejected = await service.reject_candidate(user_id="local-user", candidate_id=candidate.id)
            memory = await service.read_memory(user_id="local-user")

            assert rejected.status == "rejected"
            assert all(not item.exists for item in memory.files)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
