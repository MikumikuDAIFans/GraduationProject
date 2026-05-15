"""Memory specialist skeleton for explicit long-term memory candidates."""

from __future__ import annotations

import hashlib
import re

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState


class MemorySpecialist:
    """Prepare candidate payloads without writing memory files.

    Phase 8 keeps the actual Markdown write behind the memory candidate confirm
    API. This specialist only detects explicit "remember this" style requests
    and prepares structured candidate payloads for a future conductor hook.
    """

    name = "memory"

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        candidate = self.extract_candidate(context.user_message)
        if candidate is None:
            return state
        state.metadata.setdefault("memory_candidate_create_payloads", []).append(candidate)
        return state

    def is_explicit_memory_request(self, message: str) -> bool:
        text = message.strip()
        if not text:
            return False
        lowered = text.lower()
        return (
            any(marker in text for marker in ("记住", "帮我记", "以后记得", "保存一下", "请记"))
            or self._extract_place_alias_instruction(text) is not None
            or "remember" in lowered
        )

    def extract_candidate(self, message: str) -> dict | None:
        text = message.strip()
        if not text:
            return None
        if not self.is_explicit_memory_request(text):
            return None

        alias_instruction = self._extract_place_alias_instruction(text)
        if alias_instruction is not None:
            alias, target = alias_instruction
            memory_type = "places"
            title = alias
            content = f"{alias} = {target}"
            confidence = 0.85
            reason = "User explicitly defined a place alias."
        else:
            memory_type = self._classify_memory_type(text)
            content = self._strip_memory_prefix(text)
            title = self._title_for(memory_type, content)
            confidence = 0.7
            reason = "User explicitly asked the assistant to remember this."
        digest = hashlib.sha256(f"{memory_type}:{content}".encode("utf-8")).hexdigest()[:16]
        return {
            "memory_type": memory_type,
            "source_specialist": self.name,
            "status": "proposed",
            "confidence": confidence,
            "proposed_change_json": {
                "operation": "append_entry",
                "title": title,
                "content": content,
            },
            "reason": reason,
            "dedup_key": f"memory:{memory_type}:{digest}",
        }

    def _extract_place_alias_instruction(self, text: str) -> tuple[str, str] | None:
        patterns = [
            r"^以后把(?P<alias>[^，。,;；\n]{1,24}?)理解为(?P<target>[^，。,;；\n]{2,80})",
            r"^以后(?P<alias>[^，。,;；\n]{1,24}?)(?:指的是|就是|是)(?P<target>[^，。,;；\n]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            alias = self._clean_place_alias(match.group("alias"))
            target = self._clean_place_target(match.group("target"))
            if alias and target and alias != target:
                return alias, target
        return None

    def _clean_place_alias(self, value: str | None) -> str:
        return (value or "").strip(" ：:，,。；; \t\r\n")

    def _clean_place_target(self, value: str | None) -> str:
        return (value or "").strip(" ：:，,。；; \t\r\n")

    def _classify_memory_type(self, text: str) -> str:
        if any(token in text for token in ("地点", "地址", "学校", "图书馆", "驾校", "公司", "家")):
            return "places"
        if any(token in text for token in ("习惯", "通常", "每天", "每周", "早上", "晚上")):
            return "habits"
        if any(token in text for token in ("叫做", "意思是", "术语", "简称")):
            return "glossary"
        return "preferences"

    def _strip_memory_prefix(self, text: str) -> str:
        prefixes = (
            "请帮我记住",
            "请帮我记一下",
            "帮我记住",
            "帮我记一下",
            "帮我记",
            "请记住",
            "请记一下",
            "记住",
            "记一下",
            "以后记得",
            "保存一下",
        )
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix) :].strip(" ：:，,。")
        return text

    def _title_for(self, memory_type: str, content: str) -> str:
        trimmed = content[:32].strip()
        return trimmed or f"{memory_type} memory"
