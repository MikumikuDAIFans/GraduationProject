"""提醒聚合与降噪服务 — 避免提醒轰炸"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Reminder(BaseModel):
    """提醒模型"""
    id: int
    user_id: str
    target_type: str  # event/task/batch
    target_id: Optional[int] = None
    target_ids: list[int] = []
    message: str
    remind_at: datetime
    priority: str = "normal"
    delivery_channel: str = "websocket"


class ReminderAggregator:
    """提醒聚合与降噪服务"""

    def __init__(self):
        self.cooldown_minutes = 15  # 冷却时间
        self.aggregation_window_minutes = 30  # 聚合时间窗口
        self.last_sent: dict[int, datetime] = {}  # event_id -> last_sent_time
        self.do_not_disturb = {
            "start": "23:00",
            "end": "07:00",
        }

    async def should_send_reminder(self, reminder: Reminder) -> bool:
        """判断是否应该发送提醒"""
        # 1. 免打扰时段检查
        if self._is_in_dnd_period(reminder.remind_at):
            logger.debug(f"Reminder {reminder.id} suppressed: DND period")
            return False

        # 2. 冷却检查
        if self._is_in_cooldown(reminder.target_id or reminder.id):
            logger.debug(f"Reminder {reminder.id} suppressed: cooldown period")
            return False

        # 3. 重复提醒检查
        if await self._already_sent_similar(reminder):
            logger.debug(f"Reminder {reminder.id} suppressed: already sent similar")
            return False

        return True

    async def aggregate_reminders(
        self, reminders: list[Reminder]
    ) -> list[Reminder]:
        """聚合相近时间的提醒"""
        if len(reminders) <= 1:
            return reminders

        # 按时间排序
        reminders.sort(key=lambda r: r.remind_at)

        aggregated = []
        current_batch = [reminders[0]]

        for reminder in reminders[1:]:
            time_diff = (
                reminder.remind_at - current_batch[0].remind_at
            ).total_seconds() / 60

            if time_diff <= self.aggregation_window_minutes:
                current_batch.append(reminder)
            else:
                # 批次结束，生成聚合提醒
                aggregated.append(self._merge_batch(current_batch))
                current_batch = [reminder]

        # 处理最后一批
        if current_batch:
            aggregated.append(self._merge_batch(current_batch))

        return aggregated

    def _merge_batch(self, batch: list[Reminder]) -> Reminder:
        """将一批提醒合并为一条"""
        messages = [r.message for r in batch]
        merged_message = f"你有 {len(batch)} 条即将发生的提醒：\n" + "\n".join(
            f"- {msg}" for msg in messages
        )

        # 使用最高优先级
        priority_order = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
        highest_priority = max(
            batch, key=lambda r: priority_order.get(r.priority, 0)
        ).priority

        return Reminder(
            id=batch[0].id,
            user_id=batch[0].user_id,
            target_type="batch",
            target_ids=[r.target_id for r in batch if r.target_id],
            message=merged_message,
            remind_at=batch[0].remind_at,
            priority=highest_priority,
            delivery_channel=batch[0].delivery_channel,
        )

    def _is_in_dnd_period(self, remind_at: datetime) -> bool:
        """检查是否在免打扰时段"""
        dnd_start = datetime.strptime(self.do_not_disturb["start"], "%H:%M").time()
        dnd_end = datetime.strptime(self.do_not_disturb["end"], "%H:%M").time()

        remind_time = remind_at.time()

        if dnd_start > dnd_end:
            # 跨午夜的情况（如 23:00 - 07:00）
            return remind_time >= dnd_start or remind_time <= dnd_end
        else:
            return dnd_start <= remind_time <= dnd_end

    def _is_in_cooldown(self, target_id: int) -> bool:
        """检查是否在冷却期"""
        if target_id not in self.last_sent:
            return False

        time_since_last_sent = (
            datetime.utcnow() - self.last_sent[target_id]
        ).total_seconds() / 60

        return time_since_last_sent < self.cooldown_minutes

    def mark_sent(self, target_id: int):
        """标记提醒已发送"""
        self.last_sent[target_id] = datetime.utcnow()

    async def _already_sent_similar(self, reminder: Reminder) -> bool:
        """检查是否已发送过类似提醒"""
        # 简化版：检查同一目标在过去 1 小时内是否有提醒
        target_id = reminder.target_id or reminder.id
        if target_id not in self.last_sent:
            return False

        time_since_last_sent = (
            datetime.utcnow() - self.last_sent[target_id]
        ).total_seconds() / 60

        return time_since_last_sent < 60  # 1 小时内不重复提醒

    def clear_old_entries(self, max_age_minutes: int = 120):
        """清理旧的发送记录"""
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        to_remove = [
            target_id
            for target_id, sent_time in self.last_sent.items()
            if sent_time < cutoff
        ]
        for target_id in to_remove:
            del self.last_sent[target_id]
