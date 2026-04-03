"""Utilities for producing readable assistant replies."""

from __future__ import annotations

import json
import re


class AssistantResponseFormatter:
    """Normalize raw assistant text into user-facing markdown."""

    def format_reply(self, text: str, *, prefers_chinese: bool) -> str:
        candidate = self._unwrap_json_reply(text)
        candidate = candidate.replace("\r\n", "\n").strip()
        candidate = re.sub(r"<script.*?>.*?</script>", "", candidate, flags=re.I | re.S)
        candidate = self._normalize_markdown(candidate)
        if candidate:
            return candidate
        return "我暂时没有生成可展示的回复，请再试一次。" if prefers_chinese else "I could not produce a displayable reply yet. Please try again."

    def build_clarification_reply(
        self,
        *,
        intent: str,
        missing_fields: list[str],
        prefers_chinese: bool,
    ) -> str:
        if prefers_chinese:
            readable_fields = {
                "title": "事项名称",
                "start_time": "开始时间",
                "end_time": "结束时间",
                "content": "任务内容",
                "deadline": "截止时间",
            }
            labels = [readable_fields.get(item, item) for item in missing_fields]
            if intent == "create_event":
                return (
                    "我可以帮你创建日程，不过还缺少关键信息："
                    + "、".join(labels)
                    + "。例如你可以说：“明天下午 3 点到 4 点在图书馆开组会”。"
                )
            return (
                "我可以帮你创建任务，不过还缺少关键信息："
                + "、".join(labels)
                + "。例如你可以说：“提醒我明晚前完成论文初稿，预计两小时”。"
            )

        field_text = ", ".join(missing_fields)
        if intent == "create_event":
            return (
                "I can create the event for you, but I still need: "
                f"{field_text}. For example: 'Tomorrow 3:00-4:00 PM team meeting at the library.'"
            )
        return (
            "I can create the task for you, but I still need: "
            f"{field_text}. For example: 'Remind me to finish the thesis draft by tomorrow evening, about two hours.'"
        )

    def _unwrap_json_reply(self, text: str) -> str:
        candidate = text.strip()
        if not candidate:
            return ""
        if candidate.startswith("```") and candidate.endswith("```"):
            candidate = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", candidate)
            candidate = re.sub(r"\n?```$", "", candidate)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return candidate

        if isinstance(payload, dict):
            reply = payload.get("reply")
            if isinstance(reply, str) and reply.strip():
                return reply.strip()
        return candidate

    def _normalize_markdown(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?m)^(\d+)\)\s+", r"\1. ", text)
        text = re.sub(r"(?m)^\s*•\s+", "- ", text)
        return text.strip()
