"""情境感知提醒服务 — 结合天气、交通、习惯的智能提醒"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReminderPayload(BaseModel):
    """提醒载荷"""
    event_id: int
    message: str
    priority: str = "normal"  # low/normal/high/urgent
    channels: list[str] = ["websocket"]
    remind_at: Optional[datetime] = None
    metadata: dict = {}


class ContextualReminderService:
    """情境感知提醒服务"""

    def __init__(self, weather_service=None, maps_service=None, habit_retriever=None):
        self.weather_service = weather_service
        self.maps_service = maps_service
        self.habit_retriever = habit_retriever

    async def generate_smart_reminder(self, event) -> ReminderPayload:
        """生成情境感知的提醒"""
        # 1. 获取当前天气
        weather = None
        if self.weather_service and getattr(event, "location_coords", None):
            try:
                weather = await self.weather_service.get_weather(event.location_coords)
            except Exception as e:
                logger.debug(f"Failed to get weather: {e}")

        # 2. 获取实时交通
        traffic = None
        if self.maps_service and getattr(event, "location_coords", None):
            try:
                user_home = getattr(event, "user_home_coords", None)
                if user_home:
                    traffic = await self.maps_service.get_traffic_status(
                        origin=user_home,
                        destination=event.location_coords,
                        departure_time=getattr(event, "departure_time", None),
                    )
            except Exception as e:
                logger.debug(f"Failed to get traffic: {e}")

        # 3. 获取类似历史经验
        similar_experience = None
        if self.habit_retriever:
            try:
                similar_experience = await self.habit_retriever.get_similar_experience(
                    event.title or ""
                )
            except Exception as e:
                logger.debug(f"Failed to get similar experience: {e}")

        # 4. 构建提醒文案
        message = self._build_contextual_message(event, weather, traffic, similar_experience)

        # 5. 计算优先级
        priority = self._calculate_priority(event, weather, traffic)

        # 6. 确定提醒时间
        remind_at = self._calculate_remind_time(event, traffic)

        return ReminderPayload(
            event_id=event.id,
            message=message,
            priority=priority,
            channels=self._select_channels(priority),
            remind_at=remind_at,
            metadata={
                "weather": weather.dict() if hasattr(weather, "dict") else weather,
                "traffic": traffic if traffic else None,
                "similar_experience": similar_experience,
            },
        )

    def _build_contextual_message(
        self,
        event,
        weather: Optional[dict],
        traffic: Optional[dict],
        similar_experience: Optional[list],
    ) -> str:
        """构建情境感知的提醒文案"""
        parts = []

        # 基本信息
        start_time = event.start_time
        if isinstance(start_time, datetime):
            time_str = start_time.strftime("%H:%M")
        else:
            time_str = str(start_time)

        parts.append(f"⏰ 提醒：{event.title} 将在 {time_str} 开始")

        # 天气增强
        if weather:
            condition = weather.get("condition", "").lower()
            description = weather.get("description", "")
            temp = weather.get("temperature", "")

            if condition in ["rain", "snow", "storm"]:
                parts.append(f"🌧️ 外面正在{description}，记得带伞")
            elif condition == "hot":
                parts.append(f"☀️ 气温较高（{temp}°C），注意防晒")
            elif condition == "cold":
                parts.append(f"❄️ 气温较低（{temp}°C），注意保暖")

        # 交通增强
        if traffic:
            congestion = traffic.get("congestion_level", "")
            extra_minutes = traffic.get("extra_delay_minutes", 0)

            if congestion in ["heavy", "severe"]:
                parts.append(
                    f"🚗 当前路况{congestion}，比平时多 {extra_minutes} 分钟，建议提前出发"
                )
            elif congestion == "moderate":
                parts.append("🚗 路况一般，建议预留充足时间")

        # 习惯增强
        if similar_experience and len(similar_experience) > 0:
            exp = similar_experience[0]
            lesson = exp.get("metadata", {}).get("lesson", "")
            if lesson:
                parts.append(f"💡 上次类似情况：{lesson}")

        # 能量水平提示
        energy = getattr(event, "energy_level", None)
        if energy:
            energy_messages = {
                "high": "💪 这是你的高效时段，加油！",
                "medium": "😊 状态不错，继续保持",
                "low": "😴 这个时段你可能比较疲惫，适当休息",
            }
            msg = energy_messages.get(energy, "")
            if msg:
                parts.append(msg)

        return "\n".join(parts)

    def _calculate_priority(
        self, event, weather: Optional[dict], traffic: Optional[dict]
    ) -> str:
        """计算提醒优先级"""
        priority_score = 0

        # 基础优先级
        event_priority = getattr(event, "priority", 0)
        priority_score += event_priority or 0

        # 天气风险
        if weather:
            condition = weather.get("condition", "").lower()
            if condition in ["storm", "blizzard", "typhoon"]:
                priority_score += 3
            elif condition in ["rain", "snow"]:
                priority_score += 1

        # 交通风险
        if traffic:
            congestion = traffic.get("congestion_level", "")
            if congestion in ["severe", "standstill"]:
                priority_score += 2
            elif congestion == "heavy":
                priority_score += 1

        # 时间紧迫性
        if hasattr(event, "start_time") and isinstance(event.start_time, datetime):
            time_until_event = event.start_time - datetime.utcnow()
            if time_until_event < timedelta(minutes=15):
                priority_score += 3
            elif time_until_event < timedelta(minutes=30):
                priority_score += 1

        # 映射到优先级
        if priority_score >= 5:
            return "urgent"
        elif priority_score >= 3:
            return "high"
        elif priority_score >= 1:
            return "normal"
        else:
            return "low"

    def _calculate_remind_time(self, event, traffic: Optional[dict]) -> datetime:
        """计算最佳提醒时间"""
        start_time = event.start_time
        if not isinstance(start_time, datetime):
            return datetime.utcnow()

        # 基础提醒时间：事件开始前 30 分钟
        base_remind_time = start_time - timedelta(minutes=30)

        # 如果有交通拥堵，提前提醒
        if traffic:
            extra_minutes = traffic.get("extra_delay_minutes", 0)
            if extra_minutes > 0:
                base_remind_time -= timedelta(minutes=extra_minutes)

        # 如果有出发时间，使用出发时间
        departure_time = getattr(event, "departure_time", None)
        if departure_time and isinstance(departure_time, datetime):
            base_remind_time = min(base_remind_time, departure_time - timedelta(minutes=10))

        return base_remind_time

    def _select_channels(self, priority: str) -> list[str]:
        """根据优先级选择通知渠道"""
        if priority == "urgent":
            return ["websocket", "desktop_notification", "email", "sms"]
        elif priority == "high":
            return ["websocket", "desktop_notification", "email"]
        elif priority == "normal":
            return ["websocket", "desktop_notification"]
        else:
            return ["websocket"]
