"""Long-term assistant memory service backed by confirmed Markdown files."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.api.schemas import AssistantMemoryCandidateCreate, AssistantMemoryFileSummary, AssistantMemoryRead
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import AssistantMemoryUpdateCandidate
from app.repositories.assistant_memory_candidates import AssistantMemoryCandidateRepository


MEMORY_TYPES = ("preferences", "places", "habits", "glossary")
MEMORY_FILENAMES = {
    "preferences": "preferences.md",
    "places": "places.md",
    "habits": "habits.md",
    "glossary": "glossary.md",
}
MEMORY_TITLES = {
    "preferences": "Assistant Memory - Preferences",
    "places": "Assistant Memory - Places",
    "habits": "Assistant Memory - Habits",
    "glossary": "Assistant Memory - Glossary",
}


class AssistantMemoryService:
    """Own candidate lifecycle and confirmed Markdown writes."""

    def __init__(
        self,
        repository: AssistantMemoryCandidateRepository | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self.repository = repository or AssistantMemoryCandidateRepository(get_sessionmaker())
        self.root = root or get_settings().assistant_memory_dir

    async def create_candidate(
        self,
        *,
        user_id: str,
        payload: AssistantMemoryCandidateCreate,
    ) -> AssistantMemoryUpdateCandidate:
        self._validate_memory_type(payload.memory_type)
        proposed_change = dict(payload.proposed_change_json or {})
        self._validate_proposed_change(proposed_change)

        if payload.dedup_key:
            existing = await self.repository.get_active_by_dedup_key(user_id=user_id, dedup_key=payload.dedup_key)
            if existing is not None:
                return existing

        return await self.repository.create_candidate(
            {
                "user_id": user_id,
                **payload.model_dump(),
                "proposed_change_json": proposed_change,
            }
        )

    async def list_candidates(
        self,
        *,
        user_id: str,
        statuses: list[str] | None = None,
        memory_type: str | None = None,
        limit: int = 50,
    ) -> list[AssistantMemoryUpdateCandidate]:
        if memory_type is not None:
            self._validate_memory_type(memory_type)
        return await self.repository.list_candidates(
            user_id=user_id,
            statuses=statuses,
            memory_type=memory_type,
            limit=limit,
        )

    async def get_candidate(self, *, user_id: str, candidate_id: int) -> AssistantMemoryUpdateCandidate:
        candidate = await self.repository.get_candidate(candidate_id, user_id=user_id)
        if candidate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory candidate not found")
        return candidate

    async def confirm_candidate(self, *, user_id: str, candidate_id: int) -> AssistantMemoryUpdateCandidate:
        candidate = await self.get_candidate(user_id=user_id, candidate_id=candidate_id)
        if candidate.status == "written":
            return candidate
        if candidate.status == "rejected":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="memory candidate is rejected")
        if candidate.status not in {"proposed", "confirmed"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"memory candidate is {candidate.status}")

        now = datetime.now(timezone.utc)
        if candidate.status == "proposed":
            confirmed = await self.repository.update_candidate(
                candidate.id,
                user_id=user_id,
                payload={"status": "confirmed", "confirmed_at": now},
            )
            if confirmed is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory candidate not found")
            candidate = confirmed

        self._append_candidate_to_file(candidate, written_at=now)
        written = await self.repository.update_candidate(
            candidate.id,
            user_id=user_id,
            payload={"status": "written", "written_at": now},
        )
        if written is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory candidate not found")
        return written

    async def reject_candidate(self, *, user_id: str, candidate_id: int) -> AssistantMemoryUpdateCandidate:
        candidate = await self.get_candidate(user_id=user_id, candidate_id=candidate_id)
        if candidate.status == "written":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="written memory candidate cannot be rejected")
        if candidate.status == "rejected":
            return candidate
        rejected = await self.repository.update_candidate(
            candidate.id,
            user_id=user_id,
            payload={"status": "rejected", "rejected_at": datetime.now(timezone.utc)},
        )
        if rejected is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory candidate not found")
        return rejected

    async def read_memory(self, *, user_id: str) -> AssistantMemoryRead:
        user_root = self._user_root(user_id)
        files = [self._file_summary(user_root, memory_type) for memory_type in MEMORY_TYPES]
        return AssistantMemoryRead(user_id=user_id, root=str(user_root), files=files)

    def _append_candidate_to_file(self, candidate: AssistantMemoryUpdateCandidate, *, written_at: datetime) -> None:
        memory_type = self._validate_memory_type(candidate.memory_type)
        user_root = self._user_root(candidate.user_id)
        path = user_root / MEMORY_FILENAMES[memory_type]
        if not path.exists():
            self._initialize_memory_file(path, memory_type=memory_type)

        change = dict(candidate.proposed_change_json or {})
        entry = self._render_entry(candidate, change=change, written_at=written_at)
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(f"{text}\n{entry}", encoding="utf-8")

    def _render_entry(
        self,
        candidate: AssistantMemoryUpdateCandidate,
        *,
        change: dict[str, Any],
        written_at: datetime,
    ) -> str:
        title = str(change.get("title") or f"{candidate.memory_type} update").strip()
        content = str(change.get("content") or "").strip()
        metadata = change.get("metadata")
        lines = [
            f"### {written_at.isoformat()} - {title}",
            "",
            content,
            "",
            f"- candidate_id: {candidate.id}",
            f"- source: {candidate.source_specialist}",
            f"- confidence: {candidate.confidence:.2f}",
        ]
        if candidate.reason:
            lines.append(f"- reason: {candidate.reason}")
        if isinstance(metadata, dict) and metadata:
            lines.append(f"- metadata: {metadata}")
        lines.append("")
        return "\n".join(lines)

    def _initialize_memory_file(self, path: Path, *, memory_type: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        title = MEMORY_TITLES[memory_type]
        path.write_text(
            "\n".join(
                [
                    f"# {title}",
                    "",
                    "This file is maintained only through confirmed memory update candidates.",
                    "",
                    "## Entries",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _file_summary(self, user_root: Path, memory_type: str) -> AssistantMemoryFileSummary:
        path = user_root / MEMORY_FILENAMES[memory_type]
        if not path.exists():
            return AssistantMemoryFileSummary(memory_type=memory_type, path=str(path), exists=False)
        lines = path.read_text(encoding="utf-8").splitlines()
        stat = path.stat()
        preview = [line for line in lines if line.strip()][:8]
        return AssistantMemoryFileSummary(
            memory_type=memory_type,
            path=str(path),
            exists=True,
            line_count=len(lines),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            preview=preview,
        )

    def _user_root(self, user_id: str) -> Path:
        safe_user = re.sub(r"[^A-Za-z0-9_.-]+", "_", user_id).strip("._") or "local-user"
        root = (self.root / safe_user).resolve()
        base = self.root.resolve()
        if base != root and base not in root.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid memory path")
        return root

    def _validate_memory_type(self, memory_type: str) -> str:
        if memory_type not in MEMORY_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported memory type")
        return memory_type

    def _validate_proposed_change(self, proposed_change: dict[str, Any]) -> None:
        operation = proposed_change.get("operation") or "append_entry"
        if operation != "append_entry":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported memory change operation")
        content = proposed_change.get("content")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="memory change content is required")
