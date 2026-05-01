"""增强版意图解析器 — 结合向量检索的语义理解"""

import logging
import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ParsedIntent(BaseModel):
    """解析后的意图"""
    intent: str  # create_event, create_task, query_events, etc.
    activity: Optional[str] = None
    time_context: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    confidence: float = 0.5
    habit_reference: Optional[str] = None
    preference_warnings: list[str] = []
    raw_message: str = ""


class EnhancedIntentParser:
    """增强版意图解析器，结合向量检索"""

    def __init__(self, habit_retriever=None, llm_client=None):
        self.habit_retriever = habit_retriever
        self.llm = llm_client

    async def parse_with_context(self, message: str, user_id: str) -> ParsedIntent:
        """
        结合用户习惯解析意图
        
        例："晚上回家做饭" → 
        1. 基础解析：activity="做饭", time_context="晚上"
        2. 习惯检索：检索到用户常在 18:00 做饭
        3. 增强结果：activity="做饭", start_time="18:00", confidence=0.85
        """
        # 1. 基础 LLM 解析
        base_result = await self._basic_parse(message)

        # 2. 如果有活动关键词，检索相关习惯
        if base_result.activity and self.habit_retriever:
            try:
                habit_match = await self.habit_retriever.suggest_time(
                    activity=base_result.activity,
                    context=base_result.time_context or "",
                )

                if habit_match and habit_match.get("confidence", 0) > 0.7:
                    # 用习惯数据增强解析结果
                    base_result.start_time = habit_match.get("time_pattern")
                    base_result.confidence = max(
                        base_result.confidence,
                        habit_match.get("confidence", 0) * 0.9,
                    )
                    base_result.habit_reference = habit_match.get("id")
            except Exception as e:
                logger.debug(f"Habit retrieval failed: {e}")

        # 3. 检查是否违反用户偏好
        if self.habit_retriever:
            try:
                proposal = {
                    "activity": base_result.activity,
                    "time": base_result.start_time,
                    "location": base_result.location,
                }
                violates = await self.habit_retriever.check_preference(proposal)
                if violates:
                    base_result.preference_warnings = violates
            except Exception as e:
                logger.debug(f"Preference check failed: {e}")

        base_result.raw_message = message
        return base_result

    async def _basic_parse(self, message: str) -> ParsedIntent:
        """基础意图解析，优先走规则，必要时再使用 LLM 兜底。"""
        rule_result = self._rule_based_parse(message)
        if rule_result.intent != "unknown":
            return rule_result
        if not self.llm:
            return rule_result
        return await self._llm_parse(message, fallback=rule_result)

    def _rule_based_parse(self, message: str) -> ParsedIntent:
        result = ParsedIntent(intent="unknown", confidence=0.0, raw_message=message)
        msg_lower = message.lower()

        time_keywords = {
            "早上": ("morning", "09:00"),
            "上午": ("morning", "10:00"),
            "中午": ("noon", "12:00"),
            "下午": ("afternoon", "14:00"),
            "晚上": ("evening", "19:00"),
            "傍晚": ("evening", "17:30"),
            "深夜": ("night", "23:00"),
        }

        for keyword, (context, default_time) in time_keywords.items():
            if keyword in msg_lower:
                result.time_context = context
                result.start_time = default_time
                break

        activity_keywords = [
            "做饭", "买菜", "吃饭", "开会", "运动", "跑步", "健身",
            "学习", "阅读", "写作", "购物", "打扫", "洗衣",
        ]
        for keyword in activity_keywords:
            if keyword in msg_lower:
                result.activity = keyword
                break

        location_keywords = ["家", "公司", "学校", "超市", "健身房", "公园", "餐厅"]
        for keyword in location_keywords:
            if keyword in msg_lower:
                result.location = keyword
                break

        if any(word in msg_lower for word in ["提醒", "提醒我", "别忘了"]):
            result.intent = "create_reminder"
            result.confidence = 0.8
        elif any(word in msg_lower for word in ["任务", "待办", "todo"]):
            result.intent = "create_task"
            result.confidence = 0.8
        elif any(word in msg_lower for word in ["查询", "查看", "有什么", "日程", "安排"]):
            result.intent = "query_events"
            result.confidence = 0.75
        elif result.activity or result.start_time or result.location:
            result.intent = "create_event"
            result.confidence = 0.65

        return result

    async def _llm_parse(self, message: str, *, fallback: ParsedIntent) -> ParsedIntent:
        from app.workflow.prompts import INTENT_DETECTION_TEMPLATE
        prompt = INTENT_DETECTION_TEMPLATE.format(user_message=message)

        try:
            response_text = await self.llm.generate_text(prompt)
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not json_match:
                logger.warning(f"Failed to extract JSON from LLM response: {response_text}")
                return fallback

            data = json.loads(json_match.group(0))
            slots = data.get("slots", {})

            return ParsedIntent(
                intent=data.get("intent", "unknown"),
                activity=slots.get("title") or slots.get("activity"),
                time_context=slots.get("time_context") or slots.get("start_time"),
                start_time=slots.get("start_time"),
                end_time=slots.get("end_time"),
                location=slots.get("location"),
                confidence=data.get("confidence", 0.5),
                raw_message=message,
            )
        except Exception as exc:
            logger.error(f"LLM intent parsing failed: {exc}")
            return fallback

    async def extract_slots(self, message: str, required_slots: list[str]) -> dict:
        """从消息中提取槽位值"""
        slots = {}
        msg_lower = message.lower()
        
        if "title" in required_slots or "title" in message:
            # 简化版：提取第一个名词短语作为标题
            slots["title"] = message[:20]
        
        if "start_time" in required_slots:
            # 提取时间表达
            import re
            time_patterns = [
                (r"(\d{1,2}):(\d{2})", lambda m: f"{int(m.group(1)):02d}:{m.group(2)}"),
                (r"(\d{1,2})点", lambda m: f"{int(m.group(1)):02d}:00"),
                (r"(\d{1,2})点半", lambda m: f"{int(m.group(1)):02d}:30"),
            ]
            for pattern, formatter in time_patterns:
                match = re.search(pattern, message)
                if match:
                    slots["start_time"] = formatter(match)
                    break
        
        if "location" in required_slots:
            location_keywords = ["家", "公司", "学校", "超市", "健身房", "公园", "餐厅"]
            for keyword in location_keywords:
                if keyword in msg_lower:
                    slots["location"] = keyword
                    break
        
        return slots
