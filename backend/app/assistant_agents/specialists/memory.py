"""Memory specialist skeleton for explicit long-term memory candidates."""

from __future__ import annotations

import hashlib

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
        return any(marker in text for marker in ("记住", "帮我记", "以后记得", "保存一下", "请记")) or "remember" in lowered

    def extract_candidate(self, message: str) -> dict | None:
        text = message.strip()
        if not text:
            return None
        if not self.is_explicit_memory_request(text):
            return None

        memory_type = self._classify_memory_type(text)
        content = self._strip_memory_prefix(text)
        digest = hashlib.sha256(f"{memory_type}:{content}".encode("utf-8")).hexdigest()[:16]
        return {
            "memory_type": memory_type,
            "source_specialist": self.name,
            "status": "proposed",
            "confidence": 0.7,
            "proposed_change_json": {
                "operation": "append_entry",
                "title": self._title_for(memory_type, content),
                "content": content,
            },
            "reason": "User explicitly asked the assistant to remember this.",
            "dedup_key": f"memory:{memory_type}:{digest}",
        }

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
