# AI 助手重设计实施任务书 V1

## 计划元数据

- Plan ID: `ai-assistant-implementation-v1`
- Version: `v1`
- Last updated: `2026-05-09 02:19 +08:00`
- Canonical progress file: `E:\GraduationProject\docs\development\AI_ASSISTANT_IMPLEMENTATION_TASK_BOOK_V1.md`
- Related handoff file: `E:\GraduationProject\docs\development\AI_ASSISTANT_SESSION_HANDOFF_2026-05-07.md`
- Source design file: `E:\GraduationProject\docs\development\AI_ASSISTANT_REDESIGN_PLAN_V1.md`
- Current branch: `master`
- Current active phase: `Phase 9 - Model-Driven Orchestration Refactor`
- Execution readiness: `implementation in progress`

## 目标

将 `AI_ASSISTANT_REDESIGN_PLAN_V1.md` 中已经收口的“多智能体、proposal 优先、确认后执行、可主动跟进”的 AI 助手设计，翻译成可持续执行的工程路线图。该任务书要明确开发顺序、数据库迁移顺序、接口落地顺序、前端接入顺序和验证顺序，使后续会话可以按阶段推进实现，而不需要重新解释设计意图。

最终目标不是一次性把 Phase 1A/1B/2/3 全部写完，而是用可回滚、可验证、可分阶段启用的方式，把现有被动 Chatbot 链路逐步升级为：

```text
用户输入 / 主动信号
  -> Conductor
  -> Specialist Registry
  -> Proposal Manager
  -> 用户确认
  -> Action Executor
  -> Events / Tasks / Reminders / Memory
```

## 范围与约束

- In scope:
  - 新建 proposal / signal / thread state 的数据库与 repository 基础。
  - 记忆候选表 `AssistantMemoryUpdateCandidate` 默认延后到长期记忆阶段；若实现时确认成本很低，可随基础迁移一起建表，但不得阻塞 Phase 1A。
  - 新建 `Conductor + Specialist Registry + Action Executor` 的后端骨架。
  - 建立被动 proposal 闭环：理解、澄清、生成 proposal、确认、执行、失败重试。
  - 为前端助手面板接入纯文本 proposal 与待确认事项提供最小状态接口。
  - 在后续阶段接入主动 heartbeat、deadline/conflict/departure signal、睡前复盘、晨间汇报和 `.md` 长期记忆。
  - 为每个阶段定义可执行验证，尤其是“不确认不落库”和“重复确认不重复执行”。
- Out of scope:
  - Phase 1A 不实现完整主动心跳。
  - Phase 1A 不实现完整长期记忆写入闭环。
  - Phase 1A 不引入完整 recurrence engine。
  - Phase 1A 不新增独立 `AssistantActionExecution` 表。
  - Phase 1A 不要求替换所有旧 workflow / LangGraph 能力。
  - Phase 1A 不做复杂按钮式 UI，仍以文本协议和最小辅助展示为主。
- Constraints:
  - 保留现有 `/api/assistant/message`、`/ws/assistant`、`/api/assistant/current`、`/api/assistant/sessions` 等兼容入口。
  - 所有任务、日程、完成状态、取消、延期、重排等写操作必须经过用户确认。
  - `AssistantProposal.status` 是业务可执行性的唯一状态来源；`AssistantThreadState.status` 只能作为上下文状态。
  - `payload_json.execution` 承载 Phase 1A 执行快照；不在 V1 强制建独立执行表。
  - 数据库当前是 SQLite + async SQLAlchemy + Alembic，迁移要避免过度依赖复杂 partial unique 约束，必要去重放在 service 层。
  - 当前 worktree 已有多处改动与 untracked 文件，实施时不得回滚非本任务改动。

## 阶段依赖与门禁

| 阶段 | 必须依赖 | 进入条件 | 退出条件 |
|---|---|---|---|
| Phase 0 | 已收口设计稿 | 用户确认进入实施准备 | 基线验证结果已记录，功能开关策略已明确 |
| Phase 1 | Phase 0 | Alembic head 明确，旧链路基线已记录 | 三张核心表、repository、schema 可用，迁移可回滚 |
| Phase 2 | Phase 1 | proposal 表和 repository 可用 | Proposal Manager 状态机和 API 合约可用，confirm 不真实落库 |
| Phase 3 | Phase 2 | Proposal Manager 可创建/更新 proposal | Conductor 可 shadow 运行，旧助手输出不被破坏 |
| Phase 4 | Phase 3 | Conductor 能稳定产生 proposal 或 clarification | Action Executor 可确认后写入，并通过幂等验证 |
| Phase 5 | Phase 4 | 可执行 proposal mode 已可用 | 前端能展示 pending proposal 并支持文本确认 |
| Phase 6 | Phase 5 | 被动闭环端到端可用 | dedup / revise / expiry / debug 可观测 |
| Phase 7 | Phase 6 | 被动闭环稳定，失败可恢复 | 主动 signal 受 cooldown + dedup 管控，不绕过确认 |
| Phase 8 | Phase 6 或 Phase 7 | proposal 基础稳定，Memory Specialist 边界明确 | `.md` 长期记忆可控读写，候选更新可确认/拒绝 |
| Phase 9 | Phase 8 | Phase 8 收口完成；系统进入架构级复审 | 主控默认走模型主导语义编排；旧规则链路降级为 fallback；任务 continuation / task schedule plan 成为一等 proposal 能力 |

### Go / No-Go 规则

- 任一阶段若破坏旧 `/api/assistant/message` 或 `/ws/assistant` 基础可用性，不进入下一阶段。
- 任一阶段若出现“未确认就写入任务/日程/状态”，立即停止推进并修正。
- Phase 3 只能默认进入 `shadow`，不得直接让用户侧依赖尚未可执行的 proposal。
- Phase 4 之前，confirm API 不允许真实创建 event/task。
- Phase 5 之前，前端可以展示开发预览，但不能让用户误以为 proposal 已经可稳定执行。
- Phase 7 之前，主动 signal 只能作为内部数据或 debug 观察，不向用户形成主动协商压力。

### 回滚策略

- 配置回滚：
  - `ASSISTANT_CONDUCTOR_MODE=legacy` 立即回到旧助手链路。
  - `ASSISTANT_PROACTIVE_MODE=off` 立即停用主动系统。
- 代码回滚：
  - 新增 `assistant_agents`、proposal routes、proposal services 必须通过 facade 接入，避免侵入旧 service 核心。
  - 旧 `AssistantService` 在 Phase 1A 内保留 fallback。
- 数据回滚：
  - Phase 1 新表应可空置，不影响旧表读取。
  - 若迁移需要降级，优先 drop 新增 assistant proposal/signal/thread 表，不触碰 `events/tasks/assistant_messages` 旧数据。
- 前端回滚：
  - `AssistantPanel` 新增 proposal 展示区应可通过 store 状态隐藏。
  - 文本确认失败时回落到普通助手回复，不阻塞会话发送。

## Phase 1A 可执行切片

| 切片 | 目标 | 后端范围 | 前端范围 | 验证门槛 |
|---|---|---|---|---|
| 1A-1 单 proposal + 单 option + 手动确认 | 建立最小 proposal 状态机 | `AssistantProposal`、Proposal Manager、confirm/reject 合约；confirm 不真实落库 | 可暂不改前端，使用 API 测试 | pending -> accepted；无 option 歧义；重复 confirm 不产生副作用 |
| 1A-2 单 proposal + 多 option | 支持方案 A/B/C | `payload_json.options`、`selected_option_id`、option 校验 | 助手文本能展示多方案 | 只能确认存在的 `option_id`；错误 option 返回明确错误 |
| 1A-3 revise 生成新 proposal | 支持“改到 4 点”类修改 | revise -> 新 proposal，旧 proposal -> superseded | 文本回复能提示新 P 编号 | 旧 proposal 不可再 confirm；新 proposal 可继续确认 |
| 1A-4 接入 Action Executor 真正落库 | 完成被动闭环 | `accepted -> execution_pending -> executed/failed`；复用 events/tasks service | pending 区显示执行结果 | 未确认不落库；确认后只执行一次；失败可 retry |

说明：

- 1A-1 到 1A-3 可以全部在后端 API 和测试中完成，不要求前端同步完成。
- 只有 1A-4 通过后，才允许进入用户可感知的 `proposal` mode。
- 1A-4 之前产生的 proposal 只能视为开发/调试数据，不作为真实日程安排承诺。

## 默认参数草案

这些参数是实施默认值，不是产品永久定论。后续可在 Phase 0 或 Phase 1B 中调整。

| 参数 | 默认值 | 使用阶段 | 说明 |
|---|---|---|---|
| `ASSISTANT_CONDUCTOR_MODE` | `legacy` | Phase 0+ | `shadow` 仅用于开发观察；`proposal` 需 Phase 4 后开启 |
| `ASSISTANT_PROACTIVE_MODE` | `off` | Phase 0+ | Phase 7 前保持关闭 |
| 直接出方案阈值 | `clear_goal + clear_time_or_window + low_risk` | Phase 3+ | 不满足则澄清或回旧链路 |
| pending proposal 默认过期 | `24h` | Phase 6+ | 时间敏感 proposal 可更短 |
| `event_creation` 过期 | `event_start` 前，或创建窗口结束 | Phase 6+ | 过期后不可 confirm |
| `deadline_risk` cooldown | `6h` | Phase 7+ | 同一 task + 同一风险日 |
| `conflict_warning` cooldown | `4h` | Phase 7+ | 同一冲突组合 |
| departure safety buffer | `10min` | Phase 7+ | `departure_time = event_start - travel_duration - 10min` |
| pending proposal 列表上限 | `5` | Phase 5+ | 超出时按时间敏感度和创建时间排序 |
| proposal 文本摘要长度 | `120 chars` | Phase 5+ | 前端显示摘要，详情仍在对话文本中 |
| 起床/睡前来源 | profile -> habits.md -> fallback | Phase 7+ | fallback 可用 `08:00 / 23:30` 仅作本地默认 |

## 执行阶段

### Phase 0 - Baseline Freeze And Guardrails

- Purpose: 在真正改代码前冻结当前运行基线、确认迁移头、建立功能开关和验证入口，避免新助手机制直接冲击现有工作台。
- Outputs:
  - 当前数据库 migration head 和测试基线记录。
  - 新增或确认后端配置项：
    - `ASSISTANT_CONDUCTOR_MODE=legacy|shadow|proposal`
    - `ASSISTANT_PROACTIVE_MODE=off|signals|proposals`
  - 明确 Phase 1A 默认启用策略：
    - Action Executor 完成前默认只用 `legacy` 或 `shadow`
    - Action Executor 完成且幂等验证通过后，开发环境可用 `proposal`
    - 不确定时先用 `shadow`
    - 生产/演示前可回退到 `legacy`
  - 一份 baseline 验证记录写回本任务书的进度台账。
- Completion criteria:
  - 能明确当前 Alembic head。
  - 能运行后端 compile/test 的最小集合。
  - 能运行前端 typecheck/build 的最小集合。
  - 确认旧助手链路在未启用 proposal mode 时保持可用。
- Validation:
  - `cd E:\GraduationProject\backend; alembic heads`
  - `cd E:\GraduationProject\backend; python -m compileall app`
  - `cd E:\GraduationProject\backend; pytest tests/test_assistant_service.py tests/test_api.py`
  - `cd E:\GraduationProject\frontend; pnpm exec vue-tsc --noEmit`
  - 手动访问 `http://127.0.0.1:8888/debug.html` 检查核心接口无新增异常。
  - 若基线测试存在失败，必须记录失败用例、错误摘要和是否为既有问题；未归因前不得把失败当作新实现的通过标准。
- Evidence:
  - 记录命令结果摘要。
  - 记录当前 env/compose 是否启用 Celery/Redis。
  - 记录是否有额外 API 容器干扰。

### Phase 1 - Data Foundation And Migration

- Purpose: 先落数据骨架，让 proposal/signal/thread state 具备可查询、可幂等、可跟踪的稳定载体；memory candidate 默认延后到长期记忆阶段。
- Outputs:
  - `backend/app/models.py` 新增：
    - `AssistantProposal`
    - `AssistantSignal`
    - `AssistantThreadState`
  - 新增 Alembic migration，建议命名：
    - `0007_assistant_proposal_foundation.py`（文件名示例；实际 revision id 必须以当前 `alembic heads` 为准）
  - 新增 repository：
    - `backend/app/repositories/assistant_proposals.py`
    - `backend/app/repositories/assistant_signals.py`
    - `backend/app/repositories/assistant_thread_states.py`
  - `backend/app/api/schemas.py` 新增 proposal/signal/thread/memory candidate 的 Pydantic v2 schema。
    - memory candidate schema 可先只定义草案，也可延后到 Phase 8。
  - 可选延后 migration：
    - `0008_task_event_execution_metadata.py`
    - 仅在 Phase 1A Action Executor 明确需要时扩展 `Task` / `Event`。
    - `xxxx_assistant_memory_candidates.py`
    - 仅在 Phase 8 或一期后半段接入长期记忆候选时新增。
- Migration order:
  - Step 1: 确认当前 Alembic head。
  - Step 2: 新增 `AssistantProposal`、`AssistantSignal`、`AssistantThreadState` 三张核心表，不先修改现有 `tasks/events`。
  - Step 3: 添加普通索引：
    - `assistant_proposals(user_id, status, created_at)`
    - `assistant_proposals(user_id, dedup_key)`
    - `assistant_proposals(session_id, status)`
    - `assistant_signals(user_id, status, signal_type)`
    - `assistant_signals(user_id, dedup_key)`
    - `assistant_thread_states(user_id, session_id, status)`
  - Step 4: dedup 先用 service 层查询约束，避免 SQLite partial unique 细节拖慢 Phase 1A。
  - Step 5: 迁移后补 repository 单元测试。
- Completion criteria:
  - Alembic upgrade 能从当前库迁移到新 head。
  - 新 repository 支持 create/get/list/update/status transition。
  - `dedup_key` 字段存在并能被查询。
  - `payload_json.execution` schema 在 API 层有明确读写位置。
  - 若暂缓 `AssistantMemoryUpdateCandidate`，任务书中必须保留 Phase 8 的明确落点。
- Validation:
  - `cd E:\GraduationProject\backend; alembic upgrade head`
  - `cd E:\GraduationProject\backend; python -m compileall app`
  - 新增并运行：
    - `pytest tests/test_assistant_proposals_repository.py`
    - `pytest tests/test_assistant_signals_repository.py`
  - 迁移后打开 API，确认现有 `/api/events`、`/api/tasks`、`/api/assistant/current` 仍可访问。
- Evidence:
  - Migration 文件路径。
  - 新增 model/repository/schema 文件路径。
  - 测试结果摘要。

### Phase 2 - Proposal API And Manager

- Purpose: 在不替换旧聊天链路的前提下，先让 proposal 作为独立结构化对象完整闭环。
- Outputs:
  - 新增或拆分 route：
    - `backend/app/api/routes/assistant_proposals.py`
  - 挂载到 `backend/app/api/router.py`，保持前缀：
    - `/api/assistant/proposals`
  - 新增 service：
    - `backend/app/services/assistant_proposal_manager.py`
  - Proposal API:
    - `GET /api/assistant/proposals`
    - `GET /api/assistant/proposals/{id}`
    - `POST /api/assistant/proposals/{id}/confirm`
    - `POST /api/assistant/proposals/{id}/reject`
    - `POST /api/assistant/proposals/{id}/revise`
    - `POST /api/assistant/proposals/{id}/retry`
    - `POST /api/assistant/proposals/{id}/expire`（internal/debug，可延后到 Phase 6）
  - 明确 confirm/retry 幂等逻辑：
    - Phase 2 只完成 Proposal Manager 状态机，不执行真实任务/日程写入。
    - Phase 2 confirm 可验证 `option_id` 并记录 `selected_option_id`，最多进入 `accepted`。
    - Phase 4 接入 Action Executor 后，再允许 `accepted -> execution_pending -> executed`。
    - `execution_failed -> retry -> execution_pending` 的真实重试在 Phase 4 后启用。
    - `executed` 重复 confirm 返回同一执行回执，不重复落库。
  - 多 proposal 用户可读短标识：
    - `P1`, `P2`, `P3`
    - 由 Proposal Manager 在同一 active set 内分配。
- Completion criteria:
  - 可以通过 Proposal Manager 测试夹具或 internal/debug 入口创建测试 proposal；不新增普通用户公开创建 proposal 入口。
  - 可以确认某个 `option_id`。
  - 可以拒绝、修改。
  - retry API 的路由、权限与状态约束可先完成合约测试；真实失败重试在 Phase 4 接入 Action Executor 后验收。
  - `AssistantThreadState.status` 不参与可执行性判断。
  - confirm 对不存在 option、过期 proposal、superseded proposal 返回明确错误。
  - 在 Phase 4 之前，confirm 不得真实创建 event/task。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_proposal_api.py`
    - `pytest tests/test_assistant_proposal_manager.py`
  - 手动 API 验证：
    - pending proposal confirm 后状态变化正确。
    - 重复 confirm 不新增 event/task。
    - retry 合约拒绝非法状态；Phase 4 后再验证 execution_failed retry 复用 `selected_option_id`。
  - 检查 websocket/workspace broadcast 不因 proposal API 引入慢请求。
- Evidence:
  - API 测试截图或日志摘要。
  - Proposal 状态转换样例。
  - 幂等测试用例名称。

### Phase 3 - Passive Conductor And Specialist Registry

- Purpose: 将用户消息从“关键词 intent -> 直接执行”改造成“Conductor 按需调 specialist -> clarification/proposal/followup”，但先聚焦被动用户输入，不接主动心跳。
- Outputs:
  - 新目录：
    - `backend/app/assistant_agents/__init__.py`
    - `backend/app/assistant_agents/contracts.py`
    - `backend/app/assistant_agents/registry.py`
    - `backend/app/assistant_agents/conductor.py`
    - `backend/app/assistant_agents/specialists/understanding.py`
    - `backend/app/assistant_agents/specialists/task_or_event_clarifier.py`
    - `backend/app/assistant_agents/specialists/planning.py`
    - `backend/app/assistant_agents/specialists/negotiation.py`
    - `backend/app/assistant_agents/specialists/proposal_manager.py`
  - Phase 1A 最小 specialist 能力：
    - `Understanding Specialist`: 结构化理解用户目标、时间、地点、模糊点。
    - `Task-or-Event Clarifier`: 判断任务/日程不清时生成澄清问题。
    - `Planning Specialist`: 生成简单 proposal options。
    - `Negotiation Specialist`: 生成纯文本回复，不决定是否跳过确认。
  - 在 `backend/app/services/assistant.py` 中接入模式开关：
    - `legacy`: 走旧链路。
    - `shadow`: 运行新 Conductor 但不改变用户回复，只记录日志。
    - `proposal`: 仅在 Phase 4 Action Executor 可用且幂等验证通过后，对支持场景返回可确认执行的 proposal/clarification。
  - 初始支持场景：
    - 清晰单日程请求。
    - 模糊日程请求。
    - 模糊任务请求。
    - 任务/日程类型不清请求。
  - 不支持场景回退：
    - 普通聊天、复杂工具调用、超出计划边界的问题，暂时回旧助手回复。
  - Phase 3 的主要验收模式是 `shadow`；如需提前展示 proposal，只能作为开发环境内部预览，不承诺用户确认后落库。
- Completion criteria:
  - “我要去约会”不会直接出方案，优先澄清意图和关键约束。
  - “明天下午3点我要去学校和同学见面”能生成候选 proposal，但不落库。
  - “帮我安排复习”能识别为任务倾向，并询问科目、截止时间、节奏等必要信息。
  - 一个回复中如有多个 proposal，必须显示 `P1/P2`。
  - 只有一个 active proposal 时，用户“按方案A”可容错指向该 proposal；多个 active proposal 时必须澄清。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_conductor.py`
    - `pytest tests/test_assistant_specialists.py`
    - `pytest tests/test_assistant_text_protocol.py`
  - 对 `/ws/assistant` 手动验证流式输出：
    - `shadow` mode 下旧 token/done 流不被破坏。
    - 开发预览或 `proposal` mode 下 token / proposal_created / done 事件顺序合理。
    - 前端不因新增 chunk 类型崩溃。
  - 对 `/api/assistant/message` 验证非 WebSocket fallback 一致。
- Evidence:
  - Conductor routing 日志样例。
  - 三类核心输入的请求/响应样例。
  - shadow/proposal mode 切换结果。

### Phase 4 - Action Executor And Confirmed Write Path

- Purpose: 只在用户确认 proposal option 后执行任务/日程写入，让 proposal 真正成为执行前唯一入口。
- Outputs:
  - 新增：
    - `backend/app/assistant_agents/action_executor.py`
  - Action types:
    - `create_event`
    - `create_task`
    - `create_task_with_events`
    - `reschedule_event`
    - `mark_event_completed`
    - `mark_task_completed`
  - Phase 1A 首批只强制实现：
    - `create_event`
    - `create_task`
    - `create_task_with_events`
  - Action Executor 复用现有 service：
    - `backend/app/services/events.py`
    - `backend/app/services/tasks.py`
    - `backend/app/services/suggestions.py`
  - 更新 proposal：
    - `selected_option_id`
    - `execution_started_at`
    - `payload_json.execution`
    - `execution_error`
    - `executed_at`
  - 可选扩展 `Event`：
    - `proposal_origin_id`
    - `execution_role`
  - 可选扩展 `Task`：
    - `planning_status`
    - `completion_mode`
    - `goal_summary`
- Completion criteria:
  - 未确认 proposal 不会创建任务/日程。
  - 确认 `event_creation` proposal 后创建一个事件。
  - 确认 `task_creation` proposal 后创建一个任务。
  - 确认 `task_schedule_plan` proposal 后创建父任务和多个 linked events。
  - 执行失败时 proposal 进入 `execution_failed`，错误可读，retry 可用。
  - 重复 confirm 不重复写入。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_action_executor.py`
    - `pytest tests/test_assistant_confirm_execution.py`
  - 手动端到端：
    - 用户提出日程 -> proposal pending -> 用户确认 -> `/api/events` 出现新事件。
    - 用户提出任务 -> proposal pending -> 用户确认 -> `/api/tasks` 出现新任务。
    - 用户提出“未来一个月每周三驾校练车” -> 一个父任务 + 多个普通日程。
  - 检查 Google Calendar 同步失败不会导致本地 proposal 状态混乱；外部同步错误仍按现有事件服务策略处理。
- Evidence:
  - 执行前后 DB 记录摘要。
  - `payload_json.execution` 成功/失败样例。
  - 幂等验证结果。

### Phase 5 - Frontend Proposal Surface

- Purpose: 在保持“纯文本交互优先”的前提下，让用户能看到当前待确认 proposal、主动跟进项和清晰的回复方式。
- Outputs:
  - 更新 store：
    - `frontend/src/stores/assistant.ts`
    - 必要时新增 proposal 类型到 `frontend/src/stores/types.ts`
  - 更新组件：
    - `frontend/src/components/AssistantPanel.vue`
  - 新增前端能力：
    - 拉取 active proposals。
    - 展示当前待确认事项区。
    - 在聊天流中渲染 proposal 文本。
    - 识别 `proposal_created` / `proposal_updated` WebSocket 事件。
    - 支持用户自然语言确认，不强制按钮。
  - 不做复杂 UI：
    - 不做多层卡片嵌套。
    - 不做完整 proposal 管理后台。
    - 不做按钮依赖流程。
- Completion criteria:
  - 用户能在助手面板看到 `P1/P2` 待确认事项。
  - 文本回复“P1 按方案A”可触发 confirm 链路。
  - 多 proposal 并存时，不带 `P1/P2` 的模糊回复会得到澄清。
  - 旧会话、旧消息、session 切换不被破坏。
- Validation:
  - `cd E:\GraduationProject\frontend; pnpm exec vue-tsc --noEmit`
  - `cd E:\GraduationProject\frontend; pnpm run build`
  - Playwright 手动检查：
    - 桌面助手页 proposal 展示不溢出。
    - 移动端底部输入区不遮挡待确认事项。
    - 新增 chunk 类型不会造成控制台错误。
- Evidence:
  - 前端构建结果。
  - 桌面/移动截图路径。
  - 手动确认链路说明。

### Phase 6 - Phase 1B Stability And Observability

- Purpose: 把 proposal 闭环从“能跑”提升到“能查、能恢复、能解释”，为主动系统接入做准备。
- Outputs:
  - 强化 dedup：
    - active proposal 去重。
    - signal/proposal dedup 查询工具。
  - 强化状态审计：
    - proposal 状态转换日志。
    - action execution attempt 日志。
    - conductor routing 日志。
  - Debug 页面或 debug API 增加最小可观测项：
    - active proposals 数量。
    - execution_failed 数量。
    - 最近 proposal transitions。
  - 补齐 revise 逻辑：
    - revise 不直接改原 proposal。
    - revise 生成新 proposal，并 supersede 原 proposal。
  - 补齐 expiry job：
    - 定期将过期 pending proposal 标记为 `expired`。
- Completion criteria:
  - 失败 proposal 可见、可 retry、可解释。
  - 同一 dedup_key 不会在 active 状态下生成重复 proposal。
  - revise/supersede 状态清楚。
  - 过期 proposal 不可确认。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_proposal_dedup.py`
    - `pytest tests/test_assistant_proposal_expiry.py`
    - `pytest tests/test_assistant_proposal_revise.py`
  - 手动验证：
    - 重复发送同一清晰请求不产生两个 active proposal。
    - pending proposal 过期后 confirm 被拒绝。
    - revise 后旧 proposal 变为 superseded。
