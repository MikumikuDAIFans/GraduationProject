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


def test_memory_runtime_context_summarizes_confirmed_markdown_without_metadata(tmp_path: Path) -> None:
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
                ),
            )
            await service.confirm_candidate(user_id="local-user", candidate_id=candidate.id)

            context = await service.build_runtime_context(user_id="local-user")

            assert context["source"] == "confirmed_long_term_memory"
            assert context["places"] == ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"]
            assert "candidate_id" not in str(context)
            assert "confidence" not in str(context)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_memory_service_resolves_confirmed_place_aliases() -> None:
    service = AssistantMemoryService()
    memory_context = {
        "source": "confirmed_long_term_memory",
        "places": [
            "学校: 学校 = 北京大学东门，坐标 116.310918,39.992873",
            "图书馆: 图书馆在中心校区图书馆",
        ],
    }

    resolved = service.resolve_place_alias(
        user_message="明天下午三点去学校上课",
        location_name="学校",
        memory_context=memory_context,
    )

    assert resolved == {
        "alias": "学校",
        "location_name": "北京大学东门",
        "location_coords": "116.310918,39.992873",
    }


def test_memory_service_ignores_unmatched_place_aliases() -> None:
    service = AssistantMemoryService()
    memory_context = {
        "source": "confirmed_long_term_memory",
        "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
    }

    resolved = service.resolve_place_alias(
        user_message="明天下午三点去咖啡馆见面",
        location_name="咖啡馆",
        memory_context=memory_context,
    )

    assert resolved is None


def test_memory_service_does_not_override_different_extracted_location() -> None:
    service = AssistantMemoryService()
    memory_context = {
        "source": "confirmed_long_term_memory",
        "places": ["学校: 学校 = 北京大学东门，坐标 116.310918,39.992873"],
    }

    resolved = service.resolve_place_alias(
        user_message="从学校出发去咖啡馆见面",
        location_name="咖啡馆",
        memory_context=memory_context,
    )

    assert resolved is None
