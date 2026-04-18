# 当前实现状态审计

**审计日期**: 2026-04-18  
**审计范围**: 当前工作区代码、`IMPLEMENTATION_PLAN_V6.md`、`IMPLEMENTATION_PLAN_V7.md`、`docs/README.md`

## 结论

当前项目已经完成 **V7 主基线切换**。

这意味着：

- 当前版本应认定为 **V7**
- 已不再适合标记为“V6 在建”
- 当前剩余工作主要是 **收口与清债**，而不是“版本尚未切换”

推荐版本表述：

> **“V7 当前基线已落地”**

## 核心依据

### 1. V7 主入口已经接管

以下能力已经进入主链路：

- `AssistantService.send_message()` 已优先走 workflow
- `AssistantService.send_message_stream()` 已优先走 workflow
- workflow 不再是旁路目录，而是当前编排壳
- LangGraph 可用时走图编排
- LangGraph 不可用时走 `run_sequential()` 降级

### 2. V7 核心体验已落地

- 助手 WebSocket 流式输出已接入
  - 后端存在 `/ws/assistant`
  - 前端 `assistant.ts` 已优先使用流式发送
- 条件化外部上下文判断已接入
  - `AssistantService._needs_external_context()`
- 事件级天气/通勤并行获取已接入
  - `AssistantService._build_event_specific_context()`
- 地图与天气工具超时优化已接入
  - Amap / QWeather 已降到 `8s`

### 3. V6 能力已被当前基线吸纳

以下 V6 能力现在已经并入当前基线，而不是继续悬空：

- 前端 Store 拆分
  - `assistant.ts`
  - `events.ts`
  - `reminder.ts`
  - `suggestion.ts`
  - `profile.ts`
  - `context.ts`
  - `googleCalendar.ts`
  - `system.ts`
  - `workspace.ts` 已退化为兼容 facade
- 任务拆分接口已接入 API
  - `GET /api/tasks/{task_id}/split-suggestions`
- 向量库、习惯学习、槽位补全、扫描线冲突检测、任务拆分等 V6 能力已进入代码库并完成测试基线接通

### 4. 验证结果已经对齐

本轮可确认结果：

- `frontend` 构建通过
- `backend/.venv312` 下全量测试通过
  - **280 passed**
- `alembic upgrade head` 已在临时 SQLite 数据库上验证通过
- workflow 测试、assistant 测试、API 测试均已通过
- workflow debug 接口已接入
  - `/api/debug/workflow/summary`
  - `/api/debug/workflow/diagram`

## 当前状态判断

### 应判定为 V7 的原因

- workflow 已接管助手主入口
- ReAct 子图已保留为复杂场景分支
- 条件化上下文、流式回复、超时优化已经进入当前实现
- 后端测试已形成可复现的稳定结果

### 不再适合判定为 V6 的原因

- “V6 在建”的核心判断前提，是 workflow 尚未接管主流程
- 该前提现在已经被消除

## 当前仍需继续收口的事项

### 1. 数据层收口

- `Habit` / `TaskSplit` 的核心迁移定义已与 ORM 对齐，并已完成一次实际迁移验证
- 后续仍建议继续审视历史数据库与增量升级路径

### 2. 向量依赖说明

- 当前已对 `chromadb` / `google.genai` 缺失场景做可选依赖降级
- 若要启用完整向量能力，仍需补齐安装与运行说明

### 3. 主助手体量仍偏大

- `AssistantService` 已不再独占编排职责
- 但 runtime helper 仍偏多，后续应继续抽薄

### 4. 小型技术债

- 当前剩余弃用警告主要来自测试代码中的 `utcnow()`

## 推荐对外表述

如果要在论文、答辩或项目汇报中描述当前状态，建议使用：

> 当前项目已完成 **V7 主基线切换**：助手入口由 workflow 编排驱动，复杂场景保留 ReAct 子图分支，系统已具备稳定的测试基线；后续工作主要集中在迁移收口、可选依赖安装与架构瘦身。

## 下一步建议

1. 收口数据库迁移与 ORM 差异。
2. 为完整向量能力补齐依赖安装说明。
3. 继续把 `AssistantService` 内的 runtime helper 抽离到 workflow/runtime 层。