- Evidence:
  - debug 输出。
  - dedup/expiry/revise 测试结果。

### Phase 7 - Proactive Signals And Daily Rhythm

- Purpose: 在被动 proposal 闭环稳定后，引入主动系统，让提醒从“通知”升级为“带上下文的协商”。
- Outputs:
  - 新增或改造 jobs：
    - `backend/app/jobs/assistant_signals.py`
    - 逐步替代/吸收 `backend/app/jobs/inbox.py` 中的 proactive inbox 思路。
  - Celery beat 新增任务：
    - 晨间计划检查。
    - 睡前复盘生成。
    - deadline risk signal。
    - conflict repair signal。
    - departure readiness signal。
  - Signal -> Proposal 规则：
    - `deadline_risk -> deadline_recovery proposal`
    - `conflict_warning -> reschedule_plan proposal`
    - `daily_morning_review -> daily plan followup`
    - `daily_night_review -> daily_review_followup`
  - Signal API：
    - `GET /api/assistant/signals`
    - `POST /api/assistant/heartbeat/run`（debug only）
    - signal 状态推进使用 `new / evaluated / proposal_created / cooling / dismissed / expired`，不重新引入旧的 `consumed` 主语义。
  - 天气策略：
    - 06:00 今日天气快照。
    - 出发前默认用缓存。
    - 强风险或缓存过旧时才补拉。
  - 出行策略：
    - 一期只做保守估算 + 出发提醒 + 高德跳转预留。
    - 不承诺实时精确位置。
