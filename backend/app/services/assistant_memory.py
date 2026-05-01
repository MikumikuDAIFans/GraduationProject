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

    async def build_runtime_context(self, *, user_id: str, limit_per_type: int = 6) -> dict[str, Any]:
        """Return a compact, read-only summary of confirmed Markdown memories."""
        user_root = self._user_root(user_id)
        context: dict[str, Any] = {
            "source": "confirmed_long_term_memory",
            "write_policy": "read_only; updates require memory candidate confirmation",
        }
        has_entries = False
        for memory_type in MEMORY_TYPES:
            path = user_root / MEMORY_FILENAMES[memory_type]
            entries = self._extract_runtime_entries(path, limit=limit_per_type)
            if entries:
                context[memory_type] = entries
                has_entries = True
        return context if has_entries else {}

    def extract_place_aliases(self, memory_context: dict[str, Any] | None) -> list[dict[str, str]]:
        """Parse conservative place aliases from confirmed place memories."""
        if not isinstance(memory_context, dict):
            return []
        entries = memory_context.get("places")
        if not isinstance(entries, list):
            return []

        aliases: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_entry in entries:
            if not isinstance(raw_entry, str):
                continue
            parsed = self._parse_place_memory_entry(raw_entry)
            if parsed is None:
                continue
            key = f"{parsed.get('alias', '').lower()}|{parsed.get('location_name', '').lower()}|{parsed.get('location_coords', '')}"
            if key in seen:
                continue
            seen.add(key)
            aliases.append(parsed)
        return aliases

    def resolve_place_alias(
        self,
        *,
        user_message: str,
        location_name: str | None,
        memory_context: dict[str, Any] | None,
    ) -> dict[str, str] | None:
        """Resolve an extracted location through confirmed place memories."""
        aliases = self.extract_place_aliases(memory_context)
        if not aliases:
            return None

        message = (user_message or "").lower()
        extracted_location = (location_name or "").strip().lower()
        for item in aliases:
            alias = item.get("alias", "").strip()
            if not alias:
                continue
            alias_lower = alias.lower()
            if extracted_location and (
                extracted_location == alias_lower
                or alias_lower in extracted_location
                or extracted_location in alias_lower
            ):
                return item
        if extracted_location:
            return None
        for item in aliases:
            alias = item.get("alias", "").strip()
            if alias and alias.lower() in message:
                return item
        return None

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

    def _extract_runtime_entries(self, path: Path, *, limit: int) -> list[str]:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        entries: list[str] = []
        current_title: str | None = None
        current_body: list[str] = []

        def flush_current() -> None:
            nonlocal current_title, current_body
            if current_title is None and not current_body:
                return
            body = " ".join(item.strip() for item in current_body if item.strip())
            if current_title and body:
                entries.append(f"{current_title}: {body}")
            elif body:
                entries.append(body)
            elif current_title:
                entries.append(current_title)
            current_title = None
            current_body = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("### "):
                flush_current()
                current_title = self._strip_runtime_heading(line)
                continue
            if self._is_runtime_context_line(line):
                current_body.append(line)
        flush_current()
        return entries[-limit:]

    def _strip_runtime_heading(self, line: str) -> str:
        heading = line.removeprefix("### ").strip()
        if " - " in heading:
            return heading.split(" - ", 1)[1].strip()
        return heading

    def _is_runtime_context_line(self, line: str) -> bool:
        if line.startswith("#") or line == "This file is maintained only through confirmed memory update candidates.":
            return False
        if line.startswith("- candidate_id:") or line.startswith("- source:") or line.startswith("- confidence:"):
            return False
        if line.startswith("- reason:") or line.startswith("- metadata:"):
            return False
        return True

    def _parse_place_memory_entry(self, raw_entry: str) -> dict[str, str] | None:
        text = " ".join(raw_entry.strip().split())
        if not text:
            return None

        title: str | None = None
        body = text
        title_match = re.match(r"^(?P<title>[^:：]{1,32})[:：]\s*(?P<body>.+)$", text)
        if title_match:
            title = title_match.group("title").strip()
            body = title_match.group("body").strip()

        coords = self._extract_place_coords(text)
        body_without_coords = self._strip_place_coords(body)

        parsed = self._parse_place_alias_target(body_without_coords)
        if parsed is None and title and not self._is_generic_place_title(title):
            target = self._clean_place_target(body_without_coords)
            if target and target != title:
                parsed = {"alias": title, "location_name": target}
        if parsed is None:
            parsed = self._parse_place_alias_target(self._strip_place_coords(text))
        if parsed is None:
            return None

        alias = self._clean_place_alias(parsed.get("alias"))
        location_name = self._clean_place_target(parsed.get("location_name"))
        if not alias or not location_name or alias == location_name:
            return None
        result = {"alias": alias, "location_name": location_name}
        if coords:
            result["location_coords"] = coords
        return result

    def _parse_place_alias_target(self, text: str) -> dict[str, str] | None:
        patterns = [
            r"(?P<alias>[\u4e00-\u9fa5A-Za-z0-9·_\-\s]{1,24})\s*(?:=|＝|是|位于|在)\s*(?P<target>[^，。,;；\n]{2,80})",
            r"(?P<alias>[A-Za-z0-9][A-Za-z0-9_\-\s]{1,24})\s+(?:is|at|in)\s+(?P<target>[^,.;\n]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return {"alias": match.group("alias"), "location_name": match.group("target")}
        return None

    def _extract_place_coords(self, text: str) -> str | None:
        match = re.search(r"(-?\d{1,3}(?:\.\d+)?)\s*[,，]\s*(-?\d{1,3}(?:\.\d+)?)", text)
        if not match:
            return None
        first = float(match.group(1))
        second = float(match.group(2))
        if not (-180 <= first <= 180 and -90 <= second <= 90):
            return None
        return f"{match.group(1)},{match.group(2)}"

    def _strip_place_coords(self, text: str) -> str:
        without_label = re.sub(
            r"(?:坐标|经纬度|位置)\s*[:：]?\s*-?\d{1,3}(?:\.\d+)?\s*[,，]\s*-?\d{1,3}(?:\.\d+)?",
            "",
            text,
        )
        return re.sub(r"\s+", " ", without_label).strip(" ，。,;；")

    def _clean_place_alias(self, raw: str | None) -> str | None:
        if not raw:
            return None
        value = raw.strip(" ，。,;；:：")
        value = re.sub(r"^(?:我的|我常去的|常去的|常用的)", "", value).strip()
        if not value or value in {"我", "你", "他", "她", "它", "这里", "那里"}:
            return None
        if len(value) > 24:
            return None
        return value

    def _clean_place_target(self, raw: str | None) -> str | None:
        if not raw:
            return None
        value = raw.strip(" ，。,;；:：")
        value = re.sub(r"(?:坐标|经纬度|位置)\s*$", "", value).strip(" ，。,;；:：")
        return value or None

    def _is_generic_place_title(self, title: str) -> bool:
        normalized = title.strip().lower()
        return normalized in {"place", "places", "地点", "常用地点", "常去地点", "位置", "places update"}

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
