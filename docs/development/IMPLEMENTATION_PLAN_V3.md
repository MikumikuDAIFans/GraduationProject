# MA-IPAAS 功能补全执行方案 V3

> 本文档为项目功能补全的详细落地执行方案，面向 AI 编码助手设计，要求接手后可一次性完成所有代码修改、单元测试编写和整体测试验证。

---

## 目录

- [一、现状总结与差距分析](#一现状总结与差距分析)
- [二、执行优先级与任务清单](#二执行优先级与任务清单)
- [三、P0 — 答辩前必须完成](#三p0--答辩前必须完成)
  - [P0-1: 冲突检测 buffer 规则引擎](#p0-1-冲突检测-buffer-规则引擎)
  - [P0-2: Celery Beat 高频提醒扫描](#p0-2-celery-beat-高频提醒扫描)
  - [P0-3: 前端提醒弹窗 Toast 通知](#p0-3-前端提醒弹窗-toast-通知)
- [四、P1 — 功能完善](#四p1--功能完善)
  - [P1-1: 后台主动任务跟进 Inbox 生成](#p1-1-后台主动任务跟进-inbox-生成)
  - [P1-2: 冲突时推荐替代时段](#p1-2-冲突时推荐替代时段)
  - [P1-3: WebSocket 流式输出 AI 回复](#p1-3-websocket-流式输出-ai-回复)
- [五、P2 — 插件接口预留](#五p2--插件接口预留)
  - [P2-1: 语音输入/输出适配器接口](#p2-1-语音输入输出适配器接口)
- [六、单元测试规范](#六单元测试规范)
- [七、整体测试验证清单](#七整体测试验证清单)

---

## 一、现状总结与差距分析

### 已有架构概况

| 层级 | 现状 |
|---|---|
| 前端 | Vue 3 + TS + Vite + TailwindCSS + FullCalendar + Pinia，单 Store 架构 (`workspace.ts`)，WebSocket 驱动快照更新 |
| 后端 | FastAPI + SQLAlchemy 2 (async) + Alembic + Celery + Redis + SQLite |
| 分层 | `api/routes → services → repositories → models` |
| 数据库 | 7 张核心表均已建模完成 |
| 容器化 | Docker Compose 运行 API + Worker + Beat + Redis |

### 差距汇总（来源：README 功能对比表）

#### 部分实现（⚠️）

| # | 功能 | 当前状态 | 差距 |
|---|---|---|---|
| 1 | 冲突检测带 buffer | `buffer_before` / `buffer_after` 字段已存在于 `Event` 模型，但冲突检测逻辑仅依赖 Gemini 判断 | 缺少规则层的 buffer 计算逻辑 |
| 2 | Reminder WebSocket 推送 | 提醒写入 DB + WebSocket 快照包含提醒列表，但前端仅列表展示 | 缺少页面内 Toast 弹窗 |
| 3 | Google Calendar 双向同步 | 已实现 Google→本地导入 + 本地→Google 推送（`sync()` 方法已实现双向），但创建事件时的即时同步依赖 `sync_event()` 是否连接 | 实际已基本完成，需验证 |
| 4 | Inbox 主动生成 | Inbox 框架完整，AI 对话时可写入，但无独立后台任务主动生成 | 缺少 Celery 后台任务 |

#### 未实现（❌）

| # | 功能 | 设计书要求 |
|---|---|---|
| 5 | 高频提醒扫描（每1分钟） | 当前仅1个60秒定时任务，设计书要求4种频率 |
| 6 | 建议式重排（替代时段） | 冲突时推荐1-3个替代时间 |
| 7 | WebSocket `/ws/assistant` 流式输出 | 助手回复流式输出 |
| 8 | 语音输入/输出接口预留 | `inputAdapters/` / `outputAdapters/` 目录 |
| 9 | Capacitor 移动端封装 | Android APK |
| 10 | Tauri 2 桌面端封装 | Windows EXE + 桌面通知 |

> 注：#9 Capacitor 和 #10 Tauri 不在本执行方案范围内（属于跨平台封装工程，非功能代码）。

---

## 二、执行优先级与任务清单

| 优先级 | 任务编号 | 任务名称 | 预计涉及文件数 |
|---|---|---|---|
| **P0** | P0-1 | 冲突检测 buffer 规则引擎 | 4 |
| **P0** | P0-2 | Celery Beat 高频提醒扫描（4种频率） | 2 |
| **P0** | P0-3 | 前端提醒 Toast 弹窗 | 3 |
| **P1** | P1-1 | 后台主动任务跟进 Inbox 生成 | 3 |
| **P1** | P1-2 | 冲突时推荐替代时段 | 4 |
| **P1** | P1-3 | WebSocket `/ws/assistant` 流式输出 | 5 |
| **P2** | P2-1 | 语音输入/输出适配器接口预留 | 6 |

---

## 三、P0 — 答辩前必须完成

### P0-1: 冲突检测 buffer 规则引擎

#### 目标

在创建/更新事件时，使用规则引擎检测时间冲突（含 `buffer_before` / `buffer_after` 缓冲时间），而不是完全依赖 Gemini 判断。冲突信息作为 action 返回给前端展示。

#### 涉及文件

1. `backend/app/services/events.py` — 新增 `detect_conflicts()` 方法
2. `backend/app/services/suggestions.py` — `_compute_gaps_for_date()` 增加 buffer 扣除
3. `backend/app/services/assistant.py` — 在 `_execute_actions()` 的 `create_event` 分支中调用冲突检测
4. `backend/tests/test_conflict_detection.py` — 新增单元测试

#### 详细实现步骤

##### 步骤 1：在 `EventService` 中新增冲突检测方法

**文件**: `backend/app/services/events.py`

在 `EventService` 类中新增方法 `detect_conflicts`：

```python
async def detect_conflicts(
    self,
    user_id: str,
    start_time: datetime,
    end_time: datetime,
    buffer_before: int = 0,
    buffer_after: int = 0,
    exclude_event_id: int | None = None,
) -> list[EventRead]:
    """
    检测给定时间段（含 buffer）是否与已有事件冲突。

    冲突判断规则（来源设计书 §8.2）:
    事件 A 与事件 B 冲突，当且仅当：
      A.end_time + A.buffer_after > B.start_time - B.buffer_before
      且
      A.start_time - A.buffer_before < B.end_time + B.buffer_after

    参数:
      start_time: 新事件开始时间
      end_time: 新事件结束时间
      buffer_before: 新事件前缓冲（分钟）
      buffer_after: 新事件后缓冲（分钟）
      exclude_event_id: 排除的事件ID（用于更新场景排除自身）

    返回: 冲突事件列表
    """
    all_events = await self.repository.list_events(user_id=user_id)

    # 新事件的实际占用时间范围（含 buffer）
    new_effective_start = start_time - timedelta(minutes=buffer_before)
    new_effective_end = end_time + timedelta(minutes=buffer_after)

    conflicts = []
    for event in all_events:
        if exclude_event_id is not None and event.id == exclude_event_id:
            continue
        if event.start_time is None or event.end_time is None:
            continue

        # 已有事件的实际占用时间范围（含 buffer）
        existing_buffer_before = event.buffer_before or 0
        existing_buffer_after = event.buffer_after or 0
        existing_effective_start = event.start_time - timedelta(minutes=existing_buffer_before)
        existing_effective_end = event.end_time + timedelta(minutes=existing_buffer_after)

        # 判断是否重叠
        if new_effective_start < existing_effective_end and new_effective_end > existing_effective_start:
            conflicts.append(EventRead.model_validate(event))

    return conflicts
```

##### 步骤 2：在 `create_event` 和 `update_event` 中调用冲突检测

**文件**: `backend/app/services/events.py`

在 `create_event` 方法中，在 `self.repository.create_event()` 调用之前，插入冲突检测逻辑。但注意：**不阻止创建**，只记录冲突信息到变更日志。

在 `create_event` 方法的 `data = await self._enrich_event_payload(...)` 之后、`event = await self.repository.create_event(...)` 之前，添加：

```python
# 冲突检测
conflict_events = []
if data.get("start_time") and data.get("end_time"):
    start_dt = data["start_time"] if isinstance(data["start_time"], datetime) else datetime.fromisoformat(str(data["start_time"]))
    end_dt = data["end_time"] if isinstance(data["end_time"], datetime) else datetime.fromisoformat(str(data["end_time"]))
    conflict_events = await self.detect_conflicts(
        user_id=user_id,
        start_time=start_dt,
        end_time=end_dt,
        buffer_before=data.get("buffer_before") or 0,
        buffer_after=data.get("buffer_after") or 0,
    )
```

在变更日志中记录冲突信息：修改 `write_change_log` 调用的 `new_value_json`，增加 `conflicts` 字段：

```python
log_snapshot = self._event_snapshot(synced_event)
if conflict_events:
    log_snapshot["conflicts"] = [
        {"id": c.id, "title": c.title, "start_time": c.start_time.isoformat() if c.start_time else None, "end_time": c.end_time.isoformat() if c.end_time else None}
        for c in conflict_events
    ]
await self.repository.write_change_log(
    user_id=user_id,
    event_id=synced_event.id,
    change_type="created",
    new_value_json=log_snapshot,
    trigger_source="user",
)
```

##### 步骤 3：在 AssistantService 的 create_event action 中嵌入冲突检测并返回冲突 action

**文件**: `backend/app/services/assistant.py`

找到 `_execute_actions` 方法中处理 `create_event` 的分支。在成功创建事件后，调用冲突检测并生成 `conflict_warning` action：

在当前的 `create_event` 处理逻辑（搜索 `action_type == "create_event"` 的分支）之后，添加：

```python
# 冲突检测
if created_event.start_time and created_event.end_time:
    conflicts = await self.event_service.detect_conflicts(
        user_id=user_id,
        start_time=created_event.start_time,
        end_time=created_event.end_time,
        buffer_before=created_event.buffer_before or 0,
        buffer_after=created_event.buffer_after or 0,
        exclude_event_id=created_event.id,
    )
    if conflicts:
        actions.append(AssistantAction(
            type="conflict_warning",
            payload={
                "event_id": created_event.id,
                "event_title": created_event.title,
                "conflicts": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "start_time": c.start_time.isoformat() if c.start_time else None,
                        "end_time": c.end_time.isoformat() if c.end_time else None,
                    }
                    for c in conflicts
                ],
            },
        ))
```

##### 步骤 4：在 `_compute_gaps_for_date` 中扣除 buffer

**文件**: `backend/app/services/suggestions.py`

修改 `_compute_gaps_for_date` 方法，将事件的 `buffer_before` 和 `buffer_after` 纳入空档计算：

将当前的循环体：
```python
for event in day_events:
    if event.start_time > cursor:
        gaps.append((cursor, event.start_time))
    cursor = max(cursor, event.end_time)
```

替换为：
```python
for event in day_events:
    buffer_before = getattr(event, "buffer_before", None) or 0
    buffer_after = getattr(event, "buffer_after", None) or 0
    effective_start = event.start_time - timedelta(minutes=buffer_before)
    effective_end = event.end_time + timedelta(minutes=buffer_after)
    if effective_start > cursor:
        gaps.append((cursor, effective_start))
    cursor = max(cursor, effective_end)
```

##### 步骤 5：单元测试

**文件**: `backend/tests/test_conflict_detection.py`（新建）

```python
"""Tests for conflict detection with buffer support."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.events import EventService


class FakeEventRepository:
    """Minimal repository stub for conflict detection tests."""
    def __init__(self, events):
        self._events = events

    async def list_events(self, user_id: str, **kwargs):
        return self._events


@pytest.mark.asyncio
async def test_no_conflict_when_no_overlap():
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting A",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=0,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 12, 0),
        end_time=datetime(2026, 4, 1, 13, 0),
    )
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_conflict_when_overlap():
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting A",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=0,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 10, 30),
        end_time=datetime(2026, 4, 1, 11, 30),
    )
    assert len(conflicts) == 1
    assert conflicts[0].id == 1


@pytest.mark.asyncio
async def test_conflict_due_to_buffer():
    """Event A ends at 11:00 with buffer_after=15min, new event starts at 11:10 → conflict."""
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting A",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=15,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 11, 10),
        end_time=datetime(2026, 4, 1, 12, 0),
    )
    assert len(conflicts) == 1


@pytest.mark.asyncio
async def test_no_conflict_when_buffer_fits():
    """Event A ends at 11:00 with buffer_after=5min, new event starts at 11:10 → no conflict."""
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting A",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=5,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 11, 10),
        end_time=datetime(2026, 4, 1, 12, 0),
    )
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_conflict_due_to_new_event_buffer_before():
    """New event has buffer_before=20min, existing event ends at 10:45 → conflict."""
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting A",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 10, 45),
            buffer_before=0, buffer_after=0,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 11, 0),
        end_time=datetime(2026, 4, 1, 12, 0),
        buffer_before=20,
    )
    assert len(conflicts) == 1


@pytest.mark.asyncio
async def test_exclude_self_on_update():
    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=5, title="Self",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=0,
        ),
    ])
    conflicts = await service.detect_conflicts(
        user_id="test-user",
        start_time=datetime(2026, 4, 1, 10, 0),
        end_time=datetime(2026, 4, 1, 11, 0),
        exclude_event_id=5,
    )
    assert len(conflicts) == 0
```

**SuggestionService buffer 测试**，添加到 `backend/tests/test_suggestions_service.py`：

```python
def test_compute_gaps_deducts_buffer():
    """Gaps should account for buffer_before and buffer_after of events."""
    from datetime import date, datetime, timedelta
    from types import SimpleNamespace
    from app.services.suggestions import SuggestionService

    service = SuggestionService()
    events = [
        SimpleNamespace(
            start_time=datetime(2026, 3, 26, 10, 0),
            end_time=datetime(2026, 3, 26, 11, 0),
            buffer_before=10,
            buffer_after=15,
        ),
    ]
    profile = SimpleNamespace(wake_up_time="08:00", sleep_time="22:00")
    gaps = service._compute_gaps_for_date(
        events=events, profile=profile, target_date=date(2026, 3, 26),
    )
    # First gap: 08:00 → 09:50 (10:00 minus 10min buffer_before)
    assert gaps[0][0].hour == 8 and gaps[0][0].minute == 0
    assert gaps[0][1].hour == 9 and gaps[0][1].minute == 50
    # Second gap: 11:15 → 22:00 (11:00 plus 15min buffer_after)
    assert gaps[1][0].hour == 11 and gaps[1][0].minute == 15
    assert gaps[1][1].hour == 22
```

---

### P0-2: Celery Beat 高频提醒扫描

#### 目标

按设计书要求配置 4 种频率的 Celery Beat 定时任务，覆盖事件即将开始提醒、出发提醒、空档与待办风险扫描、冲突延误检查。

#### 涉及文件

1. `backend/app/core/celery_app.py` — 修改 `beat_schedule` 配置
2. `backend/app/jobs/reminders.py` — 新增 3 个扫描任务
3. `backend/tests/test_reminder_jobs.py` — 新增对应测试

#### 详细实现步骤

##### 步骤 1：修改 Celery Beat Schedule

**文件**: `backend/app/core/celery_app.py`

将 `beat_schedule` 替换为：

```python
celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        # 每 1 分钟：扫描近 30 分钟内即将开始的事件
        "scan-event-start-reminders": {
            "task": "app.jobs.reminders.scan_upcoming_reminders",
            "schedule": 60.0,
        },
        # 每 5 分钟：扫描近 2 小时内有出发时间的事件
        "scan-departure-reminders": {
            "task": "app.jobs.reminders.scan_departure_reminders",
            "schedule": 300.0,
        },
        # 每 15 分钟：扫描今日空档与待办风险
        "scan-idle-slot-suggestions": {
            "task": "app.jobs.reminders.scan_idle_slot_risks",
            "schedule": 900.0,
        },
        # 每 30 分钟：检查是否存在冲突或延误风险
        "scan-conflict-warnings": {
            "task": "app.jobs.reminders.scan_conflict_warnings",
            "schedule": 1800.0,
        },
    },
)
```

##### 步骤 2：拆分并新增 Celery 任务

**文件**: `backend/app/jobs/reminders.py`

保留现有 `scan_upcoming_reminders` 任务（改为仅处理 `event_start` 提醒），新增 3 个任务：

**任务 A: `scan_departure_reminders`（每5分钟）**

```python
@celery_app.task(name="app.jobs.reminders.scan_departure_reminders")
def scan_departure_reminders() -> dict[str, int]:
    """扫描近 2 小时内有出发时间的事件，生成 departure 提醒。"""
    return asyncio.run(_scan_departure_reminders())


async def _scan_departure_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=2)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        # 查找 departure_time 在 now ~ now+2h 范围内的事件
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.departure_time.is_not(None),
                    Event.departure_time >= now,
                    Event.departure_time <= window_end,
                )
            )
        ).all()

        generated_count = 0
        for event in upcoming_events:
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == event.user_id,
                    Reminder.target_type == "event",
                    Reminder.target_id == event.id,
                    Reminder.remind_type == "departure",
                )
            )
            if existing is not None:
                continue

            payload = _build_departure_reminder_payload(event=event, now=now)
            session.add(Reminder(user_id=event.user_id, **payload))
            generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}
```

**任务 B: `scan_idle_slot_risks`（每15分钟）**

```python
@celery_app.task(name="app.jobs.reminders.scan_idle_slot_risks")
def scan_idle_slot_risks() -> dict[str, int]:
    """扫描今日有截止但未安排足够时间的待办任务，生成 idle_slot_suggestion 提醒。"""
    return asyncio.run(_scan_idle_slot_risks())


async def _scan_idle_slot_risks() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        # 查找今日截止但状态未完成的任务
        at_risk_tasks = (
            await session.scalars(
                select(Task).where(
                    Task.deadline.is_not(None),
                    Task.deadline <= today_end,
                    Task.status.notin_(["done"]),
                )
            )
        ).all()

        generated_count = 0
        for task in at_risk_tasks:
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == task.user_id,
                    Reminder.target_type == "task",
                    Reminder.target_id == task.id,
                    Reminder.remind_type == "task_deadline",
                    Reminder.remind_at >= now - timedelta(hours=1),
                )
            )
            if existing is not None:
                continue

            session.add(
                Reminder(
                    user_id=task.user_id,
                    target_type="task",
                    target_id=task.id,
                    remind_type="task_deadline",
                    remind_at=now,
                    delivery_channel="in_app",
                    message=f"Task deadline approaching: {task.content} (due {task.deadline.strftime('%m-%d %H:%M') if task.deadline else 'soon'})",
                    status="pending",
                )
            )
            generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}
```

**任务 C: `scan_conflict_warnings`（每30分钟）**

```python
@celery_app.task(name="app.jobs.reminders.scan_conflict_warnings")
def scan_conflict_warnings() -> dict[str, int]:
    """扫描未来 24 小时事件之间是否存在冲突（含 buffer），生成 conflict_warning 提醒。"""
    return asyncio.run(_scan_conflict_warnings())


async def _scan_conflict_warnings() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.start_time.is_not(None),
                    Event.end_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= window_end,
                ).order_by(Event.start_time)
            )
        ).all()

        generated_count = 0
        for i, event_a in enumerate(upcoming_events):
            for event_b in upcoming_events[i + 1:]:
                # 检查 A 和 B 是否冲突（含 buffer）
                a_end_effective = event_a.end_time + timedelta(minutes=event_a.buffer_after or 0)
                b_start_effective = event_b.start_time - timedelta(minutes=event_b.buffer_before or 0)

                if a_end_effective > b_start_effective:
                    # 检查是否已有此冲突的提醒
                    existing = await session.scalar(
                        select(Reminder).where(
                            Reminder.user_id == event_a.user_id,
                            Reminder.target_type == "event",
                            Reminder.target_id == event_a.id,
                            Reminder.remind_type == "conflict_warning",
                            Reminder.remind_at >= now - timedelta(hours=6),
                        )
                    )
                    if existing is not None:
                        continue

                    session.add(
                        Reminder(
                            user_id=event_a.user_id,
                            target_type="event",
                            target_id=event_a.id,
                            remind_type="conflict_warning",
                            remind_at=now,
                            delivery_channel="in_app",
                            message=f"Schedule conflict: '{event_a.title}' and '{event_b.title}' overlap (including buffer time).",
                            status="pending",
                        )
                    )
                    generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}
```

需要在文件顶部增加 `Task` 模型的导入：
```python
from app.models import Event, Reminder, Task
```

##### 步骤 3：单元测试

**文件**: `backend/tests/test_reminder_jobs.py`（追加）

```python
"""Tests for multi-frequency reminder scanning jobs."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.jobs.reminders import (
    _scan_upcoming_reminders,
    _scan_departure_reminders,
    _scan_idle_slot_risks,
    _scan_conflict_warnings,
)


# 使用实际 SQLite 内存数据库或 mock session 来测试

def test_scan_upcoming_reminders_is_callable():
    """Sanity check: the task function exists and is decorated."""
    from app.jobs.reminders import scan_upcoming_reminders
    assert callable(scan_upcoming_reminders)


def test_scan_departure_reminders_is_callable():
    from app.jobs.reminders import scan_departure_reminders
    assert callable(scan_departure_reminders)


def test_scan_idle_slot_risks_is_callable():
    from app.jobs.reminders import scan_idle_slot_risks
    assert callable(scan_idle_slot_risks)


def test_scan_conflict_warnings_is_callable():
    from app.jobs.reminders import scan_conflict_warnings
    assert callable(scan_conflict_warnings)
```

---

### P0-3: 前端提醒弹窗 Toast 通知

#### 目标

当 WebSocket 推送的新提醒到达时，在页面内显示一个 Toast 弹窗（自动消失），同时保留现有的浏览器 Notification API。

#### 涉及文件

1. `frontend/src/components/ToastNotification.vue` — 新建 Toast 组件
2. `frontend/src/App.vue` — 集成 Toast 组件
3. `frontend/src/stores/workspace.ts` — 新增 toast 状态管理

#### 详细实现步骤

##### 步骤 1：新建 Toast 组件

**文件**: `frontend/src/components/ToastNotification.vue`（新建）

```vue
<script setup lang="ts">
import { ref, watch } from "vue";

export interface ToastItem {
  id: string;
  message: string;
  type: "info" | "warn" | "danger";
  createdAt: number;
}

const props = defineProps<{
  items: ToastItem[];
}>();

const emit = defineEmits<{
  dismiss: [id: string];
}>();

// 自动消失（5秒后）
watch(
  () => props.items,
  (newItems) => {
    for (const item of newItems) {
      setTimeout(() => emit("dismiss", item.id), 5000);
    }
  },
  { deep: true },
);
</script>

<template>
  <div class="fixed right-4 top-16 z-50 flex flex-col gap-2" style="max-width: 360px">
    <transition-group name="toast">
      <div
        v-for="item in items"
        :key="item.id"
        class="flex items-start gap-3 rounded-xl border bg-white px-4 py-3 shadow-lg transition-all duration-300"
        :class="{
          'border-accent/20': item.type === 'info',
          'border-warn/20': item.type === 'warn',
          'border-danger/20': item.type === 'danger',
        }"
      >
        <!-- Icon -->
        <div
          class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg"
          :class="{
            'bg-accent-light text-accent': item.type === 'info',
            'bg-warn-light text-warn': item.type === 'warn',
            'bg-danger-light text-danger': item.type === 'danger',
          }"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path
              v-if="item.type === 'danger'"
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
            />
            <path
              v-else-if="item.type === 'warn'"
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
            />
            <path
              v-else
              stroke-linecap="round"
              stroke-linejoin="round"
              d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
            />
          </svg>
        </div>

        <!-- Text -->
        <p class="flex-1 text-sm text-ink">{{ item.message }}</p>

        <!-- Close -->
        <button
          type="button"
          class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ink-3 transition hover:bg-surface-3 hover:text-ink"
          @click="emit('dismiss', item.id)"
        >
          <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.2s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
```

##### 步骤 2：在 workspace store 中增加 toast 状态

**文件**: `frontend/src/stores/workspace.ts`

在 `state` 中新增：

```typescript
toasts: [] as Array<{ id: string; message: string; type: "info" | "warn" | "danger"; createdAt: number }>,
```

在 `actions` 中新增：

```typescript
pushToast(message: string, type: "info" | "warn" | "danger" = "info") {
  this.toasts.push({
    id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    message,
    type,
    createdAt: Date.now(),
  });
  // 最多保留 5 条
  if (this.toasts.length > 5) {
    this.toasts = this.toasts.slice(-5);
  }
},
dismissToast(id: string) {
  this.toasts = this.toasts.filter((t) => t.id !== id);
},
```

修改 `connectNotifications` 中 `socket.onmessage` 的提醒处理部分，将 `this.notifyBrowser(...)` 调用替换为同时触发 Toast 和浏览器通知：

将：
```typescript
for (const reminder of payload.reminders) {
  if (!previousIds.has(reminder.id) && reminder.status !== "read") {
    this.notifyBrowser(reminder.message || reminder.remind_type);
  }
}
```

替换为：
```typescript
for (const reminder of payload.reminders) {
  if (!previousIds.has(reminder.id) && reminder.status !== "read") {
    const msg = reminder.message || reminder.remind_type;
    const toastType = reminder.remind_type === "conflict_warning" ? "danger"
      : reminder.remind_type === "departure" ? "warn"
      : "info";
    this.pushToast(msg, toastType);
    this.notifyBrowser(msg);
  }
}
```

##### 步骤 3：在 App.vue 中集成 Toast

**文件**: `frontend/src/App.vue`

1. 在 `<script setup>` 部分添加导入：
```typescript
import ToastNotification from "@/components/ToastNotification.vue";
```

2. 在模板中（`<div class="min-h-screen ...">` 的第一个子元素位置）添加：
```html
<ToastNotification
  :items="workspace.toasts"
  @dismiss="workspace.dismissToast"
/>
```

---

## 四、P1 — 功能完善

### P1-1: 后台主动任务跟进 Inbox 生成

#### 目标

创建一个独立的 Celery 任务，定期扫描有进展的任务（已完成部分专注块、有剩余时间），主动在 Inbox 中生成跟进条目。与当前依赖 AI 对话时写入的方式互补。

#### 涉及文件

1. `backend/app/jobs/inbox.py` — 新建，后台 Inbox 生成任务
2. `backend/app/core/celery_app.py` — 注册新任务
3. `backend/tests/test_inbox_job.py` — 单元测试

#### 详细实现步骤

##### 步骤 1：新建 Inbox 后台生成任务

**文件**: `backend/app/jobs/inbox.py`（新建）

```python
"""Background job for proactive inbox item generation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.models import Event, Reminder, Task


@celery_app.task(name="app.jobs.inbox.generate_proactive_inbox_items")
def generate_proactive_inbox_items() -> dict[str, int]:
    """Scan tasks with partial progress and generate follow-up reminders for inbox."""
    return asyncio.run(_generate_proactive_inbox_items())


async def _generate_proactive_inbox_items() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    session_factory = get_sessionmaker()
    generated_count = 0

    async with session_factory() as session:
        # 1. 查找所有未完成且有关联专注块的任务
        pending_tasks = (
            await session.scalars(
                select(Task).where(
                    Task.status.notin_(["done"]),
                )
            )
        ).all()

        for task in pending_tasks:
            # 查找该任务关联的所有专注块事件
            focus_blocks = (
                await session.scalars(
                    select(Event).where(
                        Event.linked_task_id == task.id,
                        Event.event_type == "focus_block",
                    )
                )
            ).all()

            if not focus_blocks:
                continue

            completed_blocks = [e for e in focus_blocks if e.status == "completed"]
            canceled_blocks = [e for e in focus_blocks if e.status == "canceled"]

            # 如果有取消的块且无最近的 replan 提醒
            if canceled_blocks:
                existing = await session.scalar(
                    select(Reminder).where(
                        Reminder.user_id == task.user_id,
                        Reminder.target_type == "task",
                        Reminder.target_id == task.id,
                        Reminder.remind_type == "task_replan",
                        Reminder.remind_at >= now - timedelta(hours=4),
                    )
                )
                if existing is None:
                    session.add(
                        Reminder(
                            user_id=task.user_id,
                            target_type="task",
                            target_id=task.id,
                            remind_type="task_replan",
                            remind_at=now,
                            delivery_channel="in_app",
                            message=f"Task '{task.content}' has {len(canceled_blocks)} canceled focus block(s). Consider replanning.",
                            status="pending",
                        )
                    )
                    generated_count += 1

            # 如果有已完成的块，生成进度更新
            if completed_blocks and not canceled_blocks:
                total_minutes = sum(
                    int((e.end_time - e.start_time).total_seconds() // 60)
                    for e in completed_blocks
                    if e.start_time and e.end_time
                )
                estimated = task.estimated_duration_minutes or 60
                if total_minutes < estimated:
                    existing = await session.scalar(
                        select(Reminder).where(
                            Reminder.user_id == task.user_id,
                            Reminder.target_type == "task",
                            Reminder.target_id == task.id,
                            Reminder.remind_type == "task_progress",
                            Reminder.remind_at >= now - timedelta(hours=4),
                        )
                    )
                    if existing is None:
                        session.add(
                            Reminder(
                                user_id=task.user_id,
                                target_type="task",
                                target_id=task.id,
                                remind_type="task_progress",
                                remind_at=now,
                                delivery_channel="in_app",
                                message=f"Task '{task.content}': {total_minutes}/{estimated} min completed. {estimated - total_minutes} min remaining.",
                                status="pending",
                            )
                        )
                        generated_count += 1

        if generated_count:
            await session.commit()

    return {"generated_count": generated_count}
```

##### 步骤 2：注册到 Celery Beat

**文件**: `backend/app/core/celery_app.py`

1. 在 `include` 列表中增加 `"app.jobs.inbox"`：
```python
include=["app.jobs.reminders", "app.jobs.inbox"],
```

2. 在 `beat_schedule` 中增加：
```python
"generate-proactive-inbox": {
    "task": "app.jobs.inbox.generate_proactive_inbox_items",
    "schedule": 600.0,  # 每 10 分钟
},
```

##### 步骤 3：单元测试

**文件**: `backend/tests/test_inbox_job.py`（新建）

```python
"""Tests for proactive inbox generation job."""
from __future__ import annotations

def test_generate_proactive_inbox_items_is_callable():
    from app.jobs.inbox import generate_proactive_inbox_items
    assert callable(generate_proactive_inbox_items)
```

---

### P1-2: 冲突时推荐替代时段

#### 目标

当检测到冲突时，自动推荐 1-3 个不冲突的替代时间段，作为 `suggest_reschedule` action 返回给前端。

#### 涉及文件

1. `backend/app/services/events.py` — 新增 `find_alternative_slots()` 方法
2. `backend/app/services/assistant.py` — 在冲突 action 中附加替代时段
3. `backend/app/api/schemas.py` — 无需改动（用现有 `AssistantAction` payload）
4. `frontend/src/components/AssistantPanel.vue` — 展示替代时段卡片
5. `backend/tests/test_conflict_detection.py` — 追加替代时段测试

#### 详细实现步骤

##### 步骤 1：在 `EventService` 新增 `find_alternative_slots()`

**文件**: `backend/app/services/events.py`

```python
async def find_alternative_slots(
    self,
    user_id: str,
    duration_minutes: int,
    preferred_date: date | None = None,
    buffer_before: int = 0,
    buffer_after: int = 0,
    max_results: int = 3,
) -> list[dict]:
    """
    在给定日期的空闲时段中找到可用的替代时间段。

    返回格式: [{"start_time": datetime, "end_time": datetime}, ...]
    """
    from app.services.suggestions import SuggestionService
    suggestion_service = SuggestionService()

    target_dates = []
    if preferred_date:
        target_dates.append(preferred_date)
    else:
        today = datetime.now().date()
        target_dates = [today, today + timedelta(days=1), today + timedelta(days=2)]

    profile = await self.profile_repository.get_profile(user_id)
    events = await self.repository.list_events(user_id=user_id)

    alternatives = []
    total_needed = duration_minutes + buffer_before + buffer_after

    for target_date in target_dates:
        gaps = suggestion_service._compute_gaps_for_date(
            events=events, profile=profile, target_date=target_date,
        )
        for gap_start, gap_end in gaps:
            gap_minutes = int((gap_end - gap_start).total_seconds() // 60)
            if gap_minutes >= total_needed:
                slot_start = gap_start + timedelta(minutes=buffer_before)
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                alternatives.append({
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat(),
                })
                if len(alternatives) >= max_results:
                    return alternatives

    return alternatives
```

需要在文件顶部添加 `from datetime import date` 导入。

##### 步骤 2：在 AssistantService 冲突检测后追加替代时段

**文件**: `backend/app/services/assistant.py`

在 P0-1 添加的冲突检测代码之后（`conflict_warning` action 部分），继续添加：

```python
if conflicts:
    # 推荐替代时段
    duration = int((created_event.end_time - created_event.start_time).total_seconds() // 60)
    alternatives = await self.event_service.find_alternative_slots(
        user_id=user_id,
        duration_minutes=duration,
        preferred_date=created_event.start_time.date(),
        buffer_before=created_event.buffer_before or 0,
        buffer_after=created_event.buffer_after or 0,
    )
    if alternatives:
        actions.append(AssistantAction(
            type="suggest_reschedule",
            payload={
                "event_id": created_event.id,
                "event_title": created_event.title,
                "alternatives": alternatives,
            },
        ))
```

##### 步骤 3：前端展示替代时段卡片

**文件**: `frontend/src/components/AssistantPanel.vue`

在模板中的 action 卡片渲染区域，为 `suggest_reschedule` 类型添加展示卡片。找到处理 `lastAssistantActions` 的 `v-for` 循环，在现有 action 类型判断后增加：

```html
<!-- Suggest Reschedule card -->
<div v-else-if="action.type === 'suggest_reschedule'" class="ml-8 rounded-lg border border-accent/20 bg-accent-light p-3">
  <p class="text-xs font-semibold text-accent">Alternative Times for "{{ action.payload.event_title }}"</p>
  <div class="mt-2 space-y-1.5">
    <div
      v-for="(alt, idx) in (action.payload.alternatives as Array<{start_time: string; end_time: string}>)"
      :key="idx"
      class="flex items-center justify-between rounded-md border border-border bg-white px-3 py-2"
    >
      <span class="text-xs text-ink">
        {{ new Date(alt.start_time).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) }}
        –
        {{ new Date(alt.end_time).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" }) }}
      </span>
      <button
        type="button"
        class="rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-accent-hover"
        @click="emit('send', `把事件「${action.payload.event_title}」改到 ${alt.start_time} 到 ${alt.end_time}`)"
      >
        Use
      </button>
    </div>
  </div>
</div>
```

##### 步骤 4：单元测试

追加到 `backend/tests/test_conflict_detection.py`：

```python
@pytest.mark.asyncio
async def test_find_alternative_slots_returns_non_conflicting():
    from app.services.suggestions import SuggestionService
    from types import SimpleNamespace
    from datetime import date

    service = EventService()
    service.repository = FakeEventRepository([
        SimpleNamespace(
            id=1, title="Meeting",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 11, 0),
            buffer_before=0, buffer_after=0,
        ),
        SimpleNamespace(
            id=2, title="Lunch",
            start_time=datetime(2026, 4, 1, 12, 0),
            end_time=datetime(2026, 4, 1, 13, 0),
            buffer_before=0, buffer_after=0,
        ),
    ])
    service.profile_repository = type("FakeProfileRepo", (), {
        "get_profile": staticmethod(lambda uid: SimpleNamespace(
            wake_up_time="08:00", sleep_time="22:00",
            home_location_coords=None, work_location_coords=None,
        ))
    })()

    alternatives = await service.find_alternative_slots(
        user_id="test-user",
        duration_minutes=60,
        preferred_date=date(2026, 4, 1),
    )
    assert len(alternatives) > 0
    # 第一个替代时段不应与 10:00-11:00 或 12:00-13:00 重叠
    alt_start = datetime.fromisoformat(alternatives[0]["start_time"])
    assert alt_start.hour < 10 or alt_start.hour >= 11
```

---

### P1-3: WebSocket 流式输出 AI 回复

#### 目标

新增 `/ws/assistant` WebSocket 端点，支持助手回复以 token 流的方式推送到前端，提升交互体验。

#### 涉及文件

1. `backend/app/tools/gemini.py` — 新增 `generate_plan_stream()` 流式方法
2. `backend/app/services/assistant.py` — 新增 `send_message_stream()` 方法
3. `backend/app/api/ws.py` — 新增 `/ws/assistant` 端点
4. `frontend/src/stores/workspace.ts` — 新增流式发送方法
5. `frontend/src/components/AssistantPanel.vue` — 支持逐字渲染

#### 详细实现步骤

##### 步骤 1：GeminiClient 新增流式生成方法

**文件**: `backend/app/tools/gemini.py`

新增异步生成器方法：

```python
async def generate_plan_stream(
    self,
    *,
    user_message: str,
    history: list[dict[str, Any]],
    events: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
    external_context: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream text chunks from Gemini API."""
    if not self.enabled:
        raise RuntimeError("Gemini is not configured.")

    prompt = self._build_plan_prompt(
        user_message=user_message,
        history=history,
        events=events,
        tasks=tasks,
        profile=profile,
        external_context=external_context,
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"{self.settings.gemini_model}:streamGenerateContent"
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            url,
            params={"key": self.settings.gemini_api_key, "alt": "sse"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    candidates = chunk.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                except (json.JSONDecodeError, KeyError):
                    continue
```

需要在文件顶部添加 `from typing import AsyncIterator` 和 `from collections.abc import AsyncIterator`。

##### 步骤 2：AssistantService 新增流式发送方法

**文件**: `backend/app/services/assistant.py`

新增方法：

```python
async def send_message_stream(self, user_id: str, payload: AssistantMessageCreate):
    """
    流式版本的 send_message。
    yield 类型为 dict:
      {"type": "token", "text": "..."}
      {"type": "actions", "actions": [...]}
      {"type": "done", "session_id": int, "full_reply": str}
    """
    if payload.session_id is None:
        current = await self.get_current_session(user_id=user_id)
        session = await self.repository.get_session(current.session.id, user_id=user_id)
    else:
        session = await self.repository.get_session(payload.session_id, user_id=user_id)

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    await self.repository.create_message(session_id=session.id, role="user", content=payload.message)
    history = await self.repository.list_messages(session.id)
    events = await self.event_repository.list_events(user_id=user_id)
    profile = await self.profile_repository.get_profile(user_id)
    tasks = await self.task_service.list_tasks(user_id=user_id)
    external_context = await self._build_external_context(profile=profile)

    full_reply = ""
    async for chunk in self.gemini.generate_plan_stream(
        user_message=payload.message,
        history=[{"role": m.role, "content": m.content} for m in history[-6:]],
        events=[EventRead.model_validate(e).model_dump(mode="json") for e in events[:8]],
        tasks=[t.model_dump(mode="json") if hasattr(t, "model_dump") else {} for t in tasks[:8]],
        profile=profile.__dict__ if profile else None,
        external_context=external_context,
    ):
        full_reply += chunk
        yield {"type": "token", "text": chunk}

    # 尝试解析 JSON actions
    try:
        plan = self.gemini._parse_json_payload(full_reply)
        reply_text = plan.get("reply", full_reply)
        requested_actions = plan.get("actions", [])
        actions = await self._execute_actions(
            user_id=user_id,
            actions=requested_actions,
            user_message=payload.message,
            existing_events=events,
            profile=profile,
        )
        yield {"type": "actions", "actions": [a.model_dump() for a in actions]}
    except Exception:
        reply_text = full_reply
        actions = []

    await self.repository.create_message(
        session_id=session.id,
        role="assistant",
        content=reply_text,
        tool_calls_json=[a.model_dump() for a in actions] or None,
    )

    yield {"type": "done", "session_id": session.id, "full_reply": reply_text}
```

##### 步骤 3：新增 WebSocket 端点

**文件**: `backend/app/api/ws.py`

新增：

```python
@router.websocket("/ws/assistant")
async def assistant_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming assistant replies."""
    await websocket.accept()
    user_id = websocket.query_params.get("user_id", "local-user")
    assistant_service = AssistantService()

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id")

            if not message.strip():
                await websocket.send_json({"type": "error", "text": "Empty message"})
                continue

            from app.api.schemas import AssistantMessageCreate
            payload = AssistantMessageCreate(session_id=session_id, message=message)

            async for chunk in assistant_service.send_message_stream(user_id, payload):
                await websocket.send_json(chunk)

    except WebSocketDisconnect:
        return
```

##### 步骤 4：前端流式接收

**文件**: `frontend/src/stores/workspace.ts`

新增 action：

```typescript
async sendAssistantMessageStream(message: string) {
  if (!message.trim()) return;
  this.sending = true;
  this.messages.push({
    id: `local-${Date.now()}`,
    role: "user",
    content: message,
  });

  // 添加一个空的 assistant 消息，逐步填充
  const assistantMsgId = `assistant-stream-${Date.now()}`;
  this.messages.push({
    id: assistantMsgId,
    role: "assistant",
    content: "",
  });

  const ws = new WebSocket("ws://127.0.0.1:8000/ws/assistant?user_id=local-user");

  ws.onopen = () => {
    ws.send(JSON.stringify({ message, session_id: this.sessionId }));
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "token") {
      const msg = this.messages.find((m) => m.id === assistantMsgId);
      if (msg) msg.content += data.text;
    } else if (data.type === "actions") {
      this.lastAssistantActions = data.actions;
    } else if (data.type === "done") {
      this.sessionId = data.session_id;
      const msg = this.messages.find((m) => m.id === assistantMsgId);
      if (msg) msg.content = data.full_reply;
      ws.close();
      this.sending = false;
      // Refresh data
      Promise.all([
        this.fetchEvents(),
        this.fetchTasks(),
        this.fetchReminders(),
        this.fetchSuggestions(),
        this.fetchAssistantInbox(),
        this.fetchAssistantSummary(),
      ]);
    } else if (data.type === "error") {
      ws.close();
      this.sending = false;
    }
  };

  ws.onerror = () => {
    // fallback to REST
    ws.close();
    this.messages.pop(); // remove empty assistant message
    this.messages.pop(); // remove user message
    this.sending = false;
    this.sendAssistantMessage(message); // fallback
  };
},
```

##### 步骤 5：前端切换使用流式发送

**文件**: `frontend/src/App.vue`

修改 `sendAndFocusAssistant` 函数，优先使用流式发送：

```typescript
async function sendAndFocusAssistant(message: string) {
  mobileTab.value = "assistant";
  await workspace.sendAssistantMessageStream(message);
}
```

同时修改桌面端 `AssistantPanel` 的 `@send` 事件处理，使 workspace store 的 `sendAssistantMessage` 替换为 `sendAssistantMessageStream`。可通过在 workspace store 中修改 `sendAssistantMessage` 为优先尝试流式，失败后 fallback 到 REST：

将 `sendAssistantMessage` 的开头改为：
```typescript
async sendAssistantMessage(message: string) {
  // 尝试流式，如果 WebSocket 不可用则降级到 REST
  try {
    await this.sendAssistantMessageStream(message);
    return;
  } catch {
    // 降级到 REST
  }
  // ... 原有 REST 逻辑 ...
```

---

## 五、P2 — 插件接口预留

### P2-1: 语音输入/输出适配器接口

#### 目标

按设计书 §11.1 要求，预留 `InputAdapter` / `OutputAdapter` / `ContextProvider` / `NotificationProvider` 接口。

#### 涉及文件

1. `backend/app/adapters/__init__.py` — 新建
2. `backend/app/adapters/input_adapter.py` — 输入适配器基类 + 文本实现
3. `backend/app/adapters/output_adapter.py` — 输出适配器基类 + 文本实现
4. `frontend/src/inputAdapters/textInput.ts` — 文本输入适配器
5. `frontend/src/outputAdapters/textOutput.ts` — 文本输出适配器
6. `backend/tests/test_adapters.py` — 单元测试

#### 详细实现步骤

##### 步骤 1：后端适配器接口

**文件**: `backend/app/adapters/__init__.py`（新建）

```python
"""Adapter interfaces for pluggable input/output."""
```

**文件**: `backend/app/adapters/input_adapter.py`（新建）

```python
"""Input adapter interface and text implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InputAdapter(ABC):
    """Base class for input adapters (text, voice, etc.)."""

    @abstractmethod
    async def parse(self, payload: Any) -> dict[str, Any]:
        """
        Parse raw input into a normalized message dict.

        Returns:
            {"message": str, "metadata": dict}
        """
        ...


class TextInputAdapter(InputAdapter):
    """Default text input adapter — passes through the message as-is."""

    async def parse(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, str):
            return {"message": payload, "metadata": {"source": "text"}}
        if isinstance(payload, dict):
            return {
                "message": payload.get("message", ""),
                "metadata": {"source": "text", **payload.get("metadata", {})},
            }
        return {"message": str(payload), "metadata": {"source": "text"}}


class VoiceInputAdapter(InputAdapter):
    """Placeholder for future voice input adapter."""

    async def parse(self, payload: Any) -> dict[str, Any]:
        # Future: accept audio bytes, call STT service, return transcript
        raise NotImplementedError(
            "Voice input adapter is not yet implemented. "
            "Set VOICE_INPUT_ENABLED=true and provide an STT service configuration."
        )
```

**文件**: `backend/app/adapters/output_adapter.py`（新建）

```python
"""Output adapter interface and text implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OutputAdapter(ABC):
    """Base class for output adapters (text, voice, etc.)."""

    @abstractmethod
    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Render assistant response into the target format.

        Returns:
            {"content": str_or_bytes, "content_type": str, "metadata": dict}
        """
        ...


class TextOutputAdapter(OutputAdapter):
    """Default text output adapter — returns the message as-is."""

    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "content": message,
            "content_type": "text/plain",
            "metadata": {"source": "text", **(metadata or {})},
        }


class VoiceOutputAdapter(OutputAdapter):
    """Placeholder for future voice output adapter."""

    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        # Future: call TTS service, return audio bytes
        raise NotImplementedError(
            "Voice output adapter is not yet implemented. "
            "Set VOICE_OUTPUT_ENABLED=true and provide a TTS service configuration."
        )
```

##### 步骤 2：前端适配器接口

**文件**: `frontend/src/inputAdapters/textInput.ts`（新建）

```typescript
/**
 * Text input adapter — default implementation.
 * Future voice adapter can implement the same interface.
 */
export interface InputAdapter {
  /** Parse raw input into a message string */
  parse(input: unknown): Promise<string>;
  /** Whether this adapter is currently available */
  isAvailable(): boolean;
}

export class TextInputAdapter implements InputAdapter {
  async parse(input: unknown): Promise<string> {
    if (typeof input === "string") return input;
    return String(input);
  }

  isAvailable(): boolean {
    return true;
  }
}

export const defaultInputAdapter = new TextInputAdapter();
```

**文件**: `frontend/src/outputAdapters/textOutput.ts`（新建）

```typescript
/**
 * Text output adapter — default implementation.
 * Future voice adapter can implement the same interface.
 */
export interface OutputAdapter {
  /** Render assistant response for display */
  render(message: string): Promise<string>;
  /** Whether this adapter is currently available */
  isAvailable(): boolean;
}

export class TextOutputAdapter implements OutputAdapter {
  async render(message: string): Promise<string> {
    return message;
  }

  isAvailable(): boolean {
    return true;
  }
}

export const defaultOutputAdapter = new TextOutputAdapter();
```

##### 步骤 3：单元测试

**文件**: `backend/tests/test_adapters.py`（新建）

```python
"""Tests for input/output adapters."""
from __future__ import annotations

import pytest

from app.adapters.input_adapter import TextInputAdapter, VoiceInputAdapter
from app.adapters.output_adapter import TextOutputAdapter, VoiceOutputAdapter


@pytest.mark.asyncio
async def test_text_input_adapter_parses_string():
    adapter = TextInputAdapter()
    result = await adapter.parse("Hello world")
    assert result["message"] == "Hello world"
    assert result["metadata"]["source"] == "text"


@pytest.mark.asyncio
async def test_text_input_adapter_parses_dict():
    adapter = TextInputAdapter()
    result = await adapter.parse({"message": "hi", "metadata": {"lang": "zh"}})
    assert result["message"] == "hi"
    assert result["metadata"]["lang"] == "zh"


@pytest.mark.asyncio
async def test_text_output_adapter_renders():
    adapter = TextOutputAdapter()
    result = await adapter.render("Your meeting is at 3pm.")
    assert result["content"] == "Your meeting is at 3pm."
    assert result["content_type"] == "text/plain"


@pytest.mark.asyncio
async def test_voice_input_adapter_not_implemented():
    adapter = VoiceInputAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.parse(b"audio-bytes")


@pytest.mark.asyncio
async def test_voice_output_adapter_not_implemented():
    adapter = VoiceOutputAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.render("hello")
```

---

## 六、单元测试规范

### 测试文件命名

| 功能模块 | 测试文件 |
|---|---|
| 冲突检测 | `backend/tests/test_conflict_detection.py` |
| 提醒扫描任务 | `backend/tests/test_reminder_jobs.py`（追加） |
| Inbox 后台生成 | `backend/tests/test_inbox_job.py` |
| 适配器接口 | `backend/tests/test_adapters.py` |
| 建议引擎 buffer | `backend/tests/test_suggestions_service.py`（追加） |

### 测试运行命令

在 Docker 容器中或本地安装好依赖后：

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

### 测试依赖

- `pytest`（已在项目中）
- `pytest-asyncio`（需确认是否安装，如未安装需 `pip install pytest-asyncio`）

### Mock 策略

- Repository 层：使用 `FakeRepository` 类替换，避免依赖真实数据库
- 外部 API（Gemini、高德、和风天气）：使用 `unittest.mock.AsyncMock` 或直接传入假数据
- Celery 任务：仅测试底层 async 函数（`_scan_xxx`），不测试 Celery 装饰器

---

## 七、整体测试验证清单

### 后端验证

| # | 验证项 | 验证方法 |
|---|---|---|
| 1 | 冲突检测含 buffer | 运行 `pytest tests/test_conflict_detection.py -v` |
| 2 | 空档计算含 buffer | 运行 `pytest tests/test_suggestions_service.py -v` |
| 3 | 4 种 Celery Beat 任务注册 | 检查 `celery_app.conf.beat_schedule` 包含 4 个条目 |
| 4 | 后台 Inbox 生成任务 | 运行 `pytest tests/test_inbox_job.py -v` |
| 5 | 适配器接口 | 运行 `pytest tests/test_adapters.py -v` |
| 6 | Docker 容器启动 | `docker compose up -d` 后检查 4 个容器健康 |
| 7 | API 健康检查 | `curl http://127.0.0.1:8000/api/health` 返回 `{"status": "ok"}` |

### 前端验证

| # | 验证项 | 验证方法 |
|---|---|---|
| 1 | Toast 组件渲染 | 打开浏览器，WebSocket 推送提醒时出现右上角 Toast |
| 2 | Toast 5秒自动消失 | 等待 5 秒后 Toast 淡出 |
| 3 | Toast 手动关闭 | 点击 × 按钮 Toast 立即消失 |
| 4 | 冲突提醒显示红色 Toast | 创建冲突事件时，Toast 显示红色边框 |
| 5 | 替代时段卡片 | AI 检测到冲突后，对话中出现替代时段卡片 |
| 6 | 替代时段 Use 按钮 | 点击 Use 按钮后向 AI 发送改时间的消息 |
| 7 | 流式输出（如已实现） | AI 回复逐字出现而非等待全部完成 |

### 端到端验证

| # | 验证场景 | 步骤 |
|---|---|---|
| 1 | 创建冲突事件 | 创建 10:00-11:00 事件 A → 再创建 10:30-11:30 事件 B → 期望：AI 返回 conflict_warning action + suggest_reschedule action |
| 2 | 带 buffer 冲突 | 创建 10:00-11:00 事件（buffer_after=30min）→ 再创建 11:15-12:00 事件 → 期望：检测到冲突 |
| 3 | Toast 提醒 | 创建 30 分钟内开始的事件 → 等待 Celery 扫描 → 期望：页面出现 Toast 弹窗 |
| 4 | 出发提醒 | 创建含地点的事件（2小时内出发）→ 等待 5 分钟 → 期望：departure 提醒出现 |
| 5 | 任务截止风险 | 创建今日截止的任务 → 等待 15 分钟 → 期望：task_deadline 提醒出现 |
| 6 | Inbox 后台生成 | 创建任务 → 创建关联专注块并标记 canceled → 等待 10 分钟 → 期望：Inbox 出现 replan 条目 |

---

## 附录：文件修改清单

### 新建文件

| 文件路径 | 用途 |
|---|---|
| `backend/app/jobs/inbox.py` | 后台主动 Inbox 生成任务 |
| `backend/app/adapters/__init__.py` | 适配器包 |
| `backend/app/adapters/input_adapter.py` | 输入适配器接口 |
| `backend/app/adapters/output_adapter.py` | 输出适配器接口 |
| `backend/tests/test_conflict_detection.py` | 冲突检测测试 |
| `backend/tests/test_inbox_job.py` | Inbox 后台任务测试 |
| `backend/tests/test_adapters.py` | 适配器测试 |
| `frontend/src/components/ToastNotification.vue` | Toast 弹窗组件 |
| `frontend/src/inputAdapters/textInput.ts` | 前端文本输入适配器 |
| `frontend/src/outputAdapters/textOutput.ts` | 前端文本输出适配器 |

### 修改文件

| 文件路径 | 修改内容 |
|---|---|
| `backend/app/services/events.py` | 新增 `detect_conflicts()` + `find_alternative_slots()` |
| `backend/app/services/suggestions.py` | `_compute_gaps_for_date()` 增加 buffer 扣除 |
| `backend/app/services/assistant.py` | create_event 后调用冲突检测 + 替代时段 + 流式方法 |
| `backend/app/core/celery_app.py` | 4 种频率 beat_schedule + 注册 inbox 任务 |
| `backend/app/jobs/reminders.py` | 新增 3 个扫描任务 + Task 模型导入 |
| `backend/app/tools/gemini.py` | 新增 `generate_plan_stream()` 流式方法 |
| `backend/app/api/ws.py` | 新增 `/ws/assistant` 端点 |
| `frontend/src/stores/workspace.ts` | Toast 状态 + 流式发送 + 提醒 Toast 触发 |
| `frontend/src/App.vue` | 集成 ToastNotification 组件 |
| `frontend/src/components/AssistantPanel.vue` | 替代时段卡片渲染 |
| `backend/tests/test_suggestions_service.py` | 追加 buffer 测试 |
| `backend/tests/test_reminder_jobs.py` | 追加新任务可调用性测试 |