- Completion criteria:
  - 主动 signal 能生成，但不会绕过 proposal 确认。
  - 同类 signal 受 cooldown + dedup 控制。
  - 起床后 30 分钟、睡前 30 分钟使用 profile/habits fallback 计算。
  - 出行提醒围绕 `departure_time`，不是 `event_start`。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_signals.py`
    - `pytest tests/test_assistant_daily_review.py`
    - `pytest tests/test_assistant_departure_signal.py`
  - 手动/时间模拟：
    - 创建明日冲突事件 -> 生成 conflict signal/proposal。
    - 创建临近 deadline 任务 -> 生成 deadline recovery proposal。
    - 外出事件含 travel_duration -> departure reminder 在正确时间窗出现。
- Evidence:
  - Celery beat 配置变更。
  - Signal/proposal 关联样例。
  - cooldown/dedup 测试结果。

### Phase 8 - Long-Term Memory And Personalization

- Purpose: 在核心闭环稳定后，引入可读的长期记忆文件，让地点、偏好、习惯、术语映射成为 specialist 可使用的上下文。
- Outputs:
  - 新增运行时记忆目录策略：
    - `backend/data/memory/{user_id}/preferences.md`
    - `backend/data/memory/{user_id}/places.md`
    - `backend/data/memory/{user_id}/habits.md`
    - `backend/data/memory/{user_id}/glossary.md`
  - 新增模板：
    - `backend/app/assistant_agents/memory/templates/*.md`
  - 新增：
    - `backend/app/assistant_agents/specialists/memory.py`
  - 若 Phase 1 未创建，新增：
    - `AssistantMemoryUpdateCandidate`
    - `backend/app/repositories/assistant_memory_candidates.py`
    - `xxxx_assistant_memory_candidates.py`（文件名示例，实际 revision id 以当前 head 为准）
  - Memory API：
    - `GET /api/assistant/memory`
    - `GET /api/assistant/memory/candidates`
    - `POST /api/assistant/memory/candidates/{id}/confirm`
    - `POST /api/assistant/memory/candidates/{id}/reject`
  - Memory update candidates:
    - 由 specialist 提出。
    - 由 Memory Specialist 统一写入。
    - 睡前总结后或用户明确“记住这个”时应用。
  - Places memory:
    - “学校/图书馆/驾校”等地点别名映射。
    - 地点粒度保持“主地点 + 少量子地点”。
- Completion criteria:
  - `.md` 文件可初始化、可读、可由 Memory Specialist 更新。
  - 其他 specialist 不能直接写 `.md`。
  - 地点记忆不会被误用为当前位置。
  - `current_origin` 只存在运行时上下文，不写入长期记忆。
- Validation:
  - 新增并运行：
    - `pytest tests/test_assistant_memory_specialist.py`
    - `pytest tests/test_assistant_places_memory.py`
  - 手动验证：
    - 用户说“记住学校是 X” -> candidate/apply -> `places.md` 更新。
    - 用户说“我现在在学校” -> 当前 origin 更新，但不写入长期记忆。
- Evidence:
  - memory 文件样例。
  - candidate -> applied 状态样例。
  - 读写权限测试结果。

## 迁移顺序

1. `0007_assistant_proposal_foundation.py`
   - 新增三张核心表：
     - `assistant_proposals`
     - `assistant_signals`
     - `assistant_thread_states`
   - 新增普通索引，不强依赖 partial unique。
   - 不修改现有 `events/tasks`。
   - 文件名只是示例，实际 Alembic revision id 必须基于当前 `alembic heads` 生成。

2. `0008_task_event_execution_metadata.py`（可选，建议在 Phase 4 前后再决定）
   - `tasks.planning_status`
   - `tasks.completion_mode`
   - `tasks.goal_summary`
   - `events.proposal_origin_id`
   - `events.execution_role`
   - 若 Phase 4 可通过 `payload_json.execution` 和现有 `linked_task_id` 完成，则延后此迁移。

3. `xxxx_assistant_memory_candidates.py`（Phase 8；若 Phase 1 已建则跳过）
   - `assistant_memory_update_candidates`
   - 与 Memory Specialist 和 `.md` 长期记忆一起落地。
   - `xxxx` 表示以后基于当时 Alembic head 生成的实际 revision id。

4. `xxxx_assistant_signal_scheduling.py`（Phase 7；仅在需要持久化 heartbeat schedule 时新增）
   - 如需记录 heartbeat schedule 或 daily review 状态，再新增。
   - 不在 Phase 1A 提前创建未使用字段。
   - 该迁移不要求排在 memory candidates 之后；实际顺序按执行阶段和当前 head 决定。

## 开发顺序

1. 冻结基线与功能开关。
2. 迁移 proposal 基础表。
3. 写 repository + schema + API，不接聊天。
4. 写 Proposal Manager，完成状态机和幂等。
5. 写 Conductor + registry + 最小 specialists，先 shadow。
6. 将 `/api/assistant/message` 和 `/ws/assistant` 接入 `shadow` mode，验证新 Conductor 不改变旧用户体验。
7. 写 Action Executor，确认后执行真实写入。
8. Action Executor 幂等验证通过后，再把 `/api/assistant/message` 和 `/ws/assistant` 从 `shadow` 切到可执行的 `proposal` mode。
9. 前端展示 active proposals 和文本确认。
10. 做 Phase 1B 稳定性：dedup/revise/expiry/debug。
11. 接入主动 signal。
12. 接入长期记忆。

## 验证顺序

1. Static and migration validation:
   - `python -m compileall app`
   - `alembic upgrade head`
   - `pnpm exec vue-tsc --noEmit`
   - `pnpm run build`

2. Backend unit validation:
   - repository tests
   - Proposal Manager tests
   - Conductor routing tests
   - Action Executor idempotency tests
   - Signal cooldown/dedup tests

3. API validation:
   - proposal CRUD/status endpoints
   - confirm/reject/revise/retry
   - old assistant endpoints still available
   - websocket stream chunk compatibility

4. End-to-end passive validation:
   - vague event -> clarification
   - clear event -> proposal -> confirm -> event
   - task request -> proposal -> confirm -> task
   - recurring-like task -> parent task + ordinary events
   - multiple proposals -> P1/P2 disambiguation

5. End-to-end proactive validation:
   - deadline risk -> signal -> proposal
   - conflict -> signal -> proposal
   - departure -> reminder/followup at `departure_time - 10min`
   - morning/night rhythm uses profile/habits fallback

6. Regression validation:
   - existing event CRUD
   - existing task CRUD
   - Google Calendar best-effort sync
   - workspace hydration remains light
   - notification broadcast remains non-blocking

## 阶段完成检查清单

每完成一个阶段，都必须把结果写回本任务书的进度台账。检查清单如下：

1. 是否仍满足设计硬规则：
   - 不确认不落库。
   - `AssistantProposal.status` 决定执行资格。
   - `AssistantThreadState.status` 不参与可执行性判断。
   - `Memory Specialist` 之外的模块不直接写 `.md` 长期记忆。

2. 是否仍满足兼容要求：
   - 旧 `/api/assistant/message` 可用。
   - 旧 `/ws/assistant` 可用。
   - 首页 hydrate 不新增主动重请求。
   - events/tasks/profile/settings 主链路未被改坏。

3. 是否留下可复现证据：
   - 运行过哪些命令。
   - 哪些测试通过/失败。
   - 哪些失败是既有问题。
   - 新增了哪些文件和迁移。

4. 是否更新下一步：
   - 当前 active phase 是否变化。
   - 是否有新 blocker。
   - 是否需要调整默认参数。

## 进度更新模板

后续每完成一个阶段或一个 1A 切片，使用以下格式更新本文件，不另起散落报告：

```md
## 进度更新 - YYYY-MM-DD HH:mm +08:00

- Overall progress: [一句话说明当前推进到哪里]
- Active phase: [Phase 名称或 1A-x 切片]
- Execution readiness: drafting | approved for execution | executing | blocked
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done | in progress | pending | blocked
  - Phase 1 - Data Foundation And Migration: done | in progress | pending | blocked
  - Phase 2 - Proposal API And Manager: done | in progress | pending | blocked
  - Phase 3 - Passive Conductor And Specialist Registry: done | in progress | pending | blocked
  - Phase 4 - Action Executor And Confirmed Write Path: done | in progress | pending | blocked
  - Phase 5 - Frontend Proposal Surface: done | in progress | pending | blocked
  - Phase 6 - Phase 1B Stability And Observability: done | in progress | pending | blocked
  - Phase 7 - Proactive Signals And Daily Rhythm: done | in progress | pending | blocked
  - Phase 8 - Long-Term Memory And Personalization: done | in progress | pending | blocked
- Change summary:
  - [本轮持久化改动]
- Validation result:
  - [命令、结果、失败归因]
- Decision updates:
  - Verified facts: [新增事实或 none]
  - Locked decisions: [新增决策或 none]
  - Open questions: [新增问题或 none]
- Residual risks:
  - [剩余风险或 none]
- Next recommended action:
  - [单个最优先下一步]
```

## 进度更新 - 2026-04-30 23:17 +08:00

- Overall progress: Phase 0 基线冻结已完成，当前可以进入 Phase 1 数据基础与迁移。
- Active phase: Phase 1 - Data Foundation And Migration
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: pending
  - Phase 2 - Proposal API And Manager: pending
  - Phase 3 - Passive Conductor And Specialist Registry: pending
  - Phase 4 - Action Executor And Confirmed Write Path: pending
  - Phase 5 - Frontend Proposal Surface: pending
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: in progress
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 完成 Phase 0 基线验证。
  - 确认实际运行验证应优先使用 Docker API 容器；本机 PowerShell 中 `alembic` 不在 PATH，默认 `python` 为 3.14，不作为后端基线环境。
  - 确认当前运行容器包括 `graduation-project-api`、`graduation-project-frontend`、`graduation-project-celery-worker`、`graduation-project-celery-beat`、`graduation-project-redis`。
- Validation result:
  - `docker exec graduation-project-api sh -lc "alembic heads"`: passed，当前 head 为 `1d052940e0a7`.
  - `docker exec graduation-project-api sh -lc "python -m compileall app"`: passed.
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_service.py tests/test_api.py"`: passed，`47 passed in 6.99s`.
  - `pnpm --dir E:\GraduationProject\frontend exec vue-tsc --noEmit`: passed.
  - `pnpm --dir E:\GraduationProject\frontend run build`: passed，Vite build completed in `13.50s`.
  - `Invoke-WebRequest http://127.0.0.1:8888/debug.html`: passed，HTTP `200`, response length `29265`.
- Decision updates:
  - Verified facts:
    - 后端 Phase 0 验证以 Docker 容器 `graduation-project-api` 为准，容器内 Python 为 `3.11.15`，pytest 为 `8.3.5`.
    - 前端 pnpm 可用，版本为 `10.30.1`.
    - 当前 docker compose 主服务处于运行状态，Redis healthy。
  - Locked decisions:
    - 进入 Phase 1 前无需修复基线失败，因为本轮基线验证没有失败。
  - Open questions:
    - none
- Residual risks:
  - 本机 Python 3.14 与容器 Python 3.11 不一致；后端执行、测试、迁移应优先使用容器或项目虚拟环境。
  - 当前 worktree 已有多处既有改动与 untracked 文件，Phase 1 实施时仍需避免回滚非本任务改动。
- Next recommended action:
  - 开始 Phase 1：新增 `AssistantProposal`、`AssistantSignal`、`AssistantThreadState` ORM/schema/repository 和 Alembic migration。

## 进度更新 - 2026-04-30 23:27 +08:00

- Overall progress: Phase 1 数据基础与迁移已完成，当前可以进入 Phase 2 Proposal API 与 Manager。
- Active phase: Phase 2 - Proposal API And Manager
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: pending
  - Phase 3 - Passive Conductor And Specialist Registry: pending
  - Phase 4 - Action Executor And Confirmed Write Path: pending
  - Phase 5 - Frontend Proposal Surface: pending
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增三张核心 ORM 表：`AssistantProposal`、`AssistantSignal`、`AssistantThreadState`。
  - 新增 Alembic migration：`backend/alembic/versions/0007_assistant_proposal_foundation.py`。
  - 新增 repository：`assistant_proposals.py`、`assistant_signals.py`、`assistant_thread_states.py`。
  - 新增 API schema：proposal / signal / thread state 的 create/update/read/list 与 confirm/revise request。
  - 新增 repository 测试：`test_assistant_proposals_repository.py`、`test_assistant_signals_repository.py`。
- Validation result:
  - `docker exec graduation-project-api sh -lc "python -m compileall app"`: passed.
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_proposals_repository.py tests/test_assistant_signals_repository.py"`: passed，`3 passed in 23.79s`.
  - `docker exec graduation-project-api sh -lc "alembic heads"`: passed，新 head 为 `0007_assistant_proposal_foundation`.
  - `docker exec graduation-project-api sh -lc "alembic upgrade head && alembic current"`: passed，数据库已升级到 `0007_assistant_proposal_foundation`.
  - SQLite 表检查: passed，已存在 `assistant_proposals`、`assistant_signals`、`assistant_thread_states`。
  - 核心 API smoke test: passed，`/api/health`、`/api/events`、`/api/tasks`、`/api/assistant/current?include_inbox=false` 均返回 HTTP 200。
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_service.py tests/test_api.py"`: passed，`47 passed in 3.76s`.
- Decision updates:
  - Verified facts:
    - Phase 1 最小表集按设计保持为三张核心表，未提前创建 `AssistantMemoryUpdateCandidate`。
    - `AssistantProposal.thread_state_id` 与 `AssistantThreadState.active_proposal_id` 不建循环外键，仅保留索引字段，业务一致性后续由 Proposal Manager 维护。
  - Locked decisions:
    - Phase 2 先实现 Proposal Manager 与 API 合约；真实 event/task 写入仍留到 Phase 4 Action Executor。
  - Open questions:
    - none
- Residual risks:
  - 当前数据库已执行新迁移；若后续需要回滚，应只 drop 新增 proposal/signal/thread 表，不触碰旧业务表。
  - API 进程仍是此前启动的服务实例，新增代码验证以容器内命令和测试为准；若要验证新增 route，需要后续重启 API 或等容器重载。
- Next recommended action:
  - 开始 Phase 2：实现 `AssistantProposalManager` 与 `/api/assistant/proposals` 结构化接口，不接真实 Action Executor。

## 进度更新 - 2026-04-30 23:34 +08:00

- Overall progress: Phase 2 Proposal API 与 Manager 已完成，当前可以进入 Phase 3 被动 Conductor 与 Specialist Registry。
- Active phase: Phase 3 - Passive Conductor And Specialist Registry
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: pending
  - Phase 4 - Action Executor And Confirmed Write Path: pending
  - Phase 5 - Frontend Proposal Surface: pending
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增 `AssistantProposalManager`，负责 proposal lifecycle 状态转换。
  - 新增 `/api/assistant/proposals` 路由并挂载到主 API router。
  - 支持 list/get/confirm/reject/revise/retry/expire 合约。
  - Phase 2 confirm 只校验 `option_id` 并进入 `accepted`，不真实创建 event/task。
  - retry 仅允许 `execution_failed` 状态，真实重试执行仍留给 Phase 4 Action Executor。
- Validation result:
  - `docker exec graduation-project-api sh -lc "python -m compileall app"`: passed.
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_api.py"`: passed，`5 passed in 42.45s`.
  - 重启 `graduation-project-api` 后，`GET /api/assistant/proposals`: passed，HTTP 200，返回 `{"items":[],"total":0}`。
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_api.py tests/test_assistant_service.py tests/test_api.py"`: passed，`52 passed in 48.16s`.
- Decision updates:
  - Verified facts:
    - 新 proposal 路由在实际 API 容器重启后可加载。
    - Phase 2 未新增普通用户公开创建 proposal 入口。
  - Locked decisions:
    - Phase 3 默认只能先接 `shadow` mode，不直接向用户开放可执行 proposal。
  - Open questions:
    - none
- Residual risks:
  - `AssistantProposalManager.revise_proposal()` 当前生成的是状态正确的新 proposal，具体重新规划逻辑要等 Phase 3 Planning/Negotiation specialist 接入后补足。
  - Phase 2 API 已可用，但前端尚未接入 pending proposal 展示。
- Next recommended action:
  - 开始 Phase 3：建立 `backend/app/assistant_agents` 目录、contracts、registry、conductor 和最小 specialists，并以 `shadow` mode 接入旧助手 facade。

## 进度更新 - 2026-05-01 00:08 +08:00

- Overall progress: Phase 3 被动 Conductor 与 Specialist Registry 已完成，当前可以进入 Phase 4 Action Executor 与确认后写入链路。
- Active phase: Phase 4 - Action Executor And Confirmed Write Path
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: pending
  - Phase 5 - Frontend Proposal Surface: pending
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增 `backend/app/assistant_agents` 多智能体骨架，包括 contracts、registry、conductor 和五个最小 specialists。
  - `Understanding Specialist` 支持清晰单日程、模糊日程、模糊任务、任务/日程不清的保守识别。
  - `Planning Specialist` 只生成内存 proposal draft，不写任务/日程。
  - `ProposalManager Specialist` 只准备 `P1/P2`、`dedup_key` 与 create payload，不持久化。
  - `Negotiation Specialist` 生成纯文本提案/澄清话术，并明确“现在不会直接写入日程/任务”。
  - 新增 `ASSISTANT_CONDUCTOR_MODE`、`ASSISTANT_PROACTIVE_MODE` 配置项。
  - `AssistantService` 接入 shadow conductor；默认 `legacy` 不运行，`proposal` 在 Phase 4 前强制降级为 shadow。
- Validation result:
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_conductor.py tests/test_assistant_specialists.py tests/test_assistant_text_protocol.py"`: passed，`7 passed in 4.10s`.
  - `docker exec graduation-project-api sh -lc "python -m compileall app && pytest tests/test_assistant_conductor.py tests/test_assistant_specialists.py tests/test_assistant_text_protocol.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_api.py tests/test_assistant_service.py tests/test_api.py"`: passed，`59 passed in 27.26s`.
  - 重启 `graduation-project-api` 后，`GET /api/health`: passed，HTTP 200。
  - 重启 `graduation-project-api` 后，`GET /api/assistant/proposals`: passed，HTTP 200。
  - `ws://127.0.0.1:8000/ws/assistant?user_id=local-user`: passed，WebSocket 可连接并正常关闭。
- Decision updates:
  - Verified facts:
    - Phase 3 shadow conductor 已可从 `AssistantService` 调用，且不改变旧助手返回。
    - “我要去约会”进入澄清，不生成 proposal。
    - “明天下午3点我要去学校和同学见面”可生成单个 `event_creation` proposal draft，默认 1 小时假设只作为确认前方案。
    - “帮我安排复习”进入任务澄清，要求补充科目、截止/时间窗口和节奏。
  - Locked decisions:
    - Phase 4 前即使配置为 `ASSISTANT_CONDUCTOR_MODE=proposal`，后端也只按 shadow 运行，不对用户暴露可执行 proposal。
  - Open questions:
    - Phase 4 是否马上扩展 `Task/Event` 元数据仍未决，建议先用 `payload_json.execution` 与现有字段完成最小幂等闭环。
- Residual risks:
  - Phase 3 的 proposal 仍是内存草案，尚未经过 Action Executor 幂等执行验证。
  - 新 understanding 只覆盖一期核心样例，复杂自然语言仍要依赖后续 LLM/slot extraction 增强。
  - `schedule_guidance` 暂时回旧链路，后续需要在 Phase 4/5 后再升级为 proposal-first 流程。
- Next recommended action:
  - 开始 Phase 4：实现 `backend/app/assistant_agents/action_executor.py`，先支持 `create_event`、`create_task`、`create_task_with_events`，并把 confirm 后执行做成幂等状态机。

## 进度更新 - 2026-05-01 00:24 +08:00

- Overall progress: Phase 4 Action Executor 与确认后写入链路已完成，当前可以进入 Phase 5 前端 proposal surface。
- Active phase: Phase 5 - Frontend Proposal Surface
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: pending
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增 `backend/app/assistant_agents/action_executor.py`。
  - `AssistantActionExecutor` 首批支持 `create_event`、`create_task`、`create_task_with_events`。
  - `AssistantProposalManager.confirm_proposal()` 默认从 `pending/accepted -> execution_pending -> executed/execution_failed`。
  - 重复确认同一已执行 proposal 会返回原 proposal，不重复执行。
  - `retry_proposal()` 对 `execution_failed` proposal 重新执行已选 option，并递增 `payload_json.execution.retry_count`。
  - `payload_json.execution` 记录 selected option、attempts、result、last_error。
  - `/api/assistant/proposals/{id}/confirm` 与 `/retry` 执行后触发 `broadcast_workspace_update()`。
  - Action Executor 改为懒加载，避免只读 proposal API 初始化重 service。
- Validation result:
  - `docker exec graduation-project-api sh -lc "pytest tests/test_assistant_action_executor.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_api.py"`: passed，`9 passed in 55.09s`.
  - `docker exec graduation-project-api sh -lc "python -m compileall app && pytest tests/test_assistant_action_executor.py tests/test_assistant_conductor.py tests/test_assistant_specialists.py tests/test_assistant_text_protocol.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_api.py tests/test_assistant_proposals_repository.py tests/test_assistant_signals_repository.py tests/test_assistant_service.py tests/test_api.py"`: passed，`66 passed in 70.94s`.
  - 重启 `graduation-project-api` 后，`GET /api/health`: passed，HTTP 200。
  - 重启 `graduation-project-api` 后，`GET /api/assistant/proposals`: passed，HTTP 200。
  - `ws://127.0.0.1:8000/ws/assistant?user_id=local-user`: passed，WebSocket 可连接并正常关闭。
- Decision updates:
  - Verified facts:
    - Phase 4 最小执行器已能通过 fake service 验证真实写入调用顺序。
    - 未确认 proposal 不会调用 Action Executor。
    - 已执行 proposal 重复 confirm 不会重复调用 Action Executor。
    - 失败 proposal 会进入 `execution_failed`，并可通过 retry 再次执行同一 option。
  - Locked decisions:
    - Phase 4 不新增 `AssistantActionExecution` 表，执行快照继续放在 `payload_json.execution`。
    - Phase 4 不扩展 `Task/Event` 元数据，先用 proposal 侧记录和现有 linked_task_id 建立闭环。
  - Open questions:
    - Phase 5 前端是否只接 pending/executed proposal 列表，还是同时在聊天流中展示 proposal_created 事件；建议先只接 API 列表，避免改动 WebSocket 协议。
- Residual risks:
  - `create_task_with_events` 目前复用现有 service，跨多个写入没有全局事务；若中途失败，已完成的部分写入需要后续 Phase 6 做补偿/观测。
  - 默认真实 API confirm 已会执行 proposal action；在前端正式接入前，不应手工确认不可信来源的 proposal。
  - Action Executor 只覆盖三类创建动作，重排/完成/取消仍未接入。
- Next recommended action:
  - 开始 Phase 5：前端 `assistant.ts` 接入 proposal API，`AssistantPanel.vue` 展示 pending/executed proposal 的文本式状态，并支持确认/拒绝/修改/重试的最小交互。

## 进度更新 - 2026-05-01 03:02 +08:00

- Overall progress: Phase 5 前端 proposal surface 已完成，当前可以进入 Phase 6 稳定性与可观测性。
- Active phase: Phase 6 - Phase 1B Stability And Observability
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: pending
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - `frontend/src/stores/assistant.ts` 新增 `AssistantProposal`、`AssistantProposalOption` 类型与 proposal API 方法。
  - `frontend/src/stores/workspace.ts` 透传 proposal 状态、loading/busy 状态和 confirm/reject/revise/retry 操作。
  - `frontend/src/App.vue` 将 proposal props/events 接入桌面与移动端 `AssistantPanel`。
  - `frontend/src/components/AssistantPanel.vue` 新增轻量 proposal surface，显示 pending/executed/failed 等状态，并支持确认 option、拒绝、修改、重试。
  - `frontend/src/i18n/index.ts` 补充 proposal 相关中英文文案。
  - proposal 列表未加入 `hydrate()` 首屏主路径，只在助手面板挂载、发送后刷新、主动刷新助手状态时拉取。
- Validation result:
  - `pnpm --dir E:\GraduationProject\frontend exec vue-tsc --noEmit`: passed。
  - `pnpm --dir E:\GraduationProject\frontend run build`: passed，Vite build completed in `2.77s`。
  - `Invoke-WebRequest http://127.0.0.1:8000/api/assistant/proposals`: passed，HTTP 200。
  - `Invoke-WebRequest http://127.0.0.1:8000/api/health`: passed，HTTP 200。
  - Playwright 访问 `http://127.0.0.1:8888` 并切换助手页：passed，无 console warning/error。
- Decision updates:
  - Verified facts:
    - 前端 proposal API 类型和面板 props 已通过 `vue-tsc`。
    - 当前助手面板在没有 proposal 时不会渲染额外空状态块。
    - proposal 操作成功后会刷新 events/tasks，确保确认执行后日历/任务页可看到结果。
  - Locked decisions:
    - Phase 5 不改 WebSocket chunk 协议，不引入 `proposal_created` 事件。
    - Phase 5 不把 proposal 拉取放入 `hydrate()` 首屏主路径。
  - Open questions:
    - Phase 6 是否新增 debug 页面 proposal 观测区，还是只新增 debug API；建议优先 debug API + 后端日志，前端 debug 页面延后。
- Residual risks:
  - 当前 UI 可以操作已持久化 proposal，但聊天链路仍未在 proposal mode 下自动持久化新 proposal；需要 Phase 6/后续阶段补齐从 Conductor draft 到 persisted proposal 的安全切换。
  - `create_task_with_events` 仍缺事务补偿/部分失败观测。
  - proposal 列表目前按 API 返回 active statuses 拉取，长期历史归档与分页体验留到后续。
- Next recommended action:
  - 开始 Phase 6：补 dedup/revise/expiry/debug 可观测性，并设计从 shadow draft 到 persisted proposal 的安全启用门禁。

## 进度更新 - 2026-05-01 09:54 +08:00

- Overall progress: Phase 6 稳定性与可观测性已完成，当前可以进入 Phase 7 主动 signal 与日常节律。
- Active phase: Phase 7 - Proactive Signals And Daily Rhythm
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: pending
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - `AssistantProposalManager.create_proposal()` 增加 active `dedup_key` 去重；命中 active proposal 时复用，不再创建重复 proposal。
  - pending/draft proposal 默认补 `24h` `expires_at`，同时保留显式 `expires_at` 覆盖能力。
  - `list_proposals()`、confirm/reject/revise 前均会即时清理已到期 proposal，过期后不可确认或修改。
  - 新增 `expire_due_proposals()`，并新增 Celery 任务 `app.jobs.proposals.expire_due_assistant_proposals`，每 10 分钟清理过期 proposal。
  - proposal 状态转换增加 Loguru 结构化日志；执行失败日志保留 `proposal_id`、`option_id` 与错误原因。
  - 新增 `/api/debug/assistant/proposals`，输出 active 数量、execution_failed 数量、最近状态变化、最近执行失败与 dedup 查询信息。
  - 新增 Phase 6 测试文件：`test_assistant_proposal_dedup.py`、`test_assistant_proposal_expiry.py`、`test_assistant_proposal_revise.py`。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q`: `310 passed`。
  - 运行态 smoke：`GET http://127.0.0.1:8000/api/health` -> 200；`GET http://127.0.0.1:8000/api/assistant/proposals` -> 200；`GET http://127.0.0.1:8000/api/debug/assistant/proposals` -> 200。
  - 已重启 `graduation-project-api`、`graduation-project-celery-worker`、`graduation-project-celery-beat` 以加载新增 debug route 与 proposal expiry job。
- Decision updates:
  - Verified facts:
    - 实际后端 API 暴露在 `127.0.0.1:8000`；`127.0.0.1:8888` 当前是前端静态容器，不应作为后端 API smoke 地址。
    - Phase 6 不启用自动持久化 Conductor shadow draft，不打开未完成的 `proposal` mode。
  - Locked decisions:
    - proposal mode 的安全门禁维持为：只有 persisted proposal + 用户确认 + Action Executor 幂等执行才允许真实写入；shadow draft 不自动落库。
  - Open questions:
    - Phase 7 主动 signal 进入 proposal 前，是否需要先新增 `GET /api/assistant/signals`，建议作为 Phase 7 第一小步。
- Residual risks:
  - 聊天链路仍未把 Conductor draft 自动持久化为 proposal；Phase 7 前建议先补安全持久化入口或继续保持 `ASSISTANT_CONDUCTOR_MODE=legacy/shadow`。
  - `create_task_with_events` 仍没有全局事务补偿；Phase 6 已补失败观测，但原子性/补偿策略仍需后续处理。
  - debug API 已可查 proposal，但 `frontend/public/debug.html` 尚未增加可视化区域；目前先靠 API 与日志观察。
- Next recommended action:
  - 开始 Phase 7：先建立主动 signal 的最小 API 与 cooldown/dedup 规则，再接入 morning/night/deadline/conflict/departure 的受控生成链路。

## 进度更新 - 2026-05-01 10:10 +08:00

- Overall progress: Phase 7 已完成第一段基础设施：主动 signal API、cooldown/dedup 管理、debug heartbeat，以及三类受控后台扫描骨架。
- Active phase: Phase 7 - Proactive Signals And Daily Rhythm
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: in progress
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增 `AssistantSignalManager`，统一管理 signal 创建、active dedup、cooldown 阻断、evaluate/proposal_created/dismiss 状态转换。
  - `AssistantSignalRepository` 新增 `get_blocking_by_dedup_key()`，使 dismissed 但 cooldown 未结束的 signal 也能阻止重复生成。
  - 新增 `/api/assistant/signals`、`/api/assistant/signals/{id}`、`/api/assistant/signals/{id}/dismiss`。
  - 新增 `/api/assistant/heartbeat/run` debug 入口；它只生成或复用 signal，不创建 proposal，不写任务/日程。
  - 新增 `backend/app/jobs/assistant_signals.py`，首批包含 `deadline_risk`、`conflict_warning`、`departure_readiness` 三类扫描骨架。
  - `celery_app.py` 已 include `app.jobs.assistant_signals`，并加入三类扫描任务；默认 `ASSISTANT_PROACTIVE_MODE=off` 时 scheduled scan 明确 skipped。
  - 新增测试：`test_assistant_signals.py`、`test_assistant_signal_api.py`、`test_assistant_departure_signal.py`。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q`: `319 passed`。
  - 运行态 smoke：`GET http://127.0.0.1:8000/api/health` -> 200；`GET http://127.0.0.1:8000/api/assistant/signals` -> 200；`POST http://127.0.0.1:8000/api/assistant/heartbeat/run` -> 200。
  - 手动执行 `scan_deadline_risk_signals()`：在默认 `ASSISTANT_PROACTIVE_MODE=off` 下返回 skipped，未生成主动写入。
  - Celery worker task list 已包含 `app.jobs.assistant_signals.scan_deadline_risk_signals`、`scan_conflict_repair_signals`、`scan_departure_readiness_signals`。
- Decision updates:
  - Verified facts:
    - Signal API 可用，heartbeat debug 可创建 signal，但不会绕过 proposal/confirm 写入原则。
    - 出发相关 signal 以 `departure_time` 为触发基础，不以 `event_start` 为触发基础。
  - Locked decisions:
    - Phase 7 scheduled proactive jobs 默认受 `ASSISTANT_PROACTIVE_MODE=off` 保护；debug heartbeat 是手动验证入口，不代表主动系统正式打开。
    - Signal -> Proposal 转换暂不自动执行，下一步必须仍走 proposal-first + confirmation-before-write。
  - Open questions:
    - morning/night daily rhythm 需要补 profile wake/sleep fallback 和时间窗测试后，才能把 Phase 7 标记为完成。
- Residual risks:
  - Phase 7 尚未完成 daily morning/night rhythm，也尚未实现 signal -> proposal 的受控转换。
  - 当前 heartbeat debug 会写入 signal 表；它是调试入口，后续若接 debug 页面需要显示“仅生成 signal”。
  - Celery beat 已登记新任务，但默认 off；正式打开前还需要一次启用态端到端验证。
- Next recommended action:
  - 继续 Phase 7：补 morning/night daily rhythm 计算与测试，然后实现 signal -> proposal 的最小受控转换，确保每个主动 proposal 仍必须用户确认后才可落库。

## 进度更新 - 2026-05-01 10:35 +08:00

- Overall progress: Phase 7 第二段已完成：daily rhythm 计算、signal -> proposal 受控转换，以及主动 proposal 的最小确认闭环。
- Active phase: Phase 7 - Proactive Signals And Daily Rhythm
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: in progress
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - `assistant_signals.py` job 增加 `scan_daily_rhythm_signals`，按 profile `wake_up_time + 30min` 生成晨间确认 signal，按 `sleep_time - 30min` 生成睡前复盘 signal。
  - daily rhythm 使用用户 profile timezone；缺省 fallback 为 `08:00 / 23:30`，分别对应 `08:30` 晨间触发与 `23:00` 睡前触发。
  - `AssistantSignalManager.create_proposal_from_signal()` 可将 signal 转成 pending proposal，proposal dedup 使用 `signal_proposal:{signal_id}:{signal_type}`。
  - `ActionExecutor` 新增 `acknowledge_signal` 动作，用于确认主动 proposal 但不创建/修改任务或日程。
  - 新增 `POST /api/assistant/signals/{signal_id}/proposal`，用于受控地把 signal 转 proposal。
  - 新增测试：`test_assistant_daily_review.py`、`test_assistant_signal_to_proposal.py`，并扩展 `test_assistant_action_executor.py`。
  - 运行态 smoke 生成的 `debug:*` signal/proposal 已清理，避免污染用户实际工作台数据。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q`: `325 passed`。
  - 运行态 smoke：`GET /api/health` -> 200；`POST /api/assistant/heartbeat/run` -> 200；`POST /api/assistant/signals/{id}/proposal` -> 200；`GET /api/assistant/signals` -> 200；`GET /api/assistant/proposals` -> 200。
  - 手动执行 `scan_daily_rhythm_signals()`：默认 `ASSISTANT_PROACTIVE_MODE=off` 下返回 skipped。
  - Celery worker task list 已包含 `scan_daily_rhythm_signals`。
- Decision updates:
  - Verified facts:
    - 晨间/睡前 rhythm 已有 profile + fallback 时间窗测试。
    - Signal -> proposal 转换不会直接执行任务/日程写入；确认 proposal 时的 `acknowledge_signal` 只完成确认回执。
  - Locked decisions:
    - `acknowledge_signal` 是 Phase 7 主动协商类 proposal 的最小闭环动作，不代表用户同意重排/延期/完成任务。
    - 主动 signal job 仍默认 off，启用态端到端验证必须单独做。
  - Open questions:
    - Phase 7 是否把旧 `jobs/inbox.py` 的 proactive inbox 降级/关闭，避免与 signal 体系重复提醒。
- Residual risks:
  - Phase 7 尚未完成天气缓存策略；出发前天气建议仍未并入 signal/proposal。
  - signal -> proposal 目前生成的是保守 acknowledgement proposal，真正的 deadline recovery/reschedule 方案仍需要接 Planning Specialist。
  - 旧 proactive inbox job 仍在 Celery beat 中，后续需要确认是否降级或迁移到 signal/proposal。
- Next recommended action:
  - 继续 Phase 7：处理天气缓存策略与旧 proactive inbox 去重/降级，然后做一次 `ASSISTANT_PROACTIVE_MODE` 启用态的端到端验证。

## 进度更新 - 2026-05-01 11:27 +08:00

- Overall progress: Phase 7 已完成收口：主动 signal 的 cooldown/dedup、daily rhythm、signal -> proposal 最小闭环、出发前缓存天气上下文、旧 proactive inbox 降级，以及启用态验证均已落地。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: pending
- Change summary:
  - 新增 `backend/app/services/weather_cache.py`，用文件级 JSON cache 保存天气快照，避免出发扫描时频繁调用天气 API。
  - `ContextService` 新增 `weather_snapshot()`，并新增 `GET /api/context/weather/snapshot`；默认只读缓存，只有显式 `allow_refresh=true` 或后台同步才刷新。
  - 新增 `backend/app/jobs/weather.py` 与 Celery beat `sync-daily-weather-snapshots`，每天 06:00 同步用户 profile 中 home/work 坐标的天气快照。
  - `departure_readiness` signal 会读取缓存天气并写入 `context_json.weather_snapshot`；没有缓存时不临时调用外部 API。
  - `jobs/inbox.py` 被降级为兼容入口，默认 `ASSISTANT_LEGACY_INBOX_JOB_ENABLED=false` 时返回 skipped，避免与新 signal/proposal 主动系统重复提醒。
  - 新增测试：`test_weather_snapshot_cache.py`、`test_weather_job.py`，扩展 `test_inbox_job.py` 与 `test_assistant_departure_signal.py`。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q`: `330 passed`。
  - 运行态 smoke：`GET /api/health` -> 200；`GET /api/context/weather/snapshot?location=116.40,39.90` -> 200；`GET /api/assistant/signals` -> 200；`GET /api/assistant/proposals` -> 200。
  - 手动执行 `_generate_proactive_inbox_items()`：默认返回 `skipped`，原因是 legacy proactive inbox job disabled。
  - 手动执行 `_sync_daily_weather_snapshots()`：返回 `ok`，刷新当前 profile 坐标天气快照。
  - 手动执行 `scan_departure_readiness_signals()`：默认 `ASSISTANT_PROACTIVE_MODE=off` 下返回 skipped。
  - Celery worker task list 已包含 `app.jobs.weather.sync_daily_weather_snapshots`。
  - 新增启用态测试覆盖 `ASSISTANT_PROACTIVE_MODE=signals` 下 deadline risk signal 可生成，且仍只是 signal，不绕过 proposal/confirm 写入。
- Decision updates:
  - Verified facts:
    - 天气快照缓存默认不新增数据库迁移，符合 Phase 7 “每日同步 + 背景信息”边界。
    - 旧 proactive inbox 已默认不再生成 Reminder，除非显式打开 `ASSISTANT_LEGACY_INBOX_JOB_ENABLED=true`。
    - 主动 signal 在 off 模式不运行；启用态验证中只生成 signal，不直接写任务/日程/状态。
  - Locked decisions:
    - Phase 7 的出发前天气建议只使用缓存天气；临行扫描不得高频补拉天气 API。
    - 旧 inbox 在新主动系统下作为兼容 no-op 保留，不删除，避免破坏旧入口。
  - Open questions:
    - Phase 8 长期记忆文件的目录结构、写入候选机制和用户确认协议需要在下一步正式落地。
- Residual risks:
  - signal -> proposal 目前仍是保守 acknowledgement proposal；真正的 deadline recovery/reschedule 方案仍需接 Planning Specialist。
  - `create_task_with_events` 暂无全局事务补偿，后续需要独立处理。
  - 高德 App deeplink 与移动端实时定位仍未进入 V1 后端实现，后续应作为出行专项。
- Next recommended action:
  - 开始 Phase 8：建立 `.md` 长期记忆目录、Memory Specialist 骨架和“候选更新 -> 用户确认 -> 写入记忆文件”的最小闭环。

## 进度更新 - 2026-05-01 12:14 +08:00

- Overall progress: Phase 8 第一段已完成：长期记忆候选表、`.md` 文件存储、Memory Specialist 骨架、候选确认/拒绝 API，以及真实写入 smoke 验证均已落地。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - 新增 Alembic migration `0008_assistant_memory_candidates.py`，创建 `assistant_memory_update_candidates`。
  - `models.py` 新增 `AssistantMemoryUpdateCandidate`，状态遵循 `proposed / confirmed / rejected / written`。
  - 新增 `AssistantMemoryCandidateRepository` 和 `AssistantMemoryService`，负责候选去重、确认、拒绝和确认后写入 `.md`。
  - 新增长期记忆目录配置 `ASSISTANT_MEMORY_PATH`，默认落在 `/app/data/assistant_memory/{user}`。
  - 新增 `GET /api/assistant/memory`、`GET/POST /api/assistant/memory/candidates`、`POST /api/assistant/memory/candidates/{id}/confirm`、`POST /api/assistant/memory/candidates/{id}/reject`。
  - 新增 `MemorySpecialist` 骨架，只为显式“记住/保存”类请求准备候选 payload，不自动写文件。
  - 新增测试：`test_assistant_memory_service.py`、`test_assistant_memory_api.py`、`test_assistant_memory_specialist.py`。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api alembic upgrade head`: upgraded to `0008_assistant_memory_candidates`。
  - `docker exec graduation-project-api pytest -q`: `338 passed`。
  - 运行态 smoke：`GET /api/health` -> 200；`GET /api/assistant/memory` -> 200。
  - 真实接口 smoke：创建 `places` 记忆候选 -> `status=proposed`；确认候选 -> `status=written` 并生成 `places.md`；smoke 数据和临时 `.md` 已清理。
- Decision updates:
  - Verified facts:
    - `.md` 长期记忆不会被 Memory Specialist 自动写入；只有候选确认后才写文件。
    - 记忆文件目前为每用户 4 个固定文件：`preferences.md`、`places.md`、`habits.md`、`glossary.md`。
    - `current_origin` 等运行时位置推断不进入长期记忆；只有显式记忆候选可进入 `places.md`。
  - Locked decisions:
    - Phase 8 初版写入策略采用 append-only Markdown entry，先不做复杂结构化重写，降低覆盖用户记忆的风险。
    - 候选 API 是长期记忆写入的确认边界；`written` 才表示实际落盘成功。
  - Open questions:
    - 是否把 memory candidate 接入前端助手待确认区，还是先只保留 API/debug 验证。
    - 是否让 `Conductor` 在 `proposal` mode 中自动持久化 Memory Specialist 候选，还是下一步先走显式 API/调试入口。
- Residual risks:
  - 记忆文件目前是 append-only，尚未实现条目编辑/合并/删除。
  - Memory Specialist 只是规则骨架，尚未接入 LLM 结构化抽取和上下文证据评分。
  - 前端尚未展示 memory candidates；用户侧仍看不到记忆确认队列。
- Next recommended action:
  - 继续 Phase 8：把 memory candidates 接入前端/助手待确认区，或先让 Conductor 在安全模式下把显式“记住”请求持久化为 candidate，但仍不自动写 `.md`。

## 进度更新 - 2026-05-01 16:07 +08:00

- Overall progress: Phase 8 第二段已完成：memory candidates 已接入前端助手待确认区，用户可以在助手界面确认写入或拒绝记忆；长期记忆仍保持“候选 -> 用户确认 -> 写入 `.md`”边界。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `frontend/src/stores/assistant.ts` 新增 `AssistantMemoryCandidate` / `AssistantMemoryRead` 类型、候选列表拉取、确认写入、拒绝和 memory summary 拉取动作。
  - `frontend/src/stores/workspace.ts` 暴露 memory candidate state/actions，并在助手发送后和选择性刷新中同步 pending candidates。
  - `frontend/src/components/AssistantPanel.vue` 新增“待确认记忆”区域，展示候选类型、标题、内容、原因，并提供“写入记忆 / 不记”操作。
  - `frontend/src/App.vue` 完成桌面与移动端 props/events 接线。
  - `frontend/src/i18n/index.ts` 新增中英文长期记忆确认文案。
  - memory candidates 拉取增加 `_ts` cache-bust，避免浏览器/旧 service worker 缓存导致确认后仍显示旧候选。
- Validation result:
  - `pnpm --dir frontend exec vue-tsc --noEmit`: passed。
  - `pnpm --dir frontend run build`: passed。
  - 运行态 API smoke：创建 `places` memory candidate -> `status=proposed`；`GET /api/assistant/memory/candidates?status=proposed&limit=20` 可见；拒绝候选 -> `status=rejected`。
  - Playwright UI smoke：在本地 Vite 页面进入助手 tab 后可见“待确认记忆”和候选内容；点击“不记”后候选从界面消失；后端 proposed 列表回到 `0`。
  - 验证中发现浏览器曾注册 `127.0.0.1:5173/sw.js` 并缓存旧响应；测试环境注销 service worker 后重测通过，前端也已对候选列表加 `_ts` 防缓存。
- Decision updates:
  - Verified facts:
    - 用户侧现在能看到并处理长期记忆候选；Memory Specialist 仍不会自动写 `.md`。
    - 前端确认/拒绝只是调用候选 API；实际落盘仍由后端 `confirm_candidate()` 控制。
    - 助手首屏 hydrate 未新增 memory candidate 请求，候选只在助手面板按需加载和助手刷新时同步。
  - Locked decisions:
    - 记忆候选是独立于 proposal 的确认队列，Phase 8 先不把它强行塞进任务/日程 proposal 执行状态机。
    - pending memory candidates 必须避免缓存旧列表，否则会破坏“确认后消失”的信任感。
  - Open questions:
    - 下一步是否先让 `Conductor` 在安全模式下把显式“记住”请求持久化为 candidate，还是先增强记忆文件读取给 Planning/Memory Specialist 使用。
- Residual risks:
  - 记忆候选目前只能通过 API 或后续 Conductor 持久化产生；聊天链路尚未自动创建候选。
  - `.md` 记忆仍是 append-only，尚未支持合并、编辑、删除和冲突整理。
  - 本地存在旧 service worker 缓存时可能影响开发验证；候选 API 已加 cache-bust，但生产缓存策略后续仍应统一审视。
- Next recommended action:
  - 继续 Phase 8：让 Conductor/AssistantService 在安全模式下把显式“记住/保存”类请求持久化为 memory candidate，仍不自动写 `.md`；随后验证用户发消息 -> 前端出现待确认记忆 -> 用户确认/拒绝的完整闭环。

## 进度更新 - 2026-05-01 16:38 +08:00

- Overall progress: Phase 8 第三段已完成：显式“记住/保存”聊天请求现在会自动生成 memory candidate，并在回复中提示用户到“待确认记忆”确认；仍不会直接写入 `.md`。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantService` 新增 `memory_service` 与 `memory_specialist`，在收到用户消息后先捕获显式长期记忆请求。
  - 新增 `_capture_memory_candidates_for_message()`，只创建 `AssistantMemoryUpdateCandidate(status=proposed)`，失败时只记录 warning，不打断聊天。
  - 新增 `_append_memory_candidate_notice()`，在 REST、stream、workflow 回复中提示“已放入待确认记忆，确认后才写入长期记忆”。
  - `MemorySpecialist` 扩展 “请记住 / 请帮我记住 / 帮我记 / 记一下” 等显式表达，并清理礼貌前缀。
  - 新增 `backend/tests/test_assistant_memory_capture.py`，覆盖显式聊天请求创建 candidate、非显式请求不创建、回复提示保留确认边界。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_memory_specialist.py tests/test_assistant_memory_capture.py tests/test_assistant_conductor.py`: `11 passed`。
  - `docker exec graduation-project-api pytest -q`: `342 passed`。
  - 运行态 smoke：重启 API 后，`POST /api/assistant/message` 发送“请帮我记住我喜欢上午安排深度任务 ...” -> 生成 `preferences` / `proposed` memory candidate；回复包含“待确认记忆”；随后拒绝 smoke candidate，`GET /api/assistant/memory/candidates?status=proposed` 回到 `0`。
- Decision updates:
  - Verified facts:
    - 聊天入口现在已能把显式记忆请求推进到前端待确认队列。
    - 记忆候选创建失败不会影响正常助手回复，避免长期记忆子系统拖垮主聊天链路。
    - workflow 开启时也会附加待确认记忆提示。
  - Locked decisions:
    - 只有显式“记住/保存”请求会自动创建 memory candidate；普通“我下午三点去学校”不会被长期记忆捕获。
    - 自动捕获仍只到 `proposed`，不触发 `.md` 写入。
  - Open questions:
    - 下一步是否把已确认 `.md` 记忆读入 Planning/Context/Memory Specialist 的上下文，以提升“学校/图书馆/驾校”等常用地点理解能力。
- Residual risks:
  - `.md` 记忆读取尚未进入规划上下文，已确认记忆暂时只被存储和展示，尚不能直接改善排程理解。
  - 记忆候选仍是规则抽取，后续需要 LLM/结构化抽取增强标题、地点字段和证据。
  - append-only 记忆文件仍未支持合并、编辑、删除和冲突整理。
- Next recommended action:
  - 继续 Phase 8：实现记忆读取侧，把 confirmed `.md` 记忆摘要安全注入 assistant/conductor context，优先服务常用地点和规划偏好；同时保持运行时位置不写入长期记忆的边界。

## 进度更新 - 2026-05-01 17:00 +08:00

- Overall progress: Phase 8 第四段已完成：已确认写入 `.md` 的长期记忆现在会以只读摘要注入 assistant/conductor/workflow 外部上下文，优先服务常用地点、偏好、习惯和术语。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantMemoryService` 新增 `build_runtime_context()`，从 confirmed Markdown 记忆文件构建运行时只读摘要。
  - 运行时摘要会过滤 `candidate_id/source/confidence/reason/metadata` 等内部元数据，只保留可供助手理解的标题和正文。
  - `AssistantService` 新增 `_with_assistant_memory_context()`，将 `assistant_memory` 注入 `external_context`，读取失败只记录 warning，不阻塞聊天。
  - REST、WebSocket streaming、Conductor shadow/proposal 和 Gemini prompt 均通过统一 `external_context` 获得长期记忆摘要。
  - workflow `_run_workflow_for_message()` 支持接收外部上下文；`WorkflowNodes.collect_context()` 改为合并已有 external_context，避免天气/通勤采集覆盖 `assistant_memory`。
  - 新增测试 `test_workflow_memory_context.py`，并扩展 memory service/capture 测试。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_memory_service.py tests/test_assistant_memory_capture.py tests/test_workflow_memory_context.py tests/test_assistant_memory_specialist.py`: `13 passed`。
  - `docker exec graduation-project-api pytest -q`: `345 passed`。
  - 运行态 smoke：重启 API 后，`GET /api/health` -> `ok`；`GET /api/assistant/memory` 返回 4 类 memory file summaries；`GET /api/assistant/memory/candidates?status=proposed` -> `0`。
- Decision updates:
  - Verified facts:
    - confirmed `.md` 记忆现在能进入助手运行上下文，但仍是只读输入。
    - workflow 的天气/通勤上下文采集不会覆盖已注入的 `assistant_memory`。
    - 运行时摘要不暴露候选 ID、置信度等内部治理字段。
  - Locked decisions:
    - 记忆读取侧不改变写入边界；只有用户确认 candidate 后才会影响后续助手上下文。
    - 运行时位置、临时上下文、未确认候选都不进入 `assistant_memory`。
  - Open questions:
    - 是否在 Phase 8 收口前做一个轻量地点别名解析器，把 `places.md` 中的“学校 = ...”显式用于地点字段补全，而不是仅放入 LLM/context。
- Residual risks:
  - `.md` 摘要仍是文本级启发，不是结构化地点/偏好索引；规则链路未必能稳定利用“学校/图书馆/驾校”的具体地址。
  - append-only 记忆文件仍未支持合并、编辑、删除和冲突整理。
  - 若用户长期积累大量记忆，runtime summary 需要进一步做 token/条目优先级管理。
- Next recommended action:
  - 继续 Phase 8：做轻量地点记忆解析与规则链路接入，让 `places.md` 中常用地点别名能辅助 `_extract_location` / event payload / commute destination；保持解析只读、保守、可回退。

## 进度更新 - 2026-05-02 00:02 +08:00

- Overall progress: `proposal` mode 的真实端到端闭环已经跑通：用户消息经 WebSocket 生成 pending proposal，前端展示待确认方案，用户在 UI 点击确认后由 Action Executor 创建事件，重复确认不重复落库。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - 开发环境已用 `ASSISTANT_CONDUCTOR_MODE=proposal`、`ASSISTANT_PROACTIVE_MODE=off` 重启 API，确认 proposal mode 与主动系统关闭状态同时生效。
  - 后端真实 WS/API 链路验证：`/ws/assistant` 收到清晰日程请求后返回包含“待确认方案”的回复，并持久化 `event_creation` proposal；`POST /api/assistant/proposals/{id}/confirm` 后创建事件；重复 confirm 不创建重复事件。
  - 前端生产包重建并通过 8888 加载，清理旧 service worker/cache 后确认页面加载 `/assets/index-*.js`，不再使用 5173 Vite 开发资源。
  - 浏览器 UI 验证：助手页显示“待确认方案”，点击“确认”后 proposal `3` 进入 `executed`，事件 `78` 被创建；验证完成后已删除临时事件，pending proposal 列表为 `0`。
- Validation result:
  - `docker exec graduation-project-api pytest -q`: `352 passed`。
  - 真实后端端到端：`user_id=e2e-proposal-user-*`，proposal `2`，event `78`，WS 消息数 `11`，确认后状态 `executed`，重复确认幂等；临时事件已清理。
  - 真实前端端到端：`local-user`，proposal `3`，UI 点击确认后创建事件 `78`（“和同学见面”，2026-05-02 17:00-18:00，地点“图书馆”），随后 `DELETE /api/events/78` 清理成功。
  - 运行态健康检查：`GET /api/health` -> `ok`；`GET /api/assistant/proposals?status=pending&limit=5` -> `0`。
- Decision updates:
  - Verified facts:
    - `proposal` mode 现在不仅能生成和持久化 proposal，也已经通过真实 UI 完成“确认后落库”。
    - 前端旧 service worker/cache 会导致开发验证误加载 5173 资源；清理缓存并加载 8888 生产包后 proposal surface 正常。
    - proposal 执行回执使用状态值 `executed`，action 内部结果使用 `succeeded`。
  - Locked decisions:
    - `proposal` mode 可作为开发/演示环境的候选默认，但主动系统仍保持 `off`，不得顺手打开。
    - 端到端验证数据必须在验证后清理真实 event，避免污染用户日历。
  - Open questions:
    - 是否将前端缓存清理/版本失效策略做成正式开发文档或构建策略，避免后续验证继续被旧 service worker 干扰。
- Residual risks:
  - 浏览器缓存策略仍需统一治理；本次已手工清理，但生产/演示场景最好有明确版本刷新策略。
  - `create_task_with_events` 暂无全局事务补偿；Phase 6 已补观测，原子性/补偿策略仍需后续处理。
  - Action Executor 仍只覆盖创建类 action；重排、延期、取消、完成状态修改尚未进入 proposal-confirm-execute 闭环。
  - 偏好/习惯记忆仍主要作为上下文文本提供，尚未形成可解释的强规则约束。
- Next recommended action:
  - Phase 8 可以进入收口段：优先补前端缓存/版本刷新策略与偏好/习惯记忆的规则化消费说明；随后进入下一实施阶段，扩展重排、延期、取消、完成状态修改的 proposal-confirm-execute 闭环。

## 进度更新 - 2026-05-02 00:18 +08:00

- Overall progress: Action Executor 已扩展到“确认后调整状态/时间”的第一批动作：重排事件、取消事件、标记事件完成、标记任务完成均进入 proposal-confirm-execute 闭环。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantActionExecutor.SUPPORTED_ACTIONS` 新增 `reschedule_event`、`cancel_event`、`mark_event_completed`、`mark_task_completed`。
  - `reschedule_event` 复用 `EventService.update_event()`，要求 `event_id` 和 update payload。
  - `cancel_event` 采用 `status="canceled"`，不删除事件，保留历史与任务回算依据。
  - `mark_event_completed` 采用 `status="completed"`，并继续走事件 service 的任务进度回算。
  - `mark_task_completed` 采用 `TaskService.update_task(status="done")`。
  - 新增 update payload 校验和 target id 校验，缺失或非法 id 会返回 400。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py tests/test_assistant_proposal_manager.py`: `13 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_dedup.py tests/test_assistant_proposal_expiry.py`: `9 passed`。
  - 运行态 E2E：创建临时事件/任务 -> 通过 Proposal Manager 写入 4 个 pending proposal -> 通过真实 `/api/assistant/proposals/{id}/confirm` 确认 -> 验证事件重排为 `2026-05-03T16:00:00`、事件取消为 `canceled`、事件完成为 `completed`、任务完成为 `done`，重复确认仍为 `executed`；临时事件/任务已清理，pending proposal 为 `0`。
- Decision updates:
  - Verified facts:
    - 更新类 action 现在可由真实 proposal confirm API 执行，并保持重复确认幂等。
    - 修改 executor 源码后，正在运行的 API 进程必须重启，否则 confirm 端仍会使用旧 action type 集合。
    - 取消日程当前定义为状态更新，不是物理删除。
  - Locked decisions:
    - 状态修改也属于写操作，必须继续走 proposal confirm，不允许绕过确认。
    - 取消/完成类动作优先保留历史记录，便于睡前复盘、任务回算和后续审计。
  - Open questions:
    - 延期任务是否要建独立 `postpone_task` action，还是先用 `reschedule_event` + `TaskUpdate(deadline/preferred_period)` 组合表达。
- Residual risks:
  - 还没有把自然语言“推迟/取消/完成”稳定解析成这些新 action；当前只是执行层与确认 API 已经具备能力。
  - `create_task_with_events` 仍暂无全局事务补偿；多 action proposal 若中途失败仍需要更明确的补偿策略。
  - “取消任务”尚未定义，是 `status=canceled`、`archived`、还是删除，需要产品语义再锁定。
- Next recommended action:
  - 接入理解/规划层：让 Conductor/Planning Specialist 能把“改到明天”“取消这个日程”“这个完成了”生成对应 proposal，并在多候选事件/任务时先澄清目标。

## 进度更新 - 2026-05-02 00:41 +08:00

- Overall progress: 更新类自然语言请求已接入 Conductor/Planning Specialist：用户说“改到明天”“取消某日程”“某任务完成了”时，系统能在唯一匹配目标时生成 proposal；目标不唯一或找不到时先澄清。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `UnderstandingSpecialist` 新增更新类 intent：`reschedule_event`、`cancel_event`、`mark_event_completed`、`mark_task_completed`。
  - 更新类请求会基于当前 `events/tasks` 做保守目标匹配；标题、地点和事件时间可参与打分；多候选同分时进入澄清。
  - `PlanningSpecialist` 新增更新类 proposal 生成：`event_reschedule`、`event_cancel`、`event_status_update`、`task_status_update`。
  - `TaskOrEventClarifierSpecialist` 新增目标不明/多目标/缺新时间的澄清文案。
  - `AssistantConductor` 支持 planning 阶段返回澄清问题，避免无法生成 proposal 时回落旧链路。
  - `AssistantService` 向 `AssistantAgentContext.now` 注入应用时区时间，修正容器 UTC 导致“今天/明天”偏移的问题。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py tests/test_assistant_action_executor.py tests/test_assistant_proposal_manager.py`: `23 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_dedup.py tests/test_assistant_proposal_expiry.py`: `9 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_memory_capture.py tests/test_workflow_memory_context.py tests/test_assistant_memory_service.py`: `14 passed`。
  - 运行态 E2E：真实 HTTP 创建临时日程“E2E自然语言组会” -> 用户消息“把E2E自然语言组会改到明天下午4点” -> 生成 pending `event_reschedule` proposal -> confirm 后事件改到 `2026-05-03T16:00:00-17:30:00` -> 重复 confirm 幂等 -> 临时事件已清理，pending proposal 为 `0`。
- Decision updates:
  - Verified facts:
    - 自然语言更新请求现在可以从 Conductor 生成可确认 proposal，并复用上一段 Action Executor 的确认后执行能力。
    - “明天”等相对日期必须以应用时区为基准，不能使用容器 UTC `datetime.now()`。
    - 目标消歧当前采用保守规则；无法唯一确定时不会写入 proposal，而是要求用户补充目标。
  - Locked decisions:
    - 更新类请求必须和创建类请求一样遵守 proposal-first + confirmation-before-write。
    - 缺目标或多目标时先澄清，不能猜测用户要修改哪一个日程/任务。
  - Open questions:
    - “这个/刚才那个/下午那个”等指代类目标是否在下一步接入 thread state/session history 做上下文消解。
- Residual risks:
  - 目标匹配仍是轻量规则，复杂自然语言和模糊指代需要 thread state 或 LLM 结构化抽取增强。
  - 当前只接入单目标更新；“推迟今天所有日程”这类批量重排还未实现。
  - “取消任务”的产品语义仍未锁定，尚未实现对应 action/proposal。
- Next recommended action:
  - 继续增强目标消歧：接入 thread state/session history 支持“这个/刚才那个”等指代，并设计批量重排 proposal 的边界与补偿策略。

## 进度更新 - 2026-05-05 23:20 +08:00

- Overall progress: 指代类目标消歧已完成第一段：用户说“这个/那个/刚才那个/它”时，系统会优先使用最近会话文本中精确提到的唯一日程/任务；如果上下文仍不唯一，则继续澄清，不猜测执行。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `UnderstandingSpecialist` 的事件/任务目标解析支持最近 `history` 文本指代消解。
  - 新增保守触发词：`这个`、`那个`、`这条`、`那条`、`它`、`刚才`、`刚刚`、`上一个`、`前面那个`、`刚说的`。
  - 指代解析只接受最近会话里对候选标题/content 的精确提及；不再用“组会”这类片段从历史里猜目标。
  - 移除了“下午/上午”这种弱时间段对旧目标的打分，避免把“改到明天下午4点”误当成目标原时间线索。
  - 如果没有唯一历史指代，但当前 active event/task 只有一个，允许作为唯一目标；多个候选时继续澄清。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py`: `13 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: `7 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv`: `6 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_dedup.py tests/test_assistant_proposal_expiry.py`: `9 passed`。
  - 运行态 E2E：同一会话内先发送“取消论文组会”生成 `event_cancel` proposal，再发送“把这个改到明天下午4点”生成 `event_reschedule` proposal；确认后只把“论文组会”改到 `2026-05-06T16:00:00-17:30:00`，“项目组会”保持 `2026-05-06T09:00:00`；临时事件已删除，pending proposal 为 `0`。
- Decision updates:
  - Verified facts:
    - “这个/刚才那个”现在可通过最近会话精确标题提及解析到唯一 event/task。
    - 弱时间段不能作为目标消歧依据；它只适合表达新时间，不适合识别旧目标。
    - 已执行 proposal 不能再 expire，测试清理时出现 409 属于预期状态边界；临时真实 event 已清理。
  - Locked decisions:
    - 指代消歧宁可澄清，不使用片段匹配或弱时间段强行猜目标。
    - 批量操作暂不混入单目标消歧，避免把“今天所有日程”误解释成单个日程。
  - Open questions:
    - 是否建立正式 `active_target` thread state，保存最近被讨论的 event/task/proposal，而不是每次从历史文本回推。
- Residual risks:
  - 当前指代消解依赖历史文本精确标题；如果助手回复没有包含完整标题，仍会回到澄清。
  - 尚未支持用户直接确认/修改 pending proposal 的文本协议升级，例如“就按这个”指向当前唯一 pending proposal。
  - 批量重排、批量取消和多 action 补偿策略仍未实现。
- Next recommended action:
  - 设计并落地 `active_target` thread state：当 Conductor 生成或持久化 proposal 时记录最近相关 event/task/proposal，后续“这个/就按这个/改一下这个方案”优先走显式 thread state，而不是只扫历史文本。

## 进度更新 - 2026-05-05 23:53 +08:00

- Overall progress: `active_target` thread state 第一段已落地：Conductor proposal mode 持久化 proposal 后会把最近 proposal/event/task 写入 `AssistantThreadState(thread_type="active_target")`，后续指代类请求会优先读取结构化上下文，再回退到最近 history 精确文本匹配。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantThreadStateRepository` 新增按 `thread_type` 过滤、读取和 upsert `active_target` 的入口。
  - `AssistantService` 在构建 Conductor context 前注入 `external_context["active_target"]`。
  - `AssistantService` 在 proposal 持久化后回写 active target，保存 `proposal_id`、`proposal_type`、`proposal_status`、`event_id`、`task_id`、`summary`、`target_title` 等结构化信息。
  - `UnderstandingSpecialist` 在“这个/那个/刚才那个”等上下文指代出现时，优先用 `active_target.event_id/task_id` 解析目标；无可验证目标时再退回 history 精确标题匹配和唯一候选规则。
  - 文本协议新增保守确认入口：当前 session 有 active proposal 时，“就按这个/按这个方案”等会调用既有 `confirm_proposal` 状态机；执行资格仍由 `AssistantProposal.status` 控制。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py`: `15 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposals_repository.py`: `2 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: `7 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv`: `6 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_dedup.py tests/test_assistant_proposal_expiry.py`: `9 passed`。
  - `docker-compose up -d --force-recreate api`: completed。
  - `/api/health`: returned `ok` after API recreate。
- Decision updates:
  - `active_target` is context only; it does not make a proposal executable and does not bypass confirmation.
  - Active target lookup validates the referenced event/task against current candidate lists before using it, so stale IDs fall back to safer clarification/history behavior.
  - Text confirmation only targets the active proposal id in thread state and still routes through `AssistantProposalManager.confirm_proposal`.
- Residual risks:
  - 当前只维护每个 session 最新 active target；多 proposal 并列讨论时仍需要更完整的 active set / P 编号协议。
  - “改一下这个方案”目前主要通过 active proposal/event target 解决目标指向，尚未实现真正根据修改文本重写 proposal option 的智能 revise。
  - 本轮未跑全量后端 `pytest -q`，也未重跑前端构建。
- Next recommended action:
  - 继续扩展 pending proposal 文本协议：支持按 `P1/P2` 明确选择、对 active proposal 进行自然语言 revise，并在多个 active proposal 时强制澄清。

## 进度更新 - 2026-05-06 00:08 +08:00

- Overall progress: pending proposal 文本协议第一段已完成：用户可以用 `P1/P2` 明确选择待确认方案，也可以在唯一 pending proposal 或 active proposal 上说“就按这个”；多个 pending 且未明确编号时会澄清，不猜测执行。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantProposalRepository.list_proposals` 和 `AssistantProposalManager.list_proposals` 支持按 `session_id` 过滤 pending proposal。
  - `AssistantService` 将 active proposal 文本确认扩展为统一 proposal 文本协议处理器。
  - 支持文本确认：
    - `按P2`
    - `确认P1`
    - `就按这个`
  - 支持文本 revise：
    - `把P2改到明天下午4点`
    - `改一下这个方案`
  - revise 当前复用既有 `AssistantProposalManager.revise_proposal`：生成新的 pending proposal、旧 proposal 标记 `superseded`、把 revision request 记录进 payload，并回写 active target。
  - 多个 pending proposal 且用户只说“这个/这个方案”时，返回澄清，提示用 `P1/P2`。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py`: `18 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposals_repository.py`: `2 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: `7 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv`: `6 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_dedup.py tests/test_assistant_proposal_expiry.py`: `9 passed`。
  - `docker-compose up -d --force-recreate api`: completed。
  - `/api/health`: returned `ok` after API recreate。
- Decision updates:
  - `P1/P2` 映射只在当前 session 的 pending proposals 中生效，按 proposal id 升序形成稳定编号。
  - 单 pending proposal 可以容错“就按这个”；多个 pending proposal 必须明确编号。
  - 文本确认和文本 revise 都不绕过 `AssistantProposalManager`，执行资格继续由 proposal status 控制。
- Residual risks:
  - revise 目前仍是结构化 lifecycle revise，不是智能重写 option/action payload；真正“把方案时间改成新时间”的 option 重规划仍待实现。
  - `P1/P2` 编号是服务端文本协议映射，前端 pending proposal 展示若未同步显示同样编号，用户可能仍主要依赖“这个”。
  - 本轮未跑全量后端 `pytest -q`，也未重跑前端构建。
- Next recommended action:
  - 实现 proposal revise 的真实 option/action 重规划，尤其是 event creation / reschedule 的新时间覆盖；然后把前端 pending proposal 列表同步显示 `P1/P2` 编号。

## 进度更新 - 2026-05-06 00:30 +08:00

- Overall progress: proposal revise 的真实时间重规划已完成第一段，前端 pending proposal 列表也已同步显示 session 内 `P1/P2` 编号。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantProposalManager.revise_proposal` 现在会对 `event_creation` 的 `create_event` action 和 `event_reschedule` 的 `reschedule_event.update` action 进行时间重规划。
  - revise 会从原 action 提取旧 start/end，解析用户修改文本的新时间，保留原时长，覆盖新 proposal 的 action payload。
  - 支持只改时间不改日期的表达，例如“改到下午4点”：保留原 proposal 日期。
  - 支持带日期表达，例如“改到5月8日下午4点”：按新日期和时间覆盖。
  - revised proposal 的 summary 和 option summary 会反映新时间，并在 payload 中记录 `revision.type = event_time_update`。
  - proposal list API 支持 `session_id` 过滤；前端 `fetchAssistantProposals` 会传当前 session id。
  - 前端 pending proposal 列表按当前 session 内 pending proposal id 升序显示 `P1/P2`；非 pending proposal 使用 `#id`，避免误导文本确认。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_revise.py`: `4 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_revise.py tests/test_assistant_proposal_api.py tests/test_assistant_conductor.py`: `24 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv`: `6 passed`。
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: `7 passed`。
  - `cd frontend; pnpm exec vue-tsc --noEmit`: passed。
  - `cd frontend; pnpm run build`: passed。
  - `docker-compose up -d --force-recreate api`: completed。
  - `/api/health`: first request during startup ended prematurely, retry returned `ok`。
- Decision updates:
  - revise 仍复用 proposal lifecycle：旧 proposal -> `superseded`，新 proposal -> `pending`，确认后才执行。
  - 当前只对事件创建/重排的时间字段做真实重规划；不在这一段混入地点、标题、任务拆分等更广义修改。
  - 前端展示的 `P1/P2` 只对 pending proposal 生效，和后端文本协议保持一致。
- Residual risks:
  - 复杂 revise（改地点、改标题、改任务拆分、改多 action proposal）仍只是 lifecycle revise 或后续需要专门规划。
  - 批量重排/批量取消 proposal 尚未实现。
  - 本轮未跑全量后端 `pytest -q`。
- Next recommended action:
  - 进入批量重排/批量取消 proposal 的边界设计与实现，明确确认文案、目标列表展示和部分失败补偿策略。

## 进度更新 - 2026-05-06 01:43 +08:00

- Overall progress: 批量取消 proposal 与批量“整体推迟/提前 N 天”重排 proposal 已完成第一版，继续保持 proposal 优先与确认后执行。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `UnderstandingSpecialist` 新增受限批量 event target 解析：只有包含“所有/全部/当天/这天”等批量语义并带明确日期引用时，才会选中某一天的 active events。
  - 批量取消支持“取消明天所有日程”一类表达；无日期范围会澄清，不会猜测全局取消。
  - 批量重排第一版支持“把明天所有日程推迟一天/提前两天”一类整体平移语义，保留每个日程原本开始时间、结束时间和时长。
  - `PlanningSpecialist` 新增 `event_batch_cancel` 与 `event_batch_reschedule` proposal，单个 proposal option 内包含多个既有 executor action。
  - `TaskOrEventClarifier` 新增批量日期缺失、批量过大、批量重排缺少移动规则的澄清文案。
  - `tests/test_assistant_conductor.py` 增加批量取消、无日期澄清、批量整体顺延、缺少 shift rule 澄清测试。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py`: passed，`22 passed`.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: passed，`7 passed`.
  - `docker-compose up -d --force-recreate api`: completed；`curl.exe http://localhost:8000/api/health`: HTTP 200，`status=ok`.
- Decision updates:
  - Verified facts:
    - 当前批量 proposal 复用既有 Action Executor 的逐 action 执行能力，不新增未确认写入路径。
  - Locked decisions:
    - 批量重排第一版只支持“整体推迟/提前 N 天”，暂不把“明天所有日程改到后天”解释为精确批量改期，避免目标日期/原日期解析歧义。
    - 批量目标上限暂定 8 个，超过则澄清要求缩小范围。
  - Open questions:
    - 批量 action 的部分失败补偿策略仍未定稿。
- Residual risks:
  - 批量 proposal confirm 仍是逐 action 顺序执行；若中途失败，前面 action 可能已经生效，尚无全局事务补偿。
  - “把明天所有日程改到后天”这类精确批量改期尚未支持，需要后续专门解析 source date 与 destination date。
  - 本轮未跑全量后端 `pytest -q`，也未重跑前端构建。
- Next recommended action:
  - 继续做批量 action 的部分失败补偿/回滚策略，或先补精确批量改期（source date -> destination date）的解析与测试。

## 进度更新 - 2026-05-06 04:14 +08:00

- Overall progress: 更新类 action 的部分失败补偿底座已完成第一版；多 action proposal 中若后续 action 失败，已成功的 event/task 更新 action 会按反序尝试恢复。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Execution readiness: executing
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Change summary:
  - `AssistantActionExecutor.execute` 新增 rollback stack：每个可补偿更新 action 成功后记录 compensation，后续 action 失败时反序回滚。
  - `reschedule_event`、`cancel_event`、`mark_event_completed`、`mark_task_completed` 在服务支持 `get_event/get_task` 时会读取更新前快照，并在结果中携带 `compensation`。
  - 回滚失败不会吞掉原始失败；原始 `HTTPException.detail` 会附带 `failed_action_index` 与 `rollback` 明细，便于 proposal execution 失败观测。
  - 创建类 action 暂不自动删除/回滚，避免在无明确事务边界时误删用户数据。
  - `tests/test_assistant_action_executor.py` 新增后续 action 失败时回滚已成功 reschedule 的测试。
- Validation result:
  - `docker exec graduation-project-api python -m compileall app`: passed.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py`: passed，`8 passed`.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv`: passed，`6 passed`.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py`: passed，`22 passed`.
  - `docker-compose up -d --force-recreate api`: completed；`curl.exe http://localhost:8000/api/health`: HTTP 200，`status=ok`.
- Decision updates:
  - Verified facts:
    - 更新类 action 的局部回滚可以在 executor 层完成，不需要改变 proposal confirm 的确认前置约束。
  - Locked decisions:
    - 第一版补偿只覆盖可安全恢复旧字段的更新类 action；创建类 action 与 `create_task_with_events` 全局事务补偿继续单独处理。
  - Open questions:
    - 是否要为创建类 action 引入显式 `compensation_policy`，例如只删除本 proposal 创建且没有后续用户编辑的对象。
- Residual risks:
  - 回滚依赖 service 的 `get_event/get_task` 可用；若注入的 fake/外部服务没有读取接口，executor 会执行但不登记该 action 的自动补偿。
  - 回滚仍可能因数据库/服务异常失败；当前只记录 `rollback_failed`，不重试。
  - `create_task_with_events` 仍无全局事务补偿。
  - 本轮未跑全量后端 `pytest -q`，也未重跑前端构建。
- Next recommended action:
  - 补精确批量改期（source date -> destination date）的解析与测试，或继续细化创建类 action / `create_task_with_events` 的显式补偿策略。

## 决策记录

- Verified facts:
  - 后端入口是 `E:\GraduationProject\backend\app\main.py`。
  - API router 当前在 `E:\GraduationProject\backend\app\api\router.py` 统一挂载。
  - 现有 assistant routes 在 `E:\GraduationProject\backend\app\api\routes\assistant.py`。
  - 现有 assistant service 主体在 `E:\GraduationProject\backend\app\services\assistant.py`。
  - 当前 DB model 在 `E:\GraduationProject\backend\app\models.py`。
  - 当前 Alembic versions 在 `E:\GraduationProject\backend\alembic\versions`。
  - Celery beat 当前在 `E:\GraduationProject\backend\app\core\celery_app.py` 配置。
  - 前端助手面板在 `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`。
  - 前端助手 store 在 `E:\GraduationProject\frontend\src\stores\assistant.ts`。
  - Phase 0 基线验证已通过；当前 Alembic head 为 `1d052940e0a7`。
  - Docker API 容器内 Python 为 `3.11.15`，pytest 为 `8.3.5`。
  - Phase 1 已完成，当前 Alembic head 为 `0007_assistant_proposal_foundation`。
  - Phase 2 已完成，`GET /api/assistant/proposals` 在实际 API 容器中返回 HTTP 200。
  - Phase 3 已完成，`AssistantService` 可在 `shadow` 模式运行 Conductor，不改变旧助手输出。
  - Phase 4 已完成，`AssistantProposalManager` 可在 confirm/retry 后通过 Action Executor 执行最小创建动作。
  - Phase 5 已完成，前端助手面板可展示和操作已持久化 proposal。
  - Phase 7 已完成，主动 signal、daily rhythm、天气快照、旧 inbox 降级和启用态验证均已通过。
  - Phase 8 第一段已完成，长期记忆候选确认后可写入 `.md` 文件。
  - Phase 8 第二段已完成，前端助手面板可展示和处理 memory candidates。
  - Phase 8 第三段已完成，显式“记住/保存”聊天请求可自动生成 proposed memory candidate。
  - Phase 8 第四段已完成，confirmed `.md` 记忆可作为只读摘要进入 assistant/conductor/workflow context。
  - Phase 8 第五段已完成，confirmed `places.md` 地点别名可只读解析并进入事件 payload / workflow location 槽位 / 通勤目的地链路。
  - Conductor proposal mode 安全持久化入口已完成：`ASSISTANT_CONDUCTOR_MODE=proposal` 下 proposal/clarification 会短路旧直接写入链路，proposal draft 会持久化为 `AssistantProposal`。
  - `proposal` mode 真实端到端已通过：WS 生成 proposal、前端展示待确认方案、UI 确认后创建事件、重复确认幂等、验证事件已清理。
  - Action Executor 更新类动作已完成第一批：`reschedule_event`、`cancel_event`、`mark_event_completed`、`mark_task_completed` 均通过真实 confirm API 验证。
  - 更新类自然语言请求已接入 Conductor/Planning Specialist，唯一目标可生成 proposal，多目标/未找到会澄清。
  - `AssistantAgentContext.now` 已使用应用时区时间，避免“明天”被容器 UTC 日期误算。
  - 指代类目标消歧已接入最近会话历史，且只接受精确标题/content 提及或唯一候选。
  - 批量取消与批量整体顺延 proposal 第一版已完成：要求明确日期范围，批量重排仅支持“整体推迟/提前 N 天”，确认后复用既有 executor action。
  - 更新类 action 的部分失败补偿第一版已完成：后续 action 失败时，已成功的 event/task 更新 action 会按反序尝试恢复旧快照。
- Active assumptions:
  - Phase 1A 以单用户本地原型边界实现，`local-user` 仍是默认用户。
  - SQLite 仍是近期运行数据库，因此复杂唯一约束优先放 service 层处理。
  - Gemini/LLM 调用可用，但 Phase 1A 必须具备规则/保守 fallback，不能完全依赖外部模型成功。
  - 旧助手链路暂时保留，直到 proposal mode 完成回归验证。
- Locked decisions:
  - 所有写操作必须确认后执行。
  - `AssistantProposal.status` 是执行资格的唯一业务状态来源。
  - Phase 1A 不新增 `AssistantActionExecution` 表。
  - 主动系统默认仍由 `ASSISTANT_PROACTIVE_MODE=off` 保护，显式启用前不得向用户形成主动协商压力。
  - 长期记忆写入必须走候选确认；Memory Specialist 不允许直接自动写 `.md`。
  - memory candidates 是独立确认队列，前端不得把它等同于任务/日程 proposal 执行状态机。
  - 只有显式记忆请求进入 candidate 捕获；运行时位置和普通日程内容不得被自动写入长期记忆候选。
  - 已确认记忆的读取侧只能作为上下文输入，不改变写入确认边界。
  - Phase 1A 不实现 recurrence engine。
  - 前端交互文本优先，不依赖按钮。
- Open questions:
  - `ASSISTANT_CONDUCTOR_MODE` 是否进入 `.env.example` 或只在 config 默认值中体现。
  - Phase 4 是否需要立刻扩展 `Task/Event` 元数据，还是延后到 Phase 1B。
  - Debug 页面是否在 Phase 1B 接 proposal 观测，还是仅先加 debug API。
  - 高德 App deeplink 是否进入 Phase 7，还是作为移动端后续专项。

## 关键制品与环境

- Canonical docs:
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_REDESIGN_PLAN_V1.md`: 已收口设计稿。
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_IMPLEMENTATION_TASK_BOOK_V1.md`: 本实施任务书与进度主文件。
- Important code or output artifacts:
  - `E:\GraduationProject\backend\app\models.py`: 新增 ORM 实体。
  - `E:\GraduationProject\backend\app\api\schemas.py`: 新增 API schema。
  - `E:\GraduationProject\backend\alembic\versions\0007_assistant_proposal_foundation.py`: Phase 1 核心表迁移。
  - `E:\GraduationProject\backend\app\repositories\assistant_proposals.py`: Proposal repository。
  - `E:\GraduationProject\backend\app\repositories\assistant_signals.py`: Signal repository。
  - `E:\GraduationProject\backend\app\repositories\assistant_thread_states.py`: Thread state repository。
  - `E:\GraduationProject\backend\app\services\assistant_proposal_manager.py`: Proposal lifecycle manager。
  - `E:\GraduationProject\backend\app\services\assistant_signal_manager.py`: Signal lifecycle manager。
  - `E:\GraduationProject\backend\app\api\routes\assistant_proposals.py`: Proposal API routes。
  - `E:\GraduationProject\backend\app\api\routes\assistant_signals.py`: Signal API routes。
  - `E:\GraduationProject\backend\app\jobs\assistant_signals.py`: Proactive signal generation jobs。
  - `E:\GraduationProject\backend\app\assistant_agents\contracts.py`: Conductor/specialist 数据契约。
  - `E:\GraduationProject\backend\app\assistant_agents\registry.py`: Specialist registry。
  - `E:\GraduationProject\backend\app\assistant_agents\conductor.py`: 被动 Conductor 调度入口，proposal mode 结果携带持久化元数据。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`: 最小结构化理解 specialist。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`: 澄清 specialist。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\planning.py`: 内存 proposal draft 规划 specialist。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\proposal_manager.py`: proposal draft 标号与 dedup 准备 specialist。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\negotiation.py`: 纯文本协商 specialist。
  - `E:\GraduationProject\backend\app\assistant_agents\action_executor.py`: Phase 4 确认后执行器。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`: Conductor routing、proposal mode 持久化与短路保护 tests。
  - `E:\GraduationProject\backend\tests\test_assistant_specialists.py`: Specialist registry/planning tests。
  - `E:\GraduationProject\backend\tests\test_assistant_text_protocol.py`: Proposal 文本协议 tests。
  - `E:\GraduationProject\backend\tests\test_assistant_action_executor.py`: Action Executor tests。
  - `E:\GraduationProject\frontend\src\stores\assistant.ts`: Proposal API/types 接入。
  - `E:\GraduationProject\frontend\src\stores\workspace.ts`: Proposal state/actions facade。
  - `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`: Proposal surface。
  - `E:\GraduationProject\frontend\src\App.vue`: Proposal props/events 接入。
  - `E:\GraduationProject\frontend\src\i18n\index.ts`: Proposal 文案。
  - `E:\GraduationProject\frontend\src\stores\assistant.ts`: Memory candidate API/types 接入。
  - `E:\GraduationProject\frontend\src\stores\workspace.ts`: Memory candidate state/actions facade。
  - `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`: Memory candidate 待确认区。
  - `E:\GraduationProject\backend\app\services\assistant.py`: 显式记忆请求捕获与回复提示。
  - `E:\GraduationProject\backend\app\services\assistant_memory.py`: 长期记忆 runtime context 摘要与 confirmed 地点别名解析。
  - `E:\GraduationProject\backend\app\services\assistant_runtime_plan.py`: 规则计划中接入地点记忆富化。
  - `E:\GraduationProject\backend\app\workflow\nodes.py`: workflow parse/schedule 节点接入地点记忆富化并保留 assistant memory context。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\memory.py`: Memory candidate payload 抽取。
  - `E:\GraduationProject\backend\tests\test_assistant_memory_capture.py`: 显式聊天记忆捕获测试。
  - `E:\GraduationProject\backend\tests\test_workflow_memory_context.py`: workflow 保留 assistant memory context 测试。
  - `E:\GraduationProject\backend\tests\test_assistant_proposal_manager.py`: Proposal Manager tests。
  - `E:\GraduationProject\backend\tests\test_assistant_proposal_api.py`: Proposal API tests。
  - `E:\GraduationProject\backend\tests\test_assistant_proposals_repository.py`: Proposal/thread repository tests。
  - `E:\GraduationProject\backend\tests\test_assistant_signals_repository.py`: Signal repository tests。
  - `E:\GraduationProject\backend\app\api\routes\assistant.py`: 保留旧入口，接入 proposal mode。
  - `E:\GraduationProject\backend\app\api\routes\assistant_proposals.py`: 建议新增 proposal API。
  - `E:\GraduationProject\backend\app\services\assistant.py`: 新旧 assistant 总入口衔接。
  - `E:\GraduationProject\backend\app\assistant_agents`: 建议新增多智能体实现目录。
  - `E:\GraduationProject\backend\app\jobs\reminders.py`: 后续主动 signal 可复用风险扫描逻辑。
  - `E:\GraduationProject\backend\app\jobs\inbox.py`: 后续应被 signal/proposal 机制吸收或降级。
  - `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`: 展示 proposal 和文本确认。
  - `E:\GraduationProject\frontend\src\stores\assistant.ts`: 接入 proposal API / WS 事件。
- Required commands:
  - `cd E:\GraduationProject\backend; alembic heads`: 确认迁移头。
  - `cd E:\GraduationProject\backend; alembic upgrade head`: 应用迁移。
  - `cd E:\GraduationProject\backend; python -m compileall app`: 后端语法检查。
  - `cd E:\GraduationProject\backend; pytest tests/test_assistant_service.py tests/test_api.py`: 旧助手与 API 回归基线。
  - `cd E:\GraduationProject\frontend; pnpm exec vue-tsc --noEmit`: 前端类型检查。
  - `cd E:\GraduationProject\frontend; pnpm run build`: 前端构建检查。
- Environment baseline:
  - 后端：FastAPI + Async SQLAlchemy + Alembic + Pydantic v2。
  - 队列：Celery + Redis。
  - 前端：Vue 3 + Pinia + Vite + FullCalendar。
  - Docker Compose 中 API 端口为 `8000`，前端端口为 `8888`。
  - 当前数据库模式仍是 SQLite，Docker 内路径为 `/app/data/app.db`。

## 进度台账

- Overall progress: Conductor proposal draft 持久化安全入口、真实端到端闭环、更新类 Action Executor 第一批动作、更新类自然语言规划入口、指代类目标消歧第一段、`active_target` thread state 第一段、pending proposal 文本协议第一段、proposal revise 时间/标题/地点重规划第一段、前端 `P1/P2` 编号显示、批量取消 proposal 第一版、批量整体顺延 proposal 第一版、精确批量改期（source date -> destination date）第一版、更新类 action 部分失败补偿第一版、创建类 action / `create_task_with_events` 显式补偿第一版、以及前端缓存/版本刷新策略第一版均已完成；`proposal` mode 下清晰请求会生成 pending proposal，前端可展示并确认，确认后 Action Executor 可创建、重排、取消和完成事项且重复确认幂等，Phase 8 收口验证已通过。
- Phase 0 - Baseline Freeze And Guardrails: `done`
- Phase 1 - Data Foundation And Migration: `done`
- Phase 2 - Proposal API And Manager: `done`
- Phase 3 - Passive Conductor And Specialist Registry: `done`
- Phase 4 - Action Executor And Confirmed Write Path: `done`
- Phase 5 - Frontend Proposal Surface: `done`
- Phase 6 - Phase 1B Stability And Observability: `done`
- Phase 7 - Proactive Signals And Daily Rhythm: `done`
- Phase 8 - Long-Term Memory And Personalization: `done`
- Validation status: Phase 0、Phase 1、Phase 2、Phase 3、Phase 4、Phase 5、Phase 6、Phase 7 验证均通过；Phase 8 第一段后端全量回归 `338 passed`，`compileall app` 通过，Alembic head 为 `0008_assistant_memory_candidates`，实际 API 容器中 `/api/health`、`/api/assistant/memory` 均返回 HTTP 200；Phase 8 第二段前端 `vue-tsc --noEmit` 和 `pnpm run build` 通过，Playwright 验证 pending memory candidate 可显示并可拒绝后消失；Phase 8 第三段后端全量回归 `342 passed`，运行态聊天 smoke 可生成并清理 proposed memory candidate；Phase 8 第四段后端全量回归 `345 passed`，运行态 smoke 显示 API 健康且 proposed candidate 为 `0`；Phase 8 第五段 `compileall app` 通过，相关回归 `14 passed`、宽 assistant/workflow 回归 `92 passed`、后端全量回归 `350 passed`，API 重启后 `/api/health` 与 `/api/assistant/memory` 均成功；Conductor proposal 持久化段 `compileall app` 通过，目标回归 `18 passed`、组合回归 `74 passed`、后端全量回归 `352 passed`，API 重启后 `/api/health` 与 `/api/assistant/proposals` 均成功；真实 WS/API 端到端与 Playwright 前端 UI 端到端均已通过，验证事件已清理，当前 pending proposals 为 `0`；更新类 action 段 `compileall app` 通过，目标回归 `13 passed`，proposal 外围回归 `9 passed`，真实 confirm API E2E 通过且临时数据已清理；自然语言更新规划段 `compileall app` 通过，目标回归 `23 passed`、proposal 外围回归 `9 passed`、memory/workflow 回归 `14 passed`，真实 HTTP E2E 通过且相对日期按应用时区正确计算；指代消歧段 `compileall app` 通过，conductor 回归 `13 passed`、executor 回归 `7 passed`、proposal manager 回归 `6 passed`、proposal 外围 `9 passed`，真实会话 E2E 通过且临时数据已清理；active_target 段 `compileall app` 通过，conductor 回归 `15 passed`、thread repository `2 passed`、executor `7 passed`、proposal manager `6 passed`、proposal 外围 `9 passed`，API recreate 后 `/api/health` 返回 `ok`；proposal 文本协议段 `compileall app` 通过，conductor/protocol 回归 `18 passed`、thread/proposal repository `2 passed`、executor `7 passed`、proposal manager `6 passed`、proposal 外围 `9 passed`，API recreate 后 `/api/health` 返回 `ok`；proposal revise 时间重规划段 `compileall app` 通过，revise/API/conductor 组合 `24 passed`、proposal manager `6 passed`、executor `7 passed`、前端 `vue-tsc --noEmit` 与 `pnpm run build` 均通过，API recreate 后 `/api/health` 重试返回 `ok`；批量 proposal 第一版 `compileall app` 通过，conductor 回归 `22 passed`，executor 回归 `7 passed`；更新类部分失败补偿段 `compileall app` 通过，executor 回归 `8 passed`，proposal manager 回归 `6 passed`，conductor 回归 `22 passed`；精确批量改期段 `compileall app` 通过，conductor 回归 `24 passed`，executor 回归 `8 passed`，proposal manager 回归 `6 passed`；创建类 action / `create_task_with_events` 显式补偿段 `compileall app` 通过，executor 回归 `10 passed`，proposal manager 回归 `6 passed`，conductor 回归 `24 passed`；前端缓存/版本刷新策略段 `pnpm exec vue-tsc --noEmit` 与 `pnpm run build` 均通过；proposal revise 标题/地点重规划段 `compileall app` 通过，revise 专项 `6 passed`，proposal manager `6 passed`，proposal API + conductor `26 passed`，API recreate 后 `/api/health` 返回 `ok`；Phase 8 收口验证：后端全量 `docker exec graduation-project-api pytest -q` -> `382 passed`，前端 `pnpm exec vue-tsc --noEmit` 与 `pnpm run build` 均通过。
- Residual risks:
  - 前端缓存/版本刷新策略已补第一版：开发环境会注销旧 service worker 并删除 `ma-ipaas-*` cache；生产 service worker 使用 network-first，不缓存 `/api/` 与 `/ws`，并在新版本激活后刷新页面。
  - 创建类 action / `create_task_with_events` 已有显式补偿第一版：只删除本 proposal 刚创建出的对象；若删除本身失败会记录 rollback failure，不会误碰既有用户数据。
  - SQLite + API + Celery 共享写入仍可能导致并发抖动，主动系统上线前要重点观察。
  - LLM 结构化抽取失败时必须有澄清/保守 fallback，否则会重现“无法识别简单日程”的体验问题。
  - Phase 8 长期记忆已接前端确认区、显式聊天候选持久化、confirmed `.md` 只读上下文注入和地点别名解析；但偏好/习惯记忆仍主要以上下文文本提供，尚未形成强规则约束。
  - `active_target` thread state 已接入最近 proposal/event/task，`P1/P2` 文本选择和基础自然语言 revise 协议已接入；event creation/reschedule 的时间/标题/地点 revise 已能真实重规划 option/action payload，但任务拆分类和更复杂多 action revise 仍待增强。
  - 批量 proposal 已覆盖带日期范围的批量取消、整体推迟/提前 N 天、以及“把明天所有日程改到后天”这类 source date -> destination date 精确改期；更复杂的批量筛选条件（按地点/标题/类别）仍待后续增强。更新类 action 与创建类 action 均已有部分失败补偿第一版，但底层数据库级事务原子性仍未引入。

## 下一步动作

下一步不再建议沿“补关键词 / 补路由 / 补模板澄清”方向继续增强。当前最优先动作应切换为 `Phase 9 - Model-Driven Orchestration Refactor`：先完成架构重审、定义模型主导的统一主控中间态，再逐步退役旧规则链路。

## 进度更新 - 2026-05-06 05:08 +08:00

- Overall progress: 精确批量改期（source date -> destination date）第一版已完成；“把明天所有日程改到后天”会使用明天作为源日期筛选当天 event，使用后天作为目标日期，生成 `event_batch_reschedule` proposal，确认前不会写入。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - 批量 reschedule now extracts explicit source/destination dates around `改到/改成/调整到/挪到/推迟到/提前到/延期到`.
    - 批量“改/调整/挪/移动”类请求会进入 update 意图；缺少目标日期或整体移动规则时继续澄清，不猜测。
    - 只有目标日期但没有源日期的“把所有日程改到后天”会澄清日期范围，不会把目标日期误当成源日期筛选。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\planning.py`
    - `event_batch_reschedule` can now rebuild each action by preserving original time/duration and replacing the date with `batch_destination_date`.
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增/更新精确批量改期 proposal 测试，并保留缺移动规则时的澄清测试。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `24 passed`
  - `docker exec graduation-project-api python -m compileall app` -> passed
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py` -> `8 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv` -> `6 passed`
  - `docker-compose up -d --force-recreate api` -> completed
  - `curl.exe -v http://127.0.0.1:8000/api/health` -> HTTP 200, `status=ok`
- Open risks / remaining work:
  - 复杂 proposal revise 仍只完成时间重规划第一段，地点/标题/任务拆分/多 action revise 还没增强。
  - `create_task_with_events` 仍无全局事务补偿；创建类 action 的补偿边界需要明确策略。
  - 前端缓存/service worker/版本刷新策略仍未正式补。
  - 本轮未跑后端全量 `pytest -q`，也未重新跑前端 `vue-tsc` / build。
- Next recommended action:
  - 优先实现 `create_task_with_events` / 创建类 action 的显式补偿策略与测试，或先补前端缓存/版本刷新策略。

## 进度更新 - 2026-05-06 05:42 +08:00

- Overall progress: 创建类 action / `create_task_with_events` 显式补偿第一版已完成；后续 action 失败时会反序删除本 proposal 刚创建出的 event/task，`create_task_with_events` 内部 event 创建失败时也会即时清理已创建的 event 和 task。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\action_executor.py`
    - `create_event` / `create_task` 成功后登记 `delete_event` / `delete_task` compensation。
    - `create_task_with_events` 成功后登记 composite compensation，删除顺序为 event -> task。
    - `create_task_with_events` 内部失败时会立即执行 composite rollback，并在 `HTTPException.detail` 中带回 rollback 结果。
  - `E:\GraduationProject\backend\tests\test_assistant_action_executor.py`
    - 新增内部 event 创建失败回滚测试。
    - 新增 `create_task_with_events` 成功后后续 action 失败时的统一 rollback stack 测试。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_action_executor.py` -> `10 passed`
  - `docker exec graduation-project-api python -m compileall app` -> passed
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv` -> `6 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `24 passed`
  - `docker-compose up -d --force-recreate api` -> completed
  - `curl.exe -v http://127.0.0.1:8000/api/health` -> HTTP 200, `status=ok`
- Open risks / remaining work:
  - 补偿仍是服务层 best-effort，不是数据库事务；若删除补偿本身失败，会记录 rollback failure，需要人工/后续重试处理。
  - 复杂 proposal revise 仍只完成时间重规划第一段，地点/标题/任务拆分/多 action revise 还没增强。
  - 前端缓存/service worker/版本刷新策略仍未正式补。
  - 本轮未跑后端全量 `pytest -q`，也未重新跑前端 `vue-tsc` / build。
- Next recommended action:
  - 优先补前端缓存/版本刷新策略，或继续增强复杂 proposal revise。

## 进度更新 - 2026-05-06 06:08 +08:00

- Overall progress: 前端缓存/版本刷新策略第一版已完成；旧 service worker/cache 导致 8888 页面误加载 5173 Vite 资源的风险已被正式收口。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress
- Files changed in this step:
  - `E:\GraduationProject\frontend\src\platform\pwa.ts`
    - 开发环境不再注册 SW，并会在 load 后注销既有 SW、删除 `ma-ipaas-*` cache。
    - 生产环境注册 SW 后会主动 `update()`；检测到新 SW installed 后发送 `SKIP_WAITING`，`controllerchange` 时刷新页面。
  - `E:\GraduationProject\frontend\public\sw.js`
    - cache name 升级为 `ma-ipaas-v2`，激活时清理旧 `ma-ipaas-*` cache。
    - fetch 策略改为 network-first；不拦截跨源、`/api/`、`/ws` 请求，避免缓存接口响应和开发资源。
- Validation:
  - `pnpm exec vue-tsc --noEmit` -> passed
  - `pnpm run build` -> passed
- Open risks / remaining work:
  - 复杂 proposal revise 仍只完成时间重规划第一段，地点/标题/任务拆分/多 action revise 还没增强。
  - 本轮未跑后端全量 `pytest -q`。
- Next recommended action:
  - 继续增强复杂 proposal revise，优先从 event location/title revise 或 multi-action revise 里选一个保守子集。

## 进度更新 - 2026-05-06 06:54 +08:00

- Overall progress: 复杂 proposal revise 第一段已扩展到 event 标题/地点修改；event creation 与 event reschedule 的 revise 现在可组合改时间、标题、地点，并继续生成新的 pending proposal，确认前不写入。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: in progress / ready to close after broader regression
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant_proposal_manager.py`
    - `_build_revised_payload` now collects event revision fields instead of only time.
    - `create_event` payload and `reschedule_event.update` can receive revised `start_time` / `end_time` / `title` / `location_name`.
    - Summary builder now reports modified time/title/location in one concise suffix.
    - Location extraction avoids treating obvious date/time phrases like “下午4点” as a location.
  - `E:\GraduationProject\backend\tests\test_assistant_proposal_revise.py`
    - Updated time revise assertion for `event_payload_update`.
    - Added event creation title/location revise test.
    - Added event reschedule time + location revise test.
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_revise.py` -> `6 passed`
  - `docker exec graduation-project-api python -m compileall app` -> passed
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py -vv` -> `6 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_conductor.py` -> `26 passed`
  - `docker-compose up -d --force-recreate api` -> completed
  - `curl.exe -v http://127.0.0.1:8000/api/health` -> HTTP 200, `status=ok`
- Open risks / remaining work:
  - 任务拆分类 proposal revise 与更复杂多 action proposal revise 还没做深度重规划。
  - 本轮未跑后端全量 `pytest -q`，也未重新跑前端 build。
- Next recommended action:
  - 做 Phase 8 收口验证：至少串行跑后端全量 `pytest -q`，再跑前端 `vue-tsc` / build；若通过，可把 Phase 8 标记为 done 或 ready-for-final-review。

## 进度更新 - 2026-05-06 07:12 +08:00

- Overall progress: Phase 8 收口验证已完成并通过；Phase 8 - Long-Term Memory And Personalization 标记为 `done`。
- Active phase: Phase 8 - Long-Term Memory And Personalization
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: done
- Validation:
  - `docker exec graduation-project-api pytest -q` -> `382 passed`
  - `pnpm exec vue-tsc --noEmit` -> passed
  - `pnpm run build` -> passed
- Remaining enhancement backlog:
  - 任务拆分类 proposal revise 与更复杂多 action proposal revise 仍可继续增强，但不阻塞 Phase 8 收口。
  - 更新类/创建类补偿目前是 service-level best-effort，不是数据库事务；失败会记录 rollback failure。
  - 更复杂批量筛选条件（按地点/标题/类别）仍可作为后续阶段增强。
- Next recommended action:
  - 进入后续阶段规划或最终集成审查；如果继续实现功能增强，优先从任务拆分类 / 更复杂多 action proposal revise 选一个保守子集。

## 进度更新 - 2026-05-06 17:11 +08:00

- Overall progress: Phase 8 收口后已完成一次架构级复审；结论是当前系统虽然具备 proposal-first、confirm-before-write、基础执行器和长期记忆候选，但主控理解与协商权仍被多套规则链路和 legacy fallback 分裂控制，不能再继续沿“补关键词/补路由”方向演进。下一阶段正式切换为 `Phase 9 - Model-Driven Orchestration Refactor`。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: done
  - Phase 9 - Model-Driven Orchestration Refactor: in progress
- Files changed in this step:
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_MODEL_DRIVEN_REFACTOR_REVIEW_V1.md`
    - 新增模型主导重构审查书，明确当前系统的 4 个结构性问题：决策权分裂、理解层硬路由、proposal schema 无法承载任务 continuation、澄清/协商模板化。
    - 给出“模型先整理语义，规则后置校验”的目标架构原则。
    - 给出 Phase 9A-9D 迁移路线：模型主导理解层、proposal shape 扩展、模型生成澄清、legacy path 退役。
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_IMPLEMENTATION_TASK_BOOK_V1.md`
    - 更新当前 active phase / execution readiness。
    - 在阶段依赖表中新增 `Phase 9 - Model-Driven Orchestration Refactor`。
    - 将“下一步动作”从局部功能增强切换为架构级重构。
- Validation:
  - 本轮是架构复审与规划文档更新，不引入运行时代码改动，因此未新增代码级验证命令。
  - 复审证据来自真实 transcript 失败样本、已有运行态 smoke、以及对 `assistant.py` / `understanding.py` / `planning.py` / `task_or_event_clarifier.py` / `negotiation.py` / `assistant_runtime_plan.py` 的结构审查。
- Open risks / remaining work:
  - 只要 `send_message()` 仍允许 conductor 失败后默认掉回 legacy build_plan/workflow，主控人格分裂问题就会持续存在。
  - 只要 `UnderstandingSpecialist` 仍以 regex intent 分类为主，口语化 continuation 与任务继续规划就仍会高频跑偏。
  - 只要 proposal schema 仍缺少 `task_continuation_plan` / `task_schedule_plan` / `task_split_plan`，系统就无法稳定表达“围绕已有任务继续规划”。
  - 当前固定澄清模板仍会在误路由后放大 chatbot 感，必须降级为最后兜底，而不是默认主回复机制。
- Next recommended action:
  - 先定义新的 model-driven orchestration schema 和 `send_message()` 单一路径迁移图，再补 8-12 条真实 transcript 回归测试，最后开始执行 Phase 9A 的代码重构。

## 进度更新 - 2026-05-07 18:53 +08:00

- Overall progress: Phase 9A 已进入首轮运行时代码实现。当前已完成统一 orchestration schema 的第一版落地、真实 transcript 级 continuation 回归测试、`task_schedule_plan` proposal shape 第一版，以及 `primary` 模式下阻断 legacy fallback 的迁移切口。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Phase status:
  - Phase 0 - Baseline Freeze And Guardrails: done
  - Phase 1 - Data Foundation And Migration: done
  - Phase 2 - Proposal API And Manager: done
  - Phase 3 - Passive Conductor And Specialist Registry: done
  - Phase 4 - Action Executor And Confirmed Write Path: done
  - Phase 5 - Frontend Proposal Surface: done
  - Phase 6 - Phase 1B Stability And Observability: done
  - Phase 7 - Proactive Signals And Daily Rhythm: done
  - Phase 8 - Long-Term Memory And Personalization: done
  - Phase 9 - Model-Driven Orchestration Refactor: in progress
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\contracts.py`
    - 新增统一中间态结构：`TargetScope`、`ContinuationSignals`、`PlanningIntent`、`TimePreference`、`OrchestrationAssessment`。
    - `UnderstandingResult` 现在可携带 `orchestration`，用于把“用户目标 / target resolution / continuation / planning shape”显式化。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - 新增 continuation 检测与任务继续规划识别。
    - 新增 `plan_task_schedule` 理解分支，可把“我预计 3 天整理完成，帮我安排下下午 3 点到 5 点”识别为围绕现有任务继续规划，而不是误建新 task/event。
    - 新增时间偏好、持续天数、多日 block 扩展的第一版结构化抽取。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\planning.py`
    - 新增 `task_schedule_plan` proposal shape。
    - 支持围绕已有任务生成多天专注块 proposal，并在 action payload 中写入 `linked_task_id` 与 `focus_block`。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - 为 `plan_task_schedule` 增加更贴近 continuation 语义的澄清，而不是退回泛化“这是任务还是日程”。
  - `E:\GraduationProject\backend\app\assistant_agents\conductor.py`
    - 将 `orchestration` 中间态挂入 conductor metadata，便于后续日志、A/B 验证和单一路径迁移。
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 新增 `primary` conductor mode。
    - 在 `primary` 模式下，如果 conductor 不能产出明确结果，会阻断 legacy fallback，而不是继续默认掉回旧规则链。
    - 保持 `proposal` 模式兼容现有链路，作为迁移期安全阀。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增真实 transcript 风格回归：任务 continuation -> `task_schedule_plan`。
    - 新增 `send_message()` 在 proposal 模式下对 continuation 请求不再落回 legacy。
    - 新增 `primary` 模式阻断 legacy fallback 的回归。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `30 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py tests/test_assistant_specialists.py tests/test_assistant_proposal_revise.py` -> `45 passed`
  - `docker exec graduation-project-api pytest -q` -> `393 passed`
  - `python -m compileall E:\GraduationProject\backend\app\assistant_agents E:\GraduationProject\backend\app\services\assistant.py` -> passed
  - `pnpm exec vue-tsc --noEmit` -> passed
  - `pnpm test` -> `3 passed`
  - `pnpm run build` -> passed
- Open risks / remaining work:
  - 当前 `plan_task_schedule` 还是规则抽取驱动的第一版，只是把 continuation / planning shape 升成了一等结构，尚未真正接入 LLM 产出的结构化 orchestration。
  - `primary` 模式已经能阻断 legacy fallback，但默认配置仍未切换，说明单一路径迁移还没有完成。
  - 固定模板澄清和 proposal 文案仍然存在，只是 continuation 场景触发面已缩小；Phase 9B/9C 仍需继续把回复生成权交给模型。
  - 当前 task scheduling 仅覆盖“已有任务 -> 多天专注块”这一保守子集，还没覆盖“新任务 + schedule bundle”“复杂 revise”“非连续日期偏好”等更复杂形态。
- Next recommended action:
  - 进入 Phase 9A 下一步：补更多真实 transcript 回归，继续扩展 `orchestration` 到 revise / confirm / answer 场景，并开始收缩 `send_message()` 中 workflow / legacy plan 的默认参与范围。

## 进度更新 - 2026-05-07 19:08 +08:00

- Overall progress: Phase 9A 第二步已完成。proposal 文本协议现在也开始按“已有目标交互”收口，用户明确在说“确认现有方案 / 修改现有方案”但当前并无 pending proposal 时，不会再掉回 legacy 任务/日程理解链，而是直接返回面向当前上下文的 answer。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - `_maybe_handle_proposal_text_protocol()` 在识别到 `confirm/revise` 意图但找不到 pending proposal 时，改为直接返回 answer，而不是放行到后续 conductor/workflow/legacy plan。
    - 新增 `_build_missing_proposal_protocol_reply()`，为“确认现有方案 / 修改现有方案，但当前无待确认方案”提供上下文一致的回复。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增缺失 pending proposal 时的 confirm / revise 回归。
    - 新增 `send_message()` 在 proposal 模式下不会因为“同意”而误掉回 legacy build_plan 的回归。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `33 passed`
  - `docker exec graduation-project-api pytest -q` -> `396 passed`
- Open risks / remaining work:
  - proposal 文本协议虽然已不再轻易放行到 legacy，但其本身仍是独立前置链路，尚未和 conductor 的 `orchestration` 中间态彻底合并。
  - `workflow` 与 `AssistantPlanRuntime.build_plan()` 仍然在默认 `proposal` 模式下保留兜底参与权，完整单一路径迁移还未完成。
  - 目前“answer”场景仍主要体现为协议型直答，尚未扩展到更广泛的模型主导日常问答 / 轻咨询输入。
- Next recommended action:
  - 继续 Phase 9A：把 proposal confirm / revise 的目标解析和 conversation mode 显式纳入统一 orchestration 表达，再开始把 `proposal` 模式下的 fallback 范围进一步缩到仅保留少量安全兜底。

## 进度更新 - 2026-05-07 21:42 +08:00

- Overall progress: Phase 9A 第三步已完成。proposal text protocol 不再只是“前置黑箱分支”，现在已经能显式生成 `OrchestrationAssessment`，并且 `proposal` 模式下对上下文型输入的 legacy fallback 进一步收紧：只要消息明显是在继续围绕 active target / existing proposal / context reference 说话，就不会再默认掉回旧 `build_plan()`。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 为 proposal text protocol 新增显式的 `_build_proposal_protocol_assessment()`，把 `confirm_existing / revise_existing` 的 `conversation_mode`、`user_goal`、`target_scope`、`continuation` 结构化。
    - 将 pending proposal 解析拆成 `_resolve_text_protocol_proposal_from_active()`，让协议 target resolution 逻辑更接近统一 orchestration 风格。
    - `_build_missing_proposal_protocol_reply()` 现在可根据 assessment 区分“缺 pending proposal”和“目标仍 ambiguous”。
    - `_should_block_legacy_fallback()` 扩展到 `proposal` 模式：如果消息明显属于上下文型输入，就优先阻断 legacy fallback。
    - `_primary_mode_fallback_reply()` 现在会结合 active target 给出更具体的回退提示，而不是统一笼统文案。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 proposal confirm text 的 orchestration assessment 回归。
    - 新增 `proposal` 模式下 context-driven message 遇到 conductor legacy 结果时，也不会落回 legacy build_plan 的回归。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `35 passed`
  - `docker exec graduation-project-api pytest -q` -> `398 passed`
- Open risks / remaining work:
  - 当前 orchestration 结构已覆盖 task continuation 和 proposal text protocol，但 event update / batch update / memory-only answer 还未统一并入同一层显式表达。
  - `workflow` 与 `AssistantPlanRuntime.build_plan()` 虽然触发面继续缩小，但在非 context-driven 的普通输入上仍然保有默认兜底地位。
  - `NegotiationSpecialist` / `TaskOrEventClarifierSpecialist` 的模板式回复仍未退役，Phase 9B/9C 仍需继续推进模型生成式协商。
- Next recommended action:
  - 继续 Phase 9A：把 event update / batch update 也接入统一 orchestration schema，并尝试在 `proposal` 模式下把 `workflow` 默认参与范围缩到只剩明确非 conductor 覆盖场景。

## 进度更新 - 2026-05-07 22:00 +08:00

- Overall progress: Phase 9A 第四步已完成。event update / batch update 现在也进入统一 orchestration 表达层，不再只有 task continuation 和 proposal text protocol 具备显式 `conversation_mode / user_goal / target_scope / proposal_shape`。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - `_understand_update()` 现在接收 `continuation`，并为 event/task update 产出 orchestration。
    - 新增 `_build_event_update_orchestration()`，统一描述单日程更新、批量日程改期/取消、日程完成的 `user_goal`、`target_scope`、`proposal_shape`。
    - `mark_task_completed` 的目标型更新也补上了显式 orchestration。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 为单日程改期补了 orchestration 断言。
    - 为批量改期补了 orchestration 断言。
    - 为“目标已定位但缺少 batch shift rule”的澄清场景补了 orchestration 断言。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `35 passed`
  - `docker exec graduation-project-api pytest -q` -> `398 passed`
- Open risks / remaining work:
  - 现在 update 链路已经有显式 orchestration，但 `event_creation / task_creation` 仍然没有像 Phase 9 目标那样形成完全统一的显式语义面。
  - `workflow` 与 `AssistantPlanRuntime.build_plan()` 在 `proposal` 模式下仍是最终兜底，虽然上下文型输入的触发面已经缩小，但单一路径迁移尚未完成。
  - clarification / negotiation 的模板回复仍未被模型生成式协商替代。
- Next recommended action:
  - 继续 Phase 9A：把 `event_creation / task_creation / answer` 也尽量补齐统一 orchestration 表达，然后开始尝试把 `proposal` 模式下 `workflow` 默认参与权进一步下放到 feature flag 或更窄的 degrade path。

## 进度更新 - 2026-05-08 10:18 +08:00

- Overall progress: Phase 9A 第五步已完成。`event_creation / task_creation / schedule_guidance / unknown` 现在也具备显式 orchestration 表达，统一中间态已经覆盖创建类、更新类、proposal text protocol 和 answer-like guidance 语义。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - `create_event` / `create_task` 现在会生成显式 orchestration。
    - `schedule_guidance` 现在会被标记为 `conversation_mode="answer"`、`user_goal="schedule_guidance"`，即便当前 conductor 还未直接回答它，理解层已经不再把它当成无结构 fallback。
    - `unknown` 现在也会生成基础 clarification-oriented orchestration。
    - 新增 `_build_creation_orchestration()`，统一创建类 proposal 的中间态表达。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 为 `event_creation` 补了 orchestration 断言。
    - 为 generic task clarification 补了 orchestration 断言。
    - 为 `schedule_guidance` 补了 answer-like orchestration 断言。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `36 passed`
  - `docker exec graduation-project-api pytest -q` -> `399 passed`
- Open risks / remaining work:
  - 虽然理解层的统一 orchestration 覆盖面已经明显扩大，但 conductor 仍未对 `conversation_mode="answer"` 形成独立处理分支，`schedule_guidance` 仍会继续走旧 fallback 执行路径。
  - `workflow` 与 `AssistantPlanRuntime.build_plan()` 仍然承担大量最终回答职责；当前只是理解层先把语义建模统一了。
  - negotiation / clarification 的模板回复依旧存在，尚未切换到模型主导的动态协商。
- Next recommended action:
  - 继续 Phase 9A：开始真正收缩 `proposal` 模式下 `workflow / build_plan` 的默认参与范围，并优先挑一个 answer-like 场景（建议 `schedule_guidance`）改成 conductor 可直接产出的独立 reply path。

## 进度更新 - 2026-05-08 10:49 +08:00

- Overall progress: Phase 9A 第六步已完成。`schedule_guidance` 已经从 `proposal` 模式下对 `build_plan()` 的默认依赖中切出，开始走 answer-like orchestration path：先由 conductor/understanding 产出统一中间态，再由 `AssistantService` 根据 `conversation_mode="answer"` 直接构建回复与 `suggest_schedule` 动作，而不是先掉进 workflow / legacy plan。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 在 `send_message()` 与 `send_message_stream()` 中新增 `_maybe_build_orchestration_answer_plan()` 调用。
    - 当 conductor 结果携带 `conversation_mode="answer"` 且 `user_goal="schedule_guidance"` 时，直接走 answer-like path，绕开 `_build_plan()` / `workflow` 默认兜底。
    - 当前 answer-like path 仍复用现有 `_build_rule_based_plan()` 的 `schedule_guidance` 具体回复构造，但控制权已前移到 orchestration 层。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 `proposal` 模式下 `schedule_guidance` 不再运行 legacy `_build_plan()` 的回归。
    - 新增该链路会直接返回 `suggest_schedule` 动作的回归。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `37 passed`
  - 首次全量 `pytest -q` 遇到容器内 `/tmp/pytest-of-root` 临时目录状态异常，表现为 pytest tmp dir / sqlite 临时测试环境报错，不是本轮代码回归。
  - 清理 `docker exec graduation-project-api sh -lc "rm -rf /tmp/pytest-of-root && mkdir -p /tmp/pytest-of-root"` 后重跑：
    - `docker exec graduation-project-api pytest -q` -> `400 passed`
- Open risks / remaining work:
  - `schedule_guidance` 已经不再经过默认 `_build_plan()` 兜底，但其 answer 内容仍复用旧 rule-based helper，说明“主控先整理语义”已经实现，“回复生成完全模型主导”还没实现。
  - 其他 answer-like / advice-like 输入仍未像 `schedule_guidance` 一样完成独立 path 切出。
  - `workflow` 与 `_build_plan()` 仍然覆盖很多非 proposal / 非 schedule_guidance 场景，单一路径迁移还未完成。
- Next recommended action:
  - 继续 Phase 9A：再挑一个高频非 proposal 场景（建议 `event_context_advice` 或 `progress_followup`）切出独立 orchestration answer path，然后开始评估 `workflow` 是否可以在 `proposal` 模式下降为更窄的 feature-flag fallback。

## 进度更新 - 2026-05-08 19:10 +08:00

- Overall progress: Phase 9A 第七步已完成。`progress_followup` 已从 `proposal` 模式下的默认 legacy `_build_plan()` 路径中切出，成为第二个 answer-like orchestration direct reply path：理解层先产出 `conversation_mode="answer"` / `user_goal="progress_followup"`，`AssistantService` 再直接构建进度跟进回复与 `suggest_schedule` 动作。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\contracts.py`
    - `GoalType` 增加 `progress_followup`，让进度跟进不再被迫挤进 `unknown` 或 legacy fallback 表达。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - `progress_followup` 现在会生成显式 answer orchestration。
    - target scope 先标为 `kind="task" / resolution="ambiguous"`，表达它通常围绕当前活跃任务集合给出跟进建议，而不是立即写入任务或日程。
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - `_maybe_build_orchestration_answer_plan()` 支持 `user_goal="progress_followup"`。
    - 该路径直接调用现有进度跟进计划构造，绕过 workflow / legacy `_build_plan()` 默认兜底。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 conductor 层 `progress_followup` answer orchestration 回归。
    - 新增 `send_message()` proposal 模式下进度跟进不运行 legacy `_build_plan()` 的真实 transcript 回归。
    - 回归覆盖返回进度摘要、最近执行反馈和 `suggest_schedule` 动作。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `39 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py tests/test_assistant_conductor.py` -> `75 passed`
- Open risks / remaining work:
  - `progress_followup` 的具体回复内容仍复用既有 rule-based helper；本步完成的是主控路径收敛，不是回复生成模型化。
  - `event_context_advice` 仍未切出独立 orchestration answer path，且当前理解层可能先被 event/create 识别截获，需要下一步单独处理。
  - `workflow` 与 `_build_plan()` 在其他非 answer-like 场景仍是默认兜底；Phase 9A 还需要继续收缩它们在 `proposal` 模式下的触发面。
- Next recommended action:
  - 继续 Phase 9A：优先处理 `event_context_advice`，先修正理解层对“几点出发 / 要不要带伞 / 通勤天气建议”这类输入的 orchestration 识别，再切出对应 direct answer path，并补 proposal 模式下不落回 `_build_plan()` 的 transcript 回归。

## 进度更新 - 2026-05-08 20:14 +08:00

- Overall progress: Phase 9A 第八步已完成。`event_context_advice` 也已从旧的 event creation / legacy `_build_plan()` 默认路径中切出，成为独立 answer-like orchestration path。至此，本轮连续完成了 `progress_followup` 与 `event_context_advice` 两个高频非 proposal 场景的 direct reply path。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\contracts.py`
    - `GoalType` 增加 `event_context_advice`。
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\understanding.py`
    - `_classify()` 现在优先保留 `event_context_advice` / `progress_followup` 这类 direct answer intent，避免“几点出发 / 要不要带伞 / 通勤天气建议”先被 `_looks_like_event()` 截获为创建日程。
    - `event_context_advice` 会生成 `conversation_mode="answer"`、`user_goal="event_context_advice"`、`target_scope.kind="event"` 的 orchestration。
    - 当标题、时间、地点足够明确时，target resolution 标为 `resolved`；上下文不完整时保守标为 `ambiguous`，但仍保持 answer path，不直接写入。
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - `_maybe_build_orchestration_answer_plan()` 支持 `event_context_advice`，由 orchestration direct path 构建通勤 / 天气 / 出发建议。
    - 该路径仍只产生 `propose_event` pending-style action，不进行 confirmed write，保持 proposal-first / confirmation-before-write 边界。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 conductor 层 `event_context_advice` answer orchestration 回归。
    - 新增 `send_message()` proposal 模式下 event context advice 不运行 legacy `_build_plan()` 的真实 transcript 回归。
    - 回归覆盖 `propose_event` 动作、通勤摘要、天气/带伞建议。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `41 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `36 passed`
  - `docker exec graduation-project-api pytest -q` -> `404 passed in 675.66s (0:11:15)`
- Open risks / remaining work:
  - `schedule_guidance` / `progress_followup` / `event_context_advice` 已经完成主控路径收敛，但回复内容仍主要复用现有 rule-based helper。
  - `workflow` 与 `_build_plan()` 仍覆盖剩余未迁移场景；下一步应开始把 `proposal` 模式下的 workflow 默认参与权降为更窄的 feature-flag fallback。
  - clarification / negotiation 仍有模板化回复，Phase 9B/9C 需要继续把澄清与协商文案交给模型生成。
- Next recommended action:
  - 继续 Phase 9A/9B 交界：盘点 `proposal` 模式下剩余会默认进入 workflow / `_build_plan()` 的 intent，优先把 workflow 降级为只服务未覆盖 intent 的 fallback，并为每次收缩补 transcript 回归。

## 进度更新 - 2026-05-08 20:29 +08:00

- Overall progress: Phase 9A 第九步已完成。`proposal/primary` 模式下的 workflow 已从默认兜底降级：只要 conductor 已经运行，后续不会再默认进入 `_respond_with_workflow()` / `_respond_with_workflow_stream()`，而是继续走 orchestration answer / proposal / clarification / blocked fallback / `_build_plan()` 的更窄路径。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 新增 `_should_use_workflow_fallback()`。
    - `send_message()` 与 `send_message_stream()` 改为通过该门控决定是否允许 workflow fallback。
    - 在 `assistant_conductor_mode in {"proposal", "primary"}` 且 conductor 已运行时，禁用 workflow 默认兜底；`legacy` 模式、未运行 conductor、`ENABLE_WORKFLOW=false` 的既有语义保持不变。
    - `progress_followup` 的空状态不再返回 `None`，而是直接返回“目前没有新的进度变化。”，避免空状态继续掉进 workflow / `_build_plan()`。
  - `E:\GraduationProject\backend\app\services\assistant_runtime_plan.py`
    - 同步 `build_progress_followup_plan()` 空状态行为，避免抽出 runtime 入口与 `AssistantService` 包装入口语义分裂。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增空进度跟进在 `proposal` 模式下不走 workflow / `_build_plan()` 的回归。
    - 新增 conductor 已运行后，`proposal` 模式不再把 workflow 当默认兜底的回归。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `43 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py tests/test_workflow.py tests/test_workflow_memory_context.py` -> `70 passed`
  - `docker exec graduation-project-api pytest -q` -> `406 passed in 576.12s (0:09:36)`
- Open risks / remaining work:
  - workflow 已降级，但 `_build_plan()` 仍是部分兜底路径，且内部仍有 rule-based short-circuit；后续需要继续把明确 intent 从 `_build_plan()` 中迁出。
  - `send_message_stream()` 在非 workflow fallback 后仍保留 Gemini streaming / `_build_plan()` 路径，需要后续继续统一成与非流式相同的 orchestration-first 控制面。
  - 模板式 clarification / negotiation 仍未模型化，Phase 9B/9C 仍需推进生成式澄清。
- Next recommended action:
  - 继续 Phase 9B：优先收缩 `_build_plan()` 中对 `schedule_guidance / event_context_advice / progress_followup` 的 rule-based short-circuit 兜底职责，把这些 answer-like intent 的唯一主入口固定为 `_maybe_build_orchestration_answer_plan()`，同时保留 legacy mode 兼容路径。

## 进度更新 - 2026-05-08 20:47 +08:00

- Overall progress: Phase 9B 第一处收缩已完成。`_build_plan()` 中 `schedule_guidance / event_context_advice / progress_followup` 的 rule-based short-circuit 现在可以按调用入口关闭；在 `proposal/primary` 模式且 conductor 已运行后，answer-like intent 不再通过 `_build_plan()` 内部规则短路绕过 orchestration answer 入口。legacy 兼容路径仍保留默认行为。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant_runtime_plan.py`
    - `build_plan()` 新增 `allow_answer_like_rule_short_circuit` 参数，默认 `True` 保持 legacy 兼容。
    - 当该参数为 `False` 且 intent 属于 `schedule_guidance / event_context_advice / progress_followup` 时，不再直接返回 rule-based fallback plan，也不再用 rule-based answer/actions 覆盖空模型结果。
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - `_build_plan()` 包装方法透传 `allow_answer_like_rule_short_circuit`。
    - `send_message()` 与 `send_message_stream()` 在 conductor 已运行后的 fallback plan 调用中，使用 `_should_allow_answer_like_rule_short_circuit()` 关闭 answer-like 规则短路。
  - `E:\GraduationProject\backend\tests\test_assistant_service.py`
    - 新增 `_build_plan()` 可关闭 answer-like rule short-circuit 的回归，验证 `schedule_guidance` 不再直接返回 `suggest_schedule` fallback。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 强化 proposal fallback 回归，确认 conductor 已运行后传入 `allow_answer_like_rule_short_circuit=False`。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `43 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api pytest -q tests/test_workflow.py tests/test_workflow_memory_context.py` -> `34 passed`
  - `docker exec graduation-project-api pytest -q` -> `407 passed in 782.10s (0:13:02)`
- Open risks / remaining work:
  - `_build_plan()` 仍保留 legacy 兼容能力，只是 proposal/primary conductor fallback 入口不再允许 answer-like 规则短路。
  - 非流式路径已经明确传入该门控；流式路径仍有 Gemini streaming 的单独分支，后续需要继续把流式与非流式的 fallback 控制面对齐。
  - 下一步应继续收缩模板式 clarification / negotiation，避免未知或歧义输入过早落入固定话术。
- Next recommended action:
  - 继续 Phase 9B/9C：选择一个高频 clarification 场景，把模板式 `TaskOrEventClarifierSpecialist` / `NegotiationSpecialist` 回复改为 orchestration-aware 的生成式澄清边界，并补 transcript 回归。

## 进度更新 - 2026-05-08 21:02 +08:00

- Overall progress: Phase 9C 第一处澄清收缩已完成。`TaskOrEventClarifierSpecialist` 不再只依赖固定 ambiguity 分支；对高频任务创建澄清和不完整日程创建澄清，已经优先读取 `OrchestrationAssessment.missing_information / user_goal / proposal_shape / target_scope` 生成问题，并在 conductor metadata 中标记 `clarification_source="orchestration"`。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - 新增 `_build_orchestration_clarification()`。
    - `create_task + task_creation` 的澄清现在按 orchestration missing fields 生成，例如 `subject / deadline_or_time_window / rhythm`。
    - `create_event + event_creation` 的普通缺字段澄清也改为 orchestration-aware 生成，例如 `start_time / end_time_or_duration / title`。
    - 对 `dating_request_too_vague` 保留原专门兜底，避免过度泛化高风险模糊输入。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 强化 `帮我安排复习` 回归，确认 metadata 标记 orchestration 澄清来源，并保留“科目 / 截止 / 可确认”信息。
    - 新增“不完整日程创建” transcript 回归，确认回复来自 orchestration-aware clarification，并要求包含“可确认的日程方案 / 开始时间”。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `44 passed`
  - `docker exec graduation-project-api pytest -q` -> `408 passed in 618.60s (0:10:18)`
- Open risks / remaining work:
  - 这一步仍是 orchestration-aware 的确定性生成，不是真正 LLM 生成式澄清；但已经把模板分支降级为后备路径。
  - `NegotiationSpecialist.format_proposals()` 的 proposal 文案仍是固定模板，后续 Phase 9C 需要继续拆。
  - 其他 update / batch clarification 仍有固定分支，可继续逐步迁移到 orchestration-aware 生成。
- Next recommended action:
  - 继续 Phase 9C：把 `NegotiationSpecialist` 的 proposal 回复从固定模板改成使用 `proposal_shape / orchestration.user_goal / target_scope` 的生成边界，先覆盖 `task_schedule_plan` 或 `event_reschedule`，并补 transcript 回归。

## 进度更新 - 2026-05-08 21:15 +08:00

- Overall progress: Phase 9C 第二处 negotiation 收缩已完成。`NegotiationSpecialist.format_proposals()` 不再对所有 proposal 使用同一个固定模板；`task_schedule_plan` 与 `event_reschedule` 已按 orchestration 的 `proposal_shape / target_scope` 生成更贴近目标的 proposal 回复，并在 conductor metadata 中标记 `proposal_reply_source="orchestration"`。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\negotiation.py`
    - `format_proposals()` 现在接收 `ConductorState`，可读取 `understanding.orchestration`。
    - 新增 `_format_task_schedule_plan()`，为任务排程 proposal 输出“任务排程方案 / 确认后才创建专注时段”的上下文文案。
    - 新增 `_format_event_reschedule()`，为日程改期 proposal 输出“改期方案 / 确认后才改动原日程”的上下文文案。
    - 默认固定模板保留为未迁移 proposal shape 的兜底。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - `task_schedule_plan` 回归新增 `proposal_reply_source` 断言，并确认回复包含“任务排程方案 / 确认后我才会创建这些专注时段”。
    - `event_reschedule` 回归新增 `proposal_reply_source` 断言，并确认回复包含“可确认的改期方案 / 确认后我才会改动原日程”。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `44 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api pytest -q` -> `408 passed in 496.26s (0:08:16)`
- Open risks / remaining work:
  - 这一步仍是 orchestration-aware deterministic wording，不是完整 LLM generated negotiation。
  - `event_creation / task_creation / batch update / status update` 的 proposal 回复仍走默认模板，后续可继续按 proposal shape 迁移。
  - 前端 proposal surface 未重新做系统级 smoke，最终收口前仍需真实 API/UI smoke。
- Next recommended action:
  - 继续 Phase 9C：扩展 proposal reply generation 到 `event_creation / task_creation`，或开始做一次端到端 smoke，检查 proposal-first / confirm-before-write / memory notice / proactive follow-up 是否仍完整。

## 进度更新 - 2026-05-08 21:29 +08:00

- Overall progress: Phase 9C 第三处 negotiation 收缩已完成。`event_creation` 与 `task_creation` 的 proposal 回复也已接入 orchestration-aware wording，创建类 proposal 不再默认使用通用固定模板；回复会明确区分“新日程方案 / 新任务方案”以及“确认后才创建”的执行边界。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\negotiation.py`
    - 新增 `_format_event_creation()`，为新日程 proposal 输出“新日程方案 / 现在不会直接写入日程 / 确认后才创建日程”。
    - 新增 `_format_task_creation()`，为新任务 proposal 输出“新任务方案 / 现在不会直接写入任务 / 确认后才创建任务”。
    - `event_creation / task_creation / event_reschedule / task_schedule_plan` 均已通过 `proposal_reply_source="orchestration"` 标记迁移路径。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 强化 clear event creation 回归，确认 `proposal_reply_source` 与“新日程方案 / 不会直接写入”文案。
    - 新增 clear task creation transcript 回归，确认 `task_creation` proposal shape、`create_task` action 与“新任务方案 / 不会直接写入任务”文案。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `45 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_revise.py` -> `15 passed`
  - `docker exec graduation-project-api pytest -q` -> `409 passed in 460.30s (0:07:40)`
- Open risks / remaining work:
  - Batch update / status update proposal 回复仍走默认模板兜底。
  - 当前 wording 仍是 deterministic orchestration-aware generation，不是完整 LLM negotiation。
  - 需要做系统级 smoke，确认 API / proposal persistence / confirmation write path / memory notice / proactive follow-up 仍协同正常。
- Next recommended action:
  - 进入系统级 smoke 前，先补一条 lightweight API-level smoke transcript，覆盖 proposal mode 下 create event -> pending proposal -> confirm -> write path，验证 proposal-first 与 confirmation-before-write 没被 Phase 9C wording 改动破坏。

## 进度更新 - 2026-05-08 21:48 +08:00

- Overall progress: Phase 9C 第四处 negotiation 收缩已完成。剩余 batch/status/update 类 proposal shape 已接入 orchestration-aware wording：`event_cancel / event_status_update / event_batch_cancel / event_batch_reschedule / task_status_update` 不再默认落到通用 proposal 模板，proposal 回复会明确对应“取消 / 状态更新 / 批量改期 / 批量取消”的确认边界。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\negotiation.py`
    - 新增 `_format_update_proposal()`，统一处理 update/status/batch proposal wording。
    - 新增 `_update_target_label()`，优先从 proposal payload / related id 生成目标标签。
    - `event_cancel / event_status_update / event_batch_cancel / event_batch_reschedule / task_status_update` 均标记 `proposal_reply_source="orchestration"`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - `event_batch_reschedule` transcript 增加 `proposal_reply_source`、`批量改期方案`、`确认前不会修改日程` 断言。
    - `task_status_update` transcript 增加 `proposal_reply_source`、`任务状态更新方案`、`确认前不会修改任务` 断言。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `45 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_api.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_revise.py` -> `15 passed`
  - `docker exec graduation-project-api pytest -q` -> `409 passed in 751.61s (0:12:31)`
- Open risks / remaining work:
  - Proposal wording 已基本完成 orchestration-aware 分流，但仍不是 LLM-generated negotiation。
  - 需要开始系统级 smoke，覆盖真实 API / persistence / confirm-before-write / action executor。
  - 主控路径仍需最终审计：确认 legacy workflow / `_build_plan()` 只剩明确兼容 fallback，而不是默认主控。
- Next recommended action:
  - 做 lightweight API/service smoke：proposal mode 下 create event 只创建 pending proposal，不写 event；随后 confirm proposal 才触发 action executor 写入，并验证回复/状态/写入结果。

## 进度更新 - 2026-05-08 22:03 +08:00

- Overall progress: Phase 9C 后的 lightweight service smoke 已补齐。现在有一条端到端风格回归覆盖 proposal mode 下的核心安全边界：用户提出创建日程时只生成 pending proposal，不走 legacy event write；用户随后回复确认文本时，才进入 proposal confirmation path，并把 active target 更新到 executed proposal / related event。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Files changed in this step:
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 `test_send_message_proposal_mode_create_event_then_confirm_smoke()`。
    - 第一轮 `send_message("明天下午3点我要去学校和同学见面")` 断言只创建 `event_creation` pending proposal，`event_service.create_event` 若被调用会直接失败。
    - 第二轮 `send_message("同意")` 断言调用 `confirm_proposal(user_id="demo-user", proposal_id=202, option_id="A")`。
    - 验证确认后回复为“已按这个方案确认并执行。”，并且 active target payload 写入 `active_proposal_id=202 / related_event_id=88`。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `46 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_proposal_manager.py` -> `6 passed`
  - `docker exec graduation-project-api pytest -q` -> `410 passed in 588.78s (0:09:48)`
- Open risks / remaining work:
  - 这仍是 service-level smoke，尚未通过真实 HTTP API / 前端 UI 走完整链路。
  - Fake proposal manager 验证了确认路径调用与 active target 写入；真实 action executor 的写入由 `test_assistant_proposal_manager.py` 覆盖，但两者仍是分层验证。
  - 最终收口前需要一次真实运行环境 smoke：API health、assistant message、proposal list/confirm、事件写入结果。
- Next recommended action:
  - 做最终完成审计前的真实运行环境 smoke。如果当前容器 API 已可用，先检查 health，再用现有测试库或临时 smoke 数据跑一次 create event proposal -> confirm -> event readback。

## 进度更新 - 2026-05-08 22:06 +08:00

- Overall progress: 真实运行环境 HTTP smoke 已完成一轮。当前容器 API 在 `ASSISTANT_CONDUCTOR_MODE=proposal` 下可用，已用真实 `/api/assistant/message`、`/api/assistant/proposals/{id}/confirm`、`/api/events` 路径验证 create event proposal -> confirm -> event readback -> cleanup。
- Active phase: Phase 9 - Model-Driven Orchestration Refactor
- Runtime smoke evidence:
  - `GET http://127.0.0.1:8000/api/health` -> `{"status":"ok","service":"Personal Affairs Assistant","version":"0.1.0","environment":"development","database_ready":true}`
  - Runtime env:
    - `ASSISTANT_CONDUCTOR_MODE=proposal`
    - `SQLITE_DB_PATH=/app/data/app.db`
  - `POST /api/assistant/message` with `明天下午3点我要去学校和同学见面 ...`:
    - response actions: `[]`
    - response reply contained `待确认方案`
    - no legacy event write occurred before confirmation
  - `GET /api/assistant/proposals?status=pending&proposal_type=event_creation&limit=20`:
    - pending proposal found: `proposal_id=35`
    - summary: `建议创建日程“和同学见面”：05-09 15:00-16:00，地点：学校`
  - `POST /api/assistant/proposals/35/confirm`:
    - confirmed status: `executed`
    - related event id: `57`
  - `GET /api/events`:
    - event `57` found with title `和同学见面`
  - Cleanup:
    - `DELETE /api/events/57` -> `200`
    - follow-up pending event creation count -> `0`
- Notes:
  - 首次 smoke message 带了 `SMOKE-P9-*` marker，但当前标题抽取会丢弃该 marker；脚本因此没有按 marker 匹配 proposal。随后按当前唯一 pending `event_creation` proposal 继续完成确认与 cleanup。
  - 这暴露了一个非阻塞观察点：自由文本 marker 不适合作为事件标题识别锚点，后续 smoke 如需稳定定位，应该使用 proposal id / timestamp 前置状态，而不是期望 marker 被标题抽取保留。
- Validation:
  - HTTP runtime smoke -> passed
  - smoke cleanup verification -> `pending_event_creation=0`
- Open risks / remaining work:
  - 已完成 backend tests + runtime API smoke，但尚未做前端 UI 手动/自动 smoke。
  - 还需要最终完成审计，逐项核对 `goal.txt` 的“模型主导语义编排 / proposal-first / 确认后执行 / 长期记忆 / 主动跟进 / legacy 降级”是否都有实际证据。
- Next recommended action:
  - 执行最终完成审计。如果审计发现只剩文档收口，则更新 handoff/progress 并判断 Phase 9 是否可标记完成；如果发现缺口，则继续补最小验证或代码路径。

## 完成审计 - 2026-05-08 22:07 +08:00

- Objective restatement:
  - 将个人事务工作台 AI 助手从“规则前置决策 + 多套 fallback 的 proposal 外壳”推进到“模型主导语义编排 + proposal-first 执行边界 + 用户确认后执行 + 长期记忆 + 主动跟进”的统一主控路径。
  - 当前 Phase 9 重点是收回 legacy workflow / `_build_plan()` / 模板澄清主导权。
- Prompt-to-artifact checklist:
  - 高频 answer-like 场景不再默认掉进 workflow / `_build_plan()`:
    - Evidence: `schedule_guidance / progress_followup / event_context_advice` 均已有 `conversation_mode="answer"` orchestration direct path。
    - Evidence: `tests/test_assistant_conductor.py` 覆盖 proposal mode 下不运行 legacy `_build_plan()` / workflow 的 transcript。
  - proposal-first / confirmation-before-write:
    - Evidence: service-level smoke `test_send_message_proposal_mode_create_event_then_confirm_smoke()`。
    - Evidence: runtime HTTP smoke `POST /assistant/message -> pending proposal -> POST /assistant/proposals/{id}/confirm -> event readback -> cleanup` passed。
  - workflow 降级:
    - Evidence: `_should_use_workflow_fallback()` 禁止 proposal/primary conductor 后默认进入 workflow。
    - Evidence: targeted regression 覆盖 proposal mode 不再默认用 workflow fallback。
  - `_build_plan()` answer-like rule short-circuit 降级:
    - Evidence: `allow_answer_like_rule_short_circuit=False` in proposal/primary conductor fallback。
    - Evidence: `test_build_plan_can_disable_answer_like_rule_short_circuit()`。
  - clarification / negotiation 模板降级:
    - Evidence: `TaskOrEventClarifierSpecialist` 已优先用 orchestration missing fields 生成 create task/event 澄清。
    - Evidence: `NegotiationSpecialist` 已对 major proposal shapes 使用 orchestration-aware wording，并标记 `proposal_reply_source="orchestration"`。
  - 长期记忆:
    - Evidence: Phase 8 task book 记录 memory candidate API、confirm/reject、`.md` 写入 smoke 与 UI smoke 已完成。
    - Gap: 本轮 Phase 9 后未重新跑 memory candidate HTTP/UI smoke。
  - 主动跟进:
    - Evidence: Phase 7 task book 记录 heartbeat/signals/proactive API smoke 已完成；Phase 9 progress followup direct path 已覆盖。
    - Gap: 本轮 Phase 9 后未重新跑 heartbeat/proactive signal runtime smoke。
  - 系统级 smoke:
    - Evidence: backend full regression `410 passed` and runtime HTTP create event proposal -> confirm -> event readback passed.
    - Gap: 前端 UI proposal surface 未在 Phase 9 后重新 smoke。
- Completion decision:
  - Not complete yet.
  - Reason: 后端主控路径已经大幅收敛并有真实 HTTP smoke，但“完整模型生成式澄清/协商”、Phase 9 后的 memory/proactive 重新验证、以及前端 UI smoke 仍缺证据。不能仅凭 backend tests 与单条 runtime smoke 判定整个 `goal.txt` 已完成。
- Next recommended action:
  - 跑最小增量 runtime smoke：
    1. memory candidate create -> confirm -> readback/cleanup；
    2. proactive heartbeat/signal endpoint smoke；
    3. 前端或 Playwright UI smoke 验证 proposal 待确认区仍可见/可操作。
  - 若这三项通过，再做最终 completion audit。

## 运行态补充 smoke - 2026-05-08 22:10 +08:00

- Long-term memory runtime smoke:
  - Used isolated user: `smoke-memory-1778249376`
  - `POST /api/assistant/memory/candidates` -> candidate `9`, status `proposed`
  - `POST /api/assistant/memory/candidates/9/confirm` -> status `written`
  - `GET /api/assistant/memory` -> smoke marker read back successfully
  - Cleanup: removed `/app/data/assistant_memory/smoke-memory-1778249376`
  - Result: passed
- Proactive signal runtime smoke:
  - Used isolated user: `smoke-signal-1778249420`
  - `POST /api/assistant/heartbeat/run` with `signal_type=deadline_risk` -> signal `1`
  - heartbeat message confirmed proposal creation/writes still require later confirmation
  - `POST /api/assistant/signals/1/proposal` -> proposal `36`, status `pending`
  - Proposal action type: `acknowledge_signal`
  - `GET /api/assistant/signals?status=proposal_created` contained signal `1`
  - Result: passed
- Updated completion audit status:
  - Memory runtime verification: now covered.
  - Proactive signal runtime verification: now covered.
  - Remaining material gap: front-end / UI smoke after Phase 9 changes.
- Next recommended action:
  - Run a minimal frontend/UI smoke for assistant proposal surface, or explicitly document why backend/API smoke is sufficient for current goal if UI is out of scope.

## 前端 UI smoke - 2026-05-08 22:18 +08:00

- Overall progress: Phase 9 后的最小前端 UI smoke 已补齐。当前本地 Vite 页面 `http://127.0.0.1:8888` 可打开，助手 tab 能展示后端返回的 pending proposal 与 proposed memory candidate。
- Setup:
  - Created temporary local-user proposal through real API:
    - `POST /api/assistant/message` with `明天上午10点到10点30安排和同学见面 ui-smoke-frontend-1778249832`
    - reply contained `待确认方案`
    - latest pending `event_creation` proposal: `proposal_id=38`
  - Created temporary local-user memory candidate:
    - `POST /api/assistant/memory/candidates`
    - candidate `11`, status `proposed`
    - marker/title: `ui-smoke-frontend-1778249832`
- Playwright evidence:
  - Navigated to `http://127.0.0.1:8888`
  - Opened navigation tab `助手`
  - DOM text checks:
    - `待确认方案`: present
    - `待确认记忆`: present
    - `确认`: present
    - `写入记忆`: present
    - temporary memory marker `ui-smoke-frontend-1778249832`: present
  - Result: passed
- Cleanup:
  - `POST /api/assistant/proposals/38/reject` -> status `rejected`
  - `POST /api/assistant/memory/candidates/11/reject` -> status `rejected`
  - Verification:
    - proposal `38` no longer in pending list
    - memory candidate `11` no longer in proposed list
  - Note: there was already one unrelated pending proposal and one unrelated proposed memory candidate for `local-user`; they were left untouched.
- Updated audit status:
  - Backend full regression: covered by `410 passed`
  - Runtime proposal-first create event smoke: covered
  - Runtime memory candidate write/readback smoke: covered
  - Runtime proactive signal smoke: covered
  - Frontend assistant proposal/memory surface smoke: now covered

## 最终整合判断 - 2026-05-08 22:18 +08:00

- Current session success condition:
  - Met.
  - `progress_followup` and `event_context_advice` now have orchestration-driven answer paths and regressions.
  - Proposal mode no longer treats workflow / `_build_plan()` as the default fallback after conductor output.
  - Clarification and negotiation now prefer orchestration-derived structure for the covered create/update/proposal shapes.
  - Service, backend full regression, runtime HTTP smoke, memory/proactive smoke, and frontend UI smoke all have evidence.
- Overall `goal.txt` completion decision:
  - Not marked complete yet.
  - Reason: Phase 9 has been materially advanced and smoke-tested, but the broader goal says to continue until the assistant has truly migrated to a unified model-led orchestration path. The current implementation still retains legacy workflow / `_build_plan()` compatibility fallback and deterministic orchestration-aware wording for several clarification/negotiation paths. These are now demoted, tested, and safer, but not fully removed or fully model-generated across the entire assistant surface.
- Recommended next action:
  - Continue Phase 9 by auditing remaining proposal-mode branches where `AssistantService` can still call legacy `_build_plan()` or workflow compatibility fallbacks, then remove or gate the next safest branch with transcript regressions.
  - After each removal, rerun targeted conductor/service tests and periodically rerun full backend regression.

## 进度更新 - 2026-05-09 00:45 +08:00

- Overall progress: 继续 Phase 9 fallback 收缩，补齐流式助手路径。此前 REST `send_message()` 已覆盖 proposal-mode answer-like orchestration，但 `send_message_stream()` 中存在一个未覆盖缺口：answer-plan 调用曾传入不存在的参数；并且 conductor 在 `proposal/primary` 模式下已有结果后，streaming 路径仍会先尝试旧的 Gemini streaming plan fallback。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 修正 `send_message_stream()` 调用 `_maybe_build_orchestration_answer_plan()` 的参数列表，避免 answer-like orchestration 在流式路径触发 `TypeError`。
    - 新增 `_should_use_streaming_plan_fallback()`。
    - 在 `proposal/primary` 且 conductor 已运行并返回结果时，禁止默认进入 Gemini streaming plan fallback；流式路径改为与 REST 路径一致，进入受 gate 约束的 `_build_plan(... allow_answer_like_rule_short_circuit=False)`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 `test_send_message_stream_proposal_mode_progress_followup_empty_state_stays_on_answer_path()`，覆盖空进度 answer path 不进入 workflow / `_build_plan()`，并返回 `目前没有新的进度变化。`。
    - 新增 `test_send_message_stream_proposal_mode_does_not_use_gemini_stream_as_default_fallback()`，覆盖 proposal-mode conductor 已运行后不再默认调用 Gemini streaming plan fallback，并断言后续 `_build_plan()` 的 answer-like rule short-circuit 被关闭。
- Validation:
  - First targeted run intentionally exposed the stream bug and an accidental patch mismatch; fixed before final validation.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `47 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py tests/test_assistant_service.py` -> `85 passed`
  - `docker exec graduation-project-api python -m compileall app/services/assistant.py tests/test_assistant_conductor.py` -> passed
- Current completion status:
  - Goal still not complete. This step removes one more default fallback path from the streaming surface, but broader Phase 9 still has intentionally retained compatibility fallback through `_build_plan()` for unsupported/non-orchestrated proposal-mode messages.
- Next recommended action:
  - Continue auditing `AssistantService` for remaining proposal-mode fallback behavior after conductor result, especially unsupported messages that still reach `_build_plan()` compatibility logic, and decide the next safe branch to gate behind explicit mode/intent rather than defaulting to legacy planning.

## 进度更新 - 2026-05-09 01:04 +08:00

- Overall progress: 继续收回模板式 clarification 的主导权。`unknown` goal 之前虽然已有 `OrchestrationAssessment(conversation_mode="clarification", user_goal="unknown", missing_information=["goal_type"])`，但 `TaskOrEventClarifierSpecialist` 没有消费这段 orchestration 信息，最后仍落到固定模板“你希望把这件事当成一次性日程，还是需要拆成多个日程组合成的任务？”。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - 在 `_build_orchestration_clarification()` 中新增 `user_goal="unknown" / missing_information=["goal_type"]` 分支。
    - 新回复围绕“你想让我产出什么结果”澄清，让用户选择创建/调整日程、拆解并安排任务，或只基于现有事项给建议，并提示可补充时间/地点/截止时间/偏好。
    - 命中后标记 `clarification_source="orchestration"`，不再落到最后的固定 task/event 模板。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 `test_conductor_uses_orchestration_clarification_for_unknown_goal()`，验证普通 unknown 输入走 orchestration clarification，回复包含“产出什么结果”和“基于现有事项给你建议”。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `49 passed`
  - `docker exec graduation-project-api python -m compileall app/assistant_agents/specialists/task_or_event_clarifier.py tests/test_assistant_conductor.py` -> passed
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
- Current completion status:
  - Goal still not complete. This step removes one more template clarification fallback, but Phase 9 still has retained compatibility branches and not every clarification/negotiation surface is fully model/orchestration-derived.
- Next recommended action:
  - Continue scanning template clarification/negotiation branches for cases where `UnderstandingResult.orchestration` already carries enough structure but the specialist still falls through to hard-coded legacy wording.

## 进度更新 - 2026-05-09 01:20 +08:00

- Overall progress: 继续收回批量日程澄清的模板分支。`cancel_events_batch` / `reschedule_events_batch` 在 `UnderstandingResult.orchestration` 中已经有 `user_goal`、`proposal_shape` 与 `missing_information`，但缺日期/移动规则时仍落到旧 ambiguity 文案。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - `_build_orchestration_clarification()` 新增批量日程分支。
    - 覆盖 `cancel_events_batch` 与 `reschedule_events_batch`。
    - 将 `target_event` / `target_date` 映射为“要操作的日期或日期范围”，将 `batch_shift_days` 映射为“整体移动规则，比如推迟一天、提前两天，或改到某个日期”。
    - 命中后标记 `clarification_source="orchestration"`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 更新 `test_conductor_clarifies_batch_cancel_without_date()`，断言批量取消缺日期走 orchestration clarification。
    - 更新 `test_conductor_clarifies_batch_reschedule_without_shift_or_destination()`，断言批量改期缺移动规则走 orchestration clarification。
    - 更新 `test_conductor_clarifies_batch_reschedule_destination_without_source_date()`，断言“改到目标日期但缺源日期范围”走 orchestration clarification。
- Validation:
  - First targeted run exposed actual missing key was `target_event` rather than only `target_date`; mapping fixed.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `49 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api python -m compileall app/assistant_agents/specialists/task_or_event_clarifier.py tests/test_assistant_conductor.py` -> passed
- Current completion status:
  - Goal still not complete. More clarification fallback branches are now orchestration-aware, but compatibility fallback and some specialized legacy wording remain.
- Next recommended action:
  - Continue with remaining clarification branches where ambiguity-specific text can be derived from orchestration target scope and missing information, or run a focused audit to decide whether the residual specialized ambiguity text should remain as explicit compatibility fallback.

## 进度更新 - 2026-05-09 01:34 +08:00

- Overall progress: 继续收回单个日程更新澄清的模板分支。`cancel_event` / `reschedule_event` 在目标日程不明确、目标找不到、或改期缺新时间时，已经有 `orchestration.user_goal`、`target_scope.candidate_labels` 与 `missing_information`，但之前仍落到旧 ambiguity 文案。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - `_build_orchestration_clarification()` 新增单个日程更新分支。
    - 覆盖 `cancel_event`、`reschedule_event`、`complete_event`、`update_event`。
    - 将 `target_event` 映射为“要操作的具体日程”，将 `new_start_time` 映射为“新的日期和具体时间，或一个可选时间段”。
    - 回复中保留 `target_scope.candidate_labels`，用于目标不明确时展示候选日程。
    - 命中后标记 `clarification_source="orchestration"`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 更新 `test_conductor_clarifies_ambiguous_event_update_target()`，断言取消日程目标不明确走 orchestration clarification。
    - 新增 `test_conductor_uses_orchestration_clarification_for_missing_event_update_target()`。
    - 新增 `test_conductor_uses_orchestration_clarification_for_reschedule_missing_time()`。
    - 更新 `test_conductor_clarifies_pronoun_without_unique_context()`，断言指代消歧走 orchestration clarification 并保留候选日程。
- Validation:
  - First targeted run exposed existing pronoun clarification test still expected legacy wording; updated to the new orchestration wording.
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `51 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api python -m compileall app/assistant_agents/specialists/task_or_event_clarifier.py tests/test_assistant_conductor.py` -> passed
- Current completion status:
  - Goal still not complete. Event-update clarification is now substantially orchestration-driven, but retained compatibility fallback remains elsewhere and still requires final audit before completion.
- Next recommended action:
  - Continue with task-update clarification branches (`target_task_ambiguous`, `target_task_not_found`, `schedule_time_missing`) so task continuation/update clarification follows the same orchestration-first pattern.

## 进度更新 - 2026-05-09 01:41 +08:00

- Overall progress: 继续收回任务澄清的模板分支。任务继续排程与任务状态更新此前已有 `orchestration.user_goal`、`target_scope` 和 `missing_information`，但目标任务不明确/找不到、或继续排程缺时段时仍落到旧 task ambiguity 文案。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - `_build_orchestration_clarification()` 新增 `schedule_blocks` / `task_schedule_plan` 分支。
    - 将 `target_task` 映射为“要继续规划的具体任务”，将 `time_preferences` 映射为“希望安排到哪天、几点到几点，或可接受的时间段”。
    - 新增 `complete_task` / `update_target` 分支，将 `target_task` 映射为“要操作的具体任务”。
    - 回复保留 `target_scope.candidate_labels`，用于任务候选消歧。
    - 命中后标记 `clarification_source="orchestration"`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 新增 `test_conductor_uses_orchestration_clarification_for_missing_task_update_target()`。
    - 新增 `test_conductor_uses_orchestration_clarification_for_task_schedule_missing_target_and_time()`。
    - 新增 `test_conductor_uses_orchestration_clarification_for_task_schedule_missing_time()`。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py` -> `54 passed`
  - `docker exec graduation-project-api pytest -q tests/test_assistant_service.py` -> `37 passed`
  - `docker exec graduation-project-api python -m compileall app/assistant_agents/specialists/task_or_event_clarifier.py tests/test_assistant_conductor.py` -> passed
- Current completion status:
  - Goal still not complete. Clarification paths are now much more consistently orchestration-first, but full completion still requires a final audit of remaining fallback/legacy paths and a broader regression pass.
- Next recommended action:
  - Run a focused audit of `TaskOrEventClarifierSpecialist` to identify what remains intentionally specialized fallback versus accidental legacy template fallback, then either document the residual compatibility fallback or convert the remaining safe branches.

## 验证更新 - 2026-05-09 01:53 +08:00

- Backend full regression after the 2026-05-09 clarification/fallback changes:
  - `docker exec graduation-project-api pytest -q` -> `418 passed in 576.79s (0:09:36)`
- Updated validation baseline:
  - Phase 9 当前后端全量基线已从前一轮 `410 passed` 更新为 `418 passed`。
  - 新增测试覆盖了 streaming fallback gate、unknown/batch/event-update/task-update orchestration clarification。
- Current completion status:
  - Goal still not complete. Full regression is green, but completion still requires final audit against `goal.txt` and any remaining legacy fallback/compatibility branches.

## 进度更新 - 2026-05-09 01:57 +08:00

- Overall progress: 对 `TaskOrEventClarifierSpecialist` 做 focused audit 后，剩余旧文案主要是刻意保留的专用兜底，例如 `dating_request_too_vague`、批量范围过大、以及无可消费 orchestration 的最后兜底。为后续完成审计区分“已消费 orchestration”与“刻意保留兼容兜底”，现在对残余专用分支显式打标。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\assistant_agents\specialists\task_or_event_clarifier.py`
    - 当 `understanding.orchestration` 存在但 `_build_orchestration_clarification()` 没有返回问题时，进入 legacy/specialized 分支前写入 `clarification_source="specialized_fallback"`。
    - 已经成功被 orchestration 消费的分支仍保持 `clarification_source="orchestration"`。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - `test_conductor_clarifies_vague_dating_request()` 现在断言该路径是 `specialized_fallback`，明确这是刻意保留的专用澄清，而不是未审计的模板漏网。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py tests/test_assistant_service.py` -> `91 passed`
  - `docker exec graduation-project-api python -m compileall app/assistant_agents/specialists/task_or_event_clarifier.py tests/test_assistant_conductor.py` -> passed
- Current completion status:
  - Goal still not complete. Clarification specialist 的剩余 fallback 已可审计地区分，但 `AssistantService` 层 `_build_plan()` compatibility fallback 仍需要最终审计/决策。
- Next recommended action:
  - 转向 `AssistantService` compatibility fallback：列出 proposal/primary 下仍可能调用 `_build_plan()` 的路径，判断是否应继续保留、改为 explicit compatibility mode，或在 proposal mode 下默认阻断。

## 进度更新 - 2026-05-09 02:15 +08:00

- Overall progress: 完成 `AssistantService` 层一个关键 fallback 收缩：在 `proposal/primary` 模式下，只要 conductor 已经返回结果，REST 与 streaming 路径都不再默认进入 `_build_plan()` compatibility fallback。`_build_plan()` 现在只保留给 legacy/shadow 或 conductor 未运行/无结果的兼容路径。
- Files changed in this step:
  - `E:\GraduationProject\backend\app\services\assistant.py`
    - 新增 `_should_use_plan_compatibility_fallback()`。
    - REST `send_message()` 在 workflow fallback 之后、调用 `_build_plan()` 之前检查该 gate；proposal/primary + conductor result 时直接返回 `_primary_mode_fallback_reply()`，并持久化 assistant message。
    - Streaming `send_message_stream()` 同步使用该 gate；proposal/primary + conductor result 时不进入 Gemini streaming plan，也不进入 `_build_plan()`，直接流式返回 blocked fallback reply。
    - Pending action decision 仍保留在 gate 之前，避免误伤旧 pending action 确认兼容路径。
  - `E:\GraduationProject\backend\tests\test_assistant_conductor.py`
    - 更新 `test_send_message_proposal_mode_does_not_use_workflow_as_default_fallback()`：现在断言 proposal-mode conductor 已运行后既不走 workflow，也不走 `_build_plan()`，而是返回“旧的规则回退链路”阻断回复。
    - 更新 `test_send_message_stream_proposal_mode_does_not_use_gemini_stream_as_default_fallback()`：现在断言 streaming 路径也不走 Gemini streaming plan 或 `_build_plan()`。
- Validation:
  - `docker exec graduation-project-api pytest -q tests/test_assistant_conductor.py tests/test_assistant_service.py` -> `91 passed`
  - `docker exec graduation-project-api python -m compileall app/services/assistant.py tests/test_assistant_conductor.py` -> passed
  - `docker exec graduation-project-api pytest -q` -> `418 passed in 578.63s (0:09:38)`
- Current completion status:
  - Goal still not complete pending final audit, but the largest remaining default legacy fallback is now gated: proposal/primary conductor output no longer falls through to `_build_plan()` by default.
- Next recommended action:
  - Perform a completion audit against `goal.txt`: verify model-led orchestration, proposal-first execution, confirmation-before-write, memory/proactive evidence, UI smoke, workflow fallback gating, `_build_plan()` compatibility gating, and residual specialized fallbacks.

## 最终完成审计 - 2026-05-09 02:19 +08:00

- Objective restatement:
  - 完成 `E:\GraduationProject\docs\development\goal.txt`：继续 Phase 9，直到 AI 助手从“规则前置决策 + 多套 fallback 的 proposal 外壳”迁移到“模型/Conductor 主导语义编排 + proposal-first 执行边界 + 用户确认后执行 + 长期记忆 + 主动跟进”的统一主控路径。
  - 当前重点是收回 legacy workflow / `_build_plan()` / 模板澄清的主导权，并完成真实系统级 smoke + 全量回归 + 文档收口。
- Prompt-to-artifact checklist:
  - 高频 answer-like 场景切出 orchestration direct path:
    - Evidence: `schedule_guidance`、`progress_followup`、`event_context_advice` 均有 `conversation_mode="answer"` / `_maybe_build_orchestration_answer_plan()` direct path。
    - Evidence: conductor/service 回归覆盖不进入 workflow / `_build_plan()`。
  - proposal-first / confirmation-before-write:
    - Evidence: service-level smoke 覆盖 create event 只创建 pending proposal；确认文本后才执行。
    - Evidence: final runtime smoke after latest fallback gate:
      - `GET /api/health` -> `ok`, `database_ready=true`
      - isolated user `final-smoke-1778264359`
      - `POST /api/assistant/message` -> reply contained `待确认方案`
      - pending event_creation proposal `39`, status `pending`
      - `POST /api/assistant/proposals/39/confirm` -> status `executed`, related event `57`
      - `GET /api/events` read back event `57`, title `和同学见面`
      - cleanup `DELETE /api/events/57` -> `200`
      - pending event_creation after cleanup -> `0`
  - workflow fallback 降级:
    - Evidence: `_should_use_workflow_fallback()` returns false in proposal/primary when conductor returned a result。
    - Evidence: regression asserts proposal-mode conductor output does not default to workflow fallback。
  - `_build_plan()` compatibility fallback 降级:
    - Evidence: `_should_use_plan_compatibility_fallback()` blocks REST and streaming `_build_plan()` fallback in proposal/primary after conductor result。
    - Evidence: regressions assert both REST and streaming paths do not call `_build_plan()` after proposal-mode conductor result。
  - streaming fallback 降级:
    - Evidence: `_should_use_streaming_plan_fallback()` blocks Gemini streaming plan fallback in proposal/primary after conductor result。
    - Evidence: streaming regression asserts Gemini streaming plan fallback is not called。
  - 模板 clarification 降级:
    - Evidence: `TaskOrEventClarifierSpecialist` now consumes `OrchestrationAssessment` for unknown, create task/event, batch event update, single event update, task continuation, and task update clarification。
    - Evidence: successful orchestration clarification paths mark `clarification_source="orchestration"`。
    - Evidence: residual specialized fallback paths are explicitly marked `clarification_source="specialized_fallback"` for auditability。
  - negotiation 模板降级:
    - Evidence: `NegotiationSpecialist` uses orchestration-aware wording for task schedule, event reschedule, event creation, task creation, event cancel/status/batch updates, and task status update。
    - Evidence: covered proposal replies mark `proposal_reply_source="orchestration"`。
  - 长期记忆:
    - Evidence: Phase 8 implementation exists for memory candidates, confirm/reject, `.md` write boundary, frontend pending memory UI。
    - Evidence: Phase 9 supplemental runtime smoke wrote and read back isolated memory candidate, then cleaned memory directory。
    - Evidence: Phase 9 frontend UI smoke showed `待确认记忆` and `写入记忆` surface。
  - 主动跟进:
    - Evidence: Phase 7 signal/heartbeat infrastructure and signal -> proposal conversion exist。
    - Evidence: Phase 9 supplemental runtime smoke created deadline-risk signal, converted signal to pending proposal, and verified signal status。
    - Evidence: `progress_followup` now has orchestration answer path。
  - 前端/UI:
    - Evidence: Playwright UI smoke after Phase 9 showed `待确认方案`、`待确认记忆`、`确认`、`写入记忆` in assistant tab。
  - Regression gate:
    - Evidence: targeted conductor/service regressions after latest changes -> `91 passed`。
    - Evidence: compileall after latest changes -> passed。
    - Evidence: backend full regression after latest `_build_plan()` gate -> `418 passed in 578.63s (0:09:38)`。
- Residual risks / explicit compatibility:
  - `legacy` / `shadow` modes still retain compatibility paths by design.
  - Some highly specialized clarification text remains as `specialized_fallback`, but it is no longer untracked template dominance; it is explicitly marked and only used when the orchestration branch does not produce a better question.
  - The task book and code still use deterministic specialist logic around the Conductor; this Phase 9 completion means the main control path is Conductor/orchestration-led and no longer defaults to legacy workflow / `_build_plan()` in proposal/primary mode.
- Completion decision:
  - Complete for `goal.txt`.
  - Reason: every explicit deliverable in `goal.txt` now has concrete code evidence, regression evidence, runtime/API smoke evidence, UI evidence, and documented residual compatibility boundaries.

## 进度更新 - 2026-05-10 21:00 +08:00

- Trigger:
  - 用户重新打开更严格目标：旧结论仍未满足预期，要求彻底移除程序强拆语句与老旧 workflow，并新增 DeepSeek/SiliconFlow 作为首选 LLM API、Gemini 作为备选。
- Overall progress:
  - LLM provider 已从单一 Gemini 改为 DeepSeek/SiliconFlow primary + Gemini fallback。
  - 旧 `backend/app/workflow/` LangGraph workflow 包已物理删除；`AssistantService` 不再 import、构建、调用或保留 workflow fallback / stream fallback 方法。
  - `ENABLE_WORKFLOW / ENABLE_REACT_SUBGRAPH / ROUTE_CONFIDENCE_THRESHOLD` 已从后端配置和 `.env.example` 移除。
  - `/api/debug/workflow/*` 旧调试接口已移除。
  - 改期 proposal 修复：用户只说“改到 4 点”时保留原日程时长，不再由时间解析默认 60 分钟覆盖。
- Files changed in this step:
  - `backend/app/tools/gemini.py`
    - 保持 `GeminiClient` 兼容类名，但内部按 provider order 调度。
    - `LLM_PROVIDER=deepseek` 时调用 `https://api.siliconflow.cn/v1/chat/completions`。
    - DeepSeek 失败时自动尝试 `LLM_FALLBACK_PROVIDER=gemini`。
  - `backend/app/core/config.py`
    - 新增 `LLM_FALLBACK_PROVIDER`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL` 与 DeepSeek timeout/retry 参数。
    - 移除旧 workflow 相关配置项。
  - `backend/app/api/routes/health.py` / `backend/app/api/schemas.py`
    - `/api/health/ai` 现在返回 primary provider 与 fallback provider。
  - `backend/app/services/assistant.py`
    - 删除 workflow import、workflow graph 初始化、workflow fallback gate、`_run_workflow_for_message()`、`_respond_with_workflow()`、`_respond_with_workflow_stream()`。
  - `backend/app/api/routes/debug.py`
    - 删除 `/debug/workflow/summary` 和 `/debug/workflow/diagram`。
  - `backend/app/workflow/*`
    - 已删除。
  - `backend/tests/test_workflow.py` / `backend/tests/test_workflow_memory_context.py`
    - 已删除，避免继续为已退役 workflow 建立回归约束。
  - `backend/tests/test_llm_client.py`
    - 新增 DeepSeek primary -> Gemini fallback 调度测试。
  - `.env.example`
    - 更新为 DeepSeek primary + Gemini fallback 示例，不包含真实密钥。
- Validation:
  - DeepSeek/SiliconFlow real connectivity using local `.env` key and Bearer auth:
    - `POST https://api.siliconflow.cn/v1/chat/completions` -> `status=200`
  - Source audit:
    - `rg -n "workflow|Workflow|LangGraph|react_subgraph|react_tools|ENABLE_WORKFLOW|ENABLE_REACT_SUBGRAPH|ROUTE_CONFIDENCE" backend\app backend\tests .env .env.example -S` -> no matches.
  - Targeted regression:
    - `.venv312\Scripts\python.exe -m pytest -q tests\test_llm_client.py tests\test_assistant_conductor.py tests\test_assistant_service.py tests\test_api.py` -> `114 passed`.
  - Compile:
    - `.venv312\Scripts\python.exe -m compileall app` -> passed.
  - Backend full regression:
    - `.venv312\Scripts\python.exe -m pytest -q` -> `395 passed, 3 warnings in 116.48s`.
- Current completion status:
  - Still not complete for the reopened user objective.
  - Reason: backend code and LLM provider changes are now green, but the reopened objective explicitly asks for browser-level scenario acceptance after refactor. Browser/API scenario smoke still needs to be rerun against the current server state, and final completion audit must map each new requirement to evidence.
- Next action:
  - Start/restart backend/frontend as needed, run the prepared acceptance scenarios through browser/API, then perform final audit against: no hard sentence splitting, no old workflow, DeepSeek primary/Gemini fallback, proposal-first multi-agent assistant, confirm-before-write.

## 进度更新 - 2026-05-10 21:25 +08:00

- Overall progress:
  - Reopened objective 的运行态验收已补齐。
  - 后端在 `127.0.0.1:8000` 与 `127.0.0.1:8013` 使用同一 smoke DB 启动，前端 Vite 在 `127.0.0.1:8888` 启动。
  - 前端默认 API 指向 `127.0.0.1:8000`，因此浏览器 smoke 使用 8000 端口后端完成。
- Runtime environment evidence:
  - `GET http://127.0.0.1:8000/api/health/ai` -> `{"enabled":true,"provider":"deepseek","fallback_provider":"gemini",...}`
  - `GET http://127.0.0.1:8888` -> HTTP 200.
- API acceptance evidence:
  - Scenario A: proposal-first / confirm-before-write / confirm idempotency.
    - User: `acceptance-20260510`
    - Message: `明天下午3点我要去学校和同学见面`
    - Result before confirm:
      - assistant reply contained `待确认方案`
      - pending proposal count `1`
      - event count remained `0`
    - Confirm `option_id=A`:
      - proposal status -> `executed`
      - related event id -> `1`
      - event count -> `1`
    - Repeat confirm:
      - status remained `executed`
      - related event id remained `1`
      - event count remained `1`
    - Cleanup:
      - temporary event deleted.
  - Scenario B: no hard sentence splitting.
    - User: `acceptance-split-20260510`
    - Message: `中午12点我要去驾校接李婷`
    - Proposal action payload:
      - `title = 去驾校接李婷`
      - `location_name = 驾校`
      - `has_bad_title = false` for `点我要`
      - `has_bad_location = false` for `接李婷`
    - Proposal rejected after verification; no event write performed.
- Browser acceptance evidence:
  - Playwright opened `http://127.0.0.1:8888`, navigated to `助手`.
  - Submitted `中午12点我要去驾校接李婷`.
  - UI displayed:
    - `待确认方案`
    - `P1`
    - `建议创建日程“去驾校接李婷”：05-10 12:00-13:00，地点：驾校`
    - `确认`
  - Clicking `确认` executed the proposal.
  - API readback for `local-user`:
    - events count `1`
    - event title `去驾校接李婷`
    - proposal status `executed`
    - related event id `1`
  - Cleanup:
    - temporary UI smoke event deleted; local-user event count returned to `0`.
- Additional source audit:
  - `rg -n "workflow|Workflow|LangGraph|react_subgraph|react_tools|ENABLE_WORKFLOW|ENABLE_REACT_SUBGRAPH|ROUTE_CONFIDENCE" backend\app backend\tests .env .env.example -S` -> no matches.
  - `backend/app/workflow/` directory removed.
- Current completion status:
  - Ready for final completion audit against reopened objective.

## 验收更新 - 2026-05-15 02:52 +08:00

- Trigger:
  - 继续按 `docs/development/AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md` 做最终完成审计，要求只在当前代码、测试、浏览器/API 证据均能支撑时收口。
- Fixes in this checkpoint:
  - `backend/app/core/config.py` / `backend/app/main.py`
    - CORS 从固定端口白名单改为可配置 `CORS_ALLOWED_ORIGINS`，并增加默认 `CORS_ALLOW_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1):\d+`，解决临时 Vite 端口浏览器验收被 CORS 拦截的问题。
  - `backend/tests/test_api.py`
    - 删除已退役 workflow debug endpoint 的回归测试，改为覆盖 `http://127.0.0.1:8891` 预检请求。
  - `.env.example`
    - 增加 `API_HOST_PORT` 与 CORS 示例配置。
  - `docker-compose.yml`
    - API host port 改为 `${API_HOST_PORT:-8000}:8000`，避免 Windows 主机上 8000 被占用时无法启动容器。
- Runtime/browser evidence:
  - 本地 API 使用隔离 DB `backend/data/browser_acceptance_18714.db` 跑在 `127.0.0.1:18714`，前端 Vite 跑在 `127.0.0.1:8891` 且 `VITE_API_BASE_URL=http://127.0.0.1:18714/api`。
  - 浏览器输入 `中午12点我要去驾校接李婷` 后，UI 正确显示 `待确认方案`、`P1`、`建议创建日程“去驾校接李婷”：05-15 12:00-13:00，地点：驾校`、`确认`。
  - 未确认前日历为 `0 个事件`；点击确认后 `POST /api/assistant/proposals/4/confirm => 200`，日历变为 `1 个事件`，标题为 `去驾校接李婷`。
  - 重复确认同一 proposal 后状态保持 `executed`，`related_event_id=1`，事件数量保持 `1`。
  - 清理临时事件后 pending proposal 为 `0`。
  - 干净用户 API hard-split smoke 验证同句 payload：`title=去驾校接李婷`、`location=驾校`、`bad_split=False`；proposal 已拒绝且未落库。
  - Docker API 使用 `API_HOST_PORT=18716 docker compose up -d api` 可启动；`GET http://127.0.0.1:18716/api/health` 返回 `ok` 且 `database_ready=true`。
- Current validation rerun:
  - `.\.venv312\Scripts\python.exe -m pytest -q tests/test_api.py::test_cors_allows_localhost_dev_ports tests/test_api.py::test_health_endpoint tests/test_llm_client.py tests/test_assistant_text_protocol.py tests/test_assistant_conductor.py tests/test_assistant_service.py tests/test_assistant_proposal_manager.py tests/test_assistant_proposal_revise.py tests/test_assistant_action_executor.py tests/test_assistant_memory_capture.py tests/test_assistant_signal_to_proposal.py tests/test_assistant_proposal_expiry.py` -> `201 passed in 51.65s`
  - `pnpm exec vue-tsc --noEmit` -> passed
  - `pnpm run build` -> passed
  - `rg -n "workflow|Workflow|LangGraph|react_subgraph|react_tools|ENABLE_WORKFLOW|ENABLE_REACT_SUBGRAPH|ROUTE_CONFIDENCE|点按钮|点击这里" backend\app backend\tests frontend\src .env.example -S` -> no matches
- Acceptance audit against `AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`:
  - P0 automation coverage is satisfied by the current focused regression set plus browser/API smoke: proposal-first creation, single confirm execution, duplicate confirm idempotency, ambiguity clarification, revise/reject, expired/superseded, execution_failed/retry, no direct write before confirmation, no hard sentence split, and no retired workflow/debug wording.
  - P1 coverage is tracked by existing targeted tests for signal cooldown/dedup, signal -> proposal, memory candidate confirm/reject/no implicit write, departure/deadline signals, provider fallback, CORS/dev-port browser recovery, frontend pending proposal surface, and build/typecheck gates. Browser-level coverage is not exhaustive for every P1 narrative scenario, but remaining low-risk variants are covered by unit/API tests and task-book tracking.
  - Proposal state transitions covered in current tests: `pending`, `executed`, `rejected`, `superseded`, `expired`, `execution_failed`.
  - Proactive follow-up boundaries covered by signal dedup/cooldown tests and signal-to-proposal tests; active runtime remains gated by `ASSISTANT_PROACTIVE_MODE`.
  - Refresh/mobile/network failure class: pending proposal state is persisted server-side; CORS/dev-port failure was the only browser blocker found in this checkpoint and has been fixed with a regression test.
- Completion decision:
  - Complete for the current objective.
  - Reason: the current code removes old workflow paths, keeps DeepSeek/SiliconFlow primary with Gemini fallback, enforces proposal-first and confirm-before-write boundaries, passes focused backend/frontend gates, and has real browser/API evidence for the highest-risk P0 flow and the hard-split regression.
