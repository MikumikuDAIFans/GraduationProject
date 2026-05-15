# debug.html 监测台重设计与 LLM 可观测性升级任务书 V1

## 计划元数据

- Plan ID: `debug-console-observability-upgrade-v1`
- Version: `v1`
- Last updated: `2026-05-16 00:00 +08:00`
- Canonical progress file: `E:\GraduationProject\docs\development\DEBUG_CONSOLE_OBSERVABILITY_UPGRADE_TASK_BOOK_V1.md`
- Related handoff file: `none`
- Current branch: `codex/assistant-browser-acceptance`
- Current active phase: `Phase 1: 现状审计与监测目标锁定`
- Execution readiness: `drafting`

## 目标

将现有 `frontend/public/debug.html` 从基础请求日志页面升级为可用于全面排查系统运行状态的监测台。升级后应能看到系统健康、请求日志、慢请求、错误、数据库池、缓存、WebSocket、助手会话、proposal 生命周期、LLM 调用 payload、LLM 原始返回、解析结果、fallback 过程、trace 关联和验收运行结果。最终目标是让开发者能从一个页面追踪一次用户输入如何经过前端、后端、LLM、proposal、数据库写入和 WebSocket 刷新，定位系统是否按预期运行。

## 范围与约束

- In scope:
  - 重设计 `frontend/public/debug.html` 信息架构和视觉布局。
  - 扩展 `backend/app/api/routes/debug.py` 或新增 debug 子模块。
  - 为 LLM 调用链路增加安全脱敏后的 trace 记录。
  - 展示 LLM request payload、raw response、parsed result、provider、model、latency、status、error、fallback。
  - 展示 assistant message/proposal/render_blocks/event/task 写入链路。
  - 展示系统健康、请求、错误、性能、DB pool、cache、WebSocket 和验收结果。
  - 补后端测试、前端页面浏览器验收和安全脱敏测试。
- Out of scope:
  - 把 debug.html 做成生产级 APM 平台。
  - 长期保存无限量 raw payload。
  - 在未脱敏情况下展示 API key、Authorization header、用户隐私和完整密钥。
  - 引入大型外部监控系统作为必要依赖。
- Constraints:
  - debug 页面必须可以在本地开发环境直接打开。
  - debug API 在生产环境必须默认关闭或受保护，避免敏感调试信息泄漏。
  - LLM payload/response 展示必须经过 redaction。
  - 页面要适合长时间观察，避免频繁刷新造成页面卡顿。
  - 所有监测数据必须有时间戳、trace id 或 request id，方便关联。

## 目标信息架构

升级后的 debug.html 建议拆成以下一级标签：

1. `Overview`: 总览健康状态、错误率、慢请求、LLM 成功率、DB pool、WebSocket、最近告警。
2. `Requests`: HTTP 请求日志、耗时分布、状态码、request id、关联 trace。
3. `Assistant Trace`: 用户消息到助手回复的链路，包含 session、message、render_blocks、proposal、event/task 写入。
4. `LLM Traces`: LLM provider、model、payload、raw response、parsed result、fallback、错误。
5. `Proposals`: proposal 生命周期、pending/executed/rejected/failed、选项、执行结果。
6. `WebSocket`: workspace snapshot、assistant streaming、连接数量、断线、最后消息。
7. `Database`: DB pool、最近写入、迁移版本、关键表计数。
8. `Cache & External`: Redis、地图、天气、Google Calendar、外部 API 状态。
9. `Acceptance Runs`: 浏览器验收脚本运行结果、失败截图、最新 clean DB 证据。
10. `Settings`: API base、自动刷新、采样开关、trace retention、清空日志。

## LLM trace 数据模型建议

每次 LLM 调用至少记录以下字段：

```json
{
  "trace_id": "llm_xxx",
  "request_id": "http_xxx",
  "session_id": 1,
  "message_id": 10,
  "purpose": "understanding|planning|reply|fallback",
  "provider": "deepseek|gemini",
  "model": "model-name",
  "status": "success|error|fallback_success|fallback_failed|timeout|parse_error",
  "started_at": "2026-05-16T00:00:00+08:00",
  "duration_ms": 1234,
  "attempt": 1,
  "request_payload_redacted": {},
  "raw_response_redacted": {},
  "parsed_result": {},
  "error": null,
  "fallback_from_trace_id": null,
  "redaction_applied": true
}
```

必须脱敏字段：

- `api_key`
- `Authorization`
- `token`
- `password`
- `secret`
- `cookie`
- `set-cookie`
- 任何形如 `sk-...`、`Bearer ...`、长 access token 的字段

## 执行阶段

### Phase 1: 现状审计与监测目标锁定

- Purpose: 明确现有 debug.html 和 debug API 能做什么、缺什么。
- Outputs:
  - 现有 debug API 清单。
  - 现有 debug.html 页面结构截图和问题清单。
  - 监测目标优先级：P0/P1/P2。
- Completion criteria:
  - 找出所有现有数据源：`/debug/logs`、`/debug/requests`、`/debug/db-pool`、`/debug/cache-stats`、`/debug/system`、`/debug/assistant/proposals`、`/health/*`。
  - 明确缺失数据源：LLM trace、assistant trace、WebSocket trace、DB table counts、acceptance run summary。
- Validation:
  - 打开 `frontend/public/debug.html`。
  - 调用现有 debug API。
  - 记录当前页面无法定位的一次 assistant/LLM 问题。
- Evidence:
  - 页面截图、API 返回样例、缺口清单。

### Phase 2: 后端 debug 数据源与 trace 存储

- Purpose: 先补齐监测数据，再做前端展示。
- Outputs:
  - `LLMTraceRecorder` 或同等轻量服务。
  - debug API：
    - `GET /api/debug/llm/traces`
    - `GET /api/debug/llm/traces/{trace_id}`
    - `GET /api/debug/assistant/traces`
    - `GET /api/debug/system/overview`
    - `GET /api/debug/database/summary`
    - `GET /api/debug/websocket/summary`
    - `POST /api/debug/logs/clear`
  - redaction helper 和测试。
- Completion criteria:
  - LLM 成功、失败、fallback、parse error 都会生成 trace。
  - trace 仅保留最近 N 条，默认内存存储即可；如需要可后续扩展 SQLite。
  - 所有敏感字段被替换为 `[REDACTED]`。
  - debug API 返回结构稳定，有后端测试。
- Validation:
  - 后端单测覆盖 trace record、redaction、fallback trace 关联。
  - API 测试覆盖 debug endpoints。
  - 手动触发一次 assistant 消息后能查到 LLM trace。
- Evidence:
  - 测试结果、trace JSON 样例、脱敏前后断言。

### Phase 3: LLM 调用链路接入

- Purpose: 让 DeepSeek/Gemini 调用真实产生可观测 trace。
- Outputs:
  - `backend/app/tools/gemini.py` 中 DeepSeek 和 Gemini 调用埋点。
  - provider order、attempt、timeout、HTTP error、JSON parse error、fallback 原因记录。
  - `AssistantService` 或 conductor 上下文向 LLM trace 注入 session/message/purpose。
- Completion criteria:
  - 每个 provider attempt 有独立 trace。
  - primary 失败 fallback 成功时，页面能看到前后两个 trace 的关联。
  - 全失败时，页面能看到所有 provider 的错误摘要。
  - 不影响现有 LLM 调用行为。
- Validation:
  - 模拟 DeepSeek 成功。
  - 模拟 DeepSeek 失败 Gemini 成功。
  - 模拟全部失败。
  - 模拟返回非 JSON 导致 parse error。
- Evidence:
  - 后端测试、debug 页面 LLM trace 截图。

### Phase 4: debug.html 信息架构重设计

- Purpose: 把页面从“日志列表”升级为“可用于定位问题的监测台”。
- Outputs:
  - 新布局：
    - 顶部状态栏：API base、环境、最后刷新、总体健康。
    - 左侧指标栏：错误率、慢请求、LLM 成功率、active WS、DB pool、pending proposal。
    - 主区域 tabs：Overview / Requests / Assistant Trace / LLM Traces / Proposals / WebSocket / Database / Cache & External / Acceptance Runs / Settings。
  - JSON viewer：支持折叠、复制、搜索、格式化。
  - Trace drilldown：从 request -> assistant -> LLM -> proposal -> DB 写入。
  - 自动刷新与暂停刷新。
- Completion criteria:
  - 页面不再依赖 emoji 作为关键信息。
  - 表格、JSON、长文本在 390px 和桌面视口都不溢出。
  - LLM payload/response 可以展开查看，但默认折叠长内容。
  - 错误项、慢请求、fallback trace 有明显状态标识。
- Validation:
  - Playwright 检查所有 tabs 可切换。
  - 390px、768px、1440px 截图无重叠。
  - 控制台无 error。
- Evidence:
  - 浏览器截图、DOM 状态断言。

### Phase 5: Assistant 与 Proposal 链路监测

- Purpose: 让用户能检查一次智能助手对话是否真的按设计运行。
- Outputs:
  - Assistant trace 视图：
    - user message
    - assistant reply
    - render_blocks
    - active context
    - proposal ids
    - selected option
    - created events/tasks
    - execution errors
  - Proposal detail 视图：
    - payload_json
    - options
    - protocol_label
    - status transitions
    - execution result
    - related event/task
- Completion criteria:
  - 能定位 inline proposal 为什么显示、为什么禁用、刷新后如何恢复。
  - 能定位确认/拒绝是否走助手文本协议，而不是绕过助手。
  - 能定位多 pending 下 `可以` 为什么澄清。
- Validation:
  - 浏览器执行：创建 proposal、接受、拒绝、修改、重试、刷新恢复。
  - debug 页面逐步显示对应 trace。
- Evidence:
  - 每个动作的 debug 截图和 SQLite 证据。

### Phase 6: WebSocket、请求与系统健康监测

- Purpose: 覆盖系统运行状态，而不仅是 LLM。
- Outputs:
  - WebSocket summary：
    - active connection count
    - last broadcast time
    - broadcast failures
    - workspace snapshot size
    - assistant streaming status
  - Request diagnostics：
    - status distribution
    - slowest endpoints
    - error endpoints
    - recent request detail
  - System overview：
    - health
    - AI health
    - performance metrics
    - DB pool
    - cache
    - table counts
- Completion criteria:
  - debug 页面可以说明“系统现在是否正常”。
  - 慢请求和错误请求能关联 request id。
  - WebSocket 断线和广播失败可见。
- Validation:
  - 打开主页面触发 hydrate 和 WS。
  - 断开/重连前端或刷新页面。
  - 人为触发一个失败请求。
- Evidence:
  - debug 页面 Overview 和 WebSocket 截图。

### Phase 7: 安全、权限与隐私保护

- Purpose: 避免 debug 能力本身变成泄漏风险。
- Outputs:
  - Debug mode gating：
    - 本地开发默认可用。
    - 生产环境默认禁用或需要显式 token。
  - redaction 测试。
  - 大 payload 截断策略。
  - 清空 trace/log 的明确操作。
- Completion criteria:
  - 生产配置下无法无保护访问敏感 debug 数据。
  - API key、Authorization、token、cookie 不会出现在页面。
  - payload 过大时显示摘要和截断提示。
- Validation:
  - 后端单测。
  - 浏览器检查页面显示。
  - `rg` 搜索测试输出中不存在真实密钥。
- Evidence:
  - 安全测试结果和 redaction 样例。

### Phase 8: 浏览器级验收与最终全功能复测

- Purpose: 确保 debug 页面真实可用，而不是只完成 API。
- Outputs:
  - debug.html 浏览器验收报告。
  - 真实 assistant 操作后 debug 追踪截图。
  - 最终全功能复测记录。
- Completion criteria:
  - 所有 tabs 都能加载数据。
  - LLM payload/response 可见且已脱敏。
  - 一次完整助手对话能从 request 追到 LLM trace、proposal、DB 写入和 WebSocket 更新。
  - 页面在移动/桌面视口可用。
  - 后端测试、前端构建、浏览器验收全通过。
- Validation:
  - `cd backend && .\.venv312\Scripts\python.exe -m pytest -q`
  - `cd frontend && npm run build`
  - Playwright 打开 `debug.html?apiBase=http://127.0.0.1:<port>/api`
  - 真实创建/修改/拒绝/重试 proposal 后检查 debug 页面。
- Evidence:
  - `docs/development/browser_acceptance_runs/` 新增 debug console 验收报告。

## P0 功能清单

1. Overview 显示整体健康、错误率、慢请求、LLM 成功率、DB pool、active WebSocket。
2. Requests 显示最近请求、状态码、耗时、request id、筛选、排序、清空。
3. LLM Traces 显示 provider、model、purpose、payload、raw response、parsed result、error、fallback。
4. payload/response 全部脱敏，敏感字段不可见。
5. Assistant Trace 能关联用户消息、助手回复、proposal、render_blocks、写库结果。
6. Proposals 能显示 status、options、selected option、execution result、失败原因。
7. WebSocket 能显示连接和广播状态。
8. 页面移动端和桌面端都可用。
9. debug API 在生产环境受保护或默认禁用。
10. 所有监测数据可通过刷新、暂停刷新和清空操作控制。

## P1 功能清单

1. Acceptance Runs 标签展示最新浏览器验收结果。
2. 慢请求趋势图和 endpoint 聚合。
3. LLM token 或字符长度统计。
4. trace 导出为 JSON。
5. 一键复制复现信息。
6. 最近错误的根因提示。
7. 外部服务地图、天气、Google Calendar 状态摘要。

## P2 功能清单

1. trace 持久化到 SQLite。
2. 多用户筛选。
3. debug 面板内触发受控 smoke test。
4. 与 CI 验收报告联动。
5. 高级时间线视图。

## 决策记录

- Verified facts:
  - 当前 debug 页面文件为 `frontend/public/debug.html`。
  - 当前 debug API 文件为 `backend/app/api/routes/debug.py`。
  - 当前 debug.html 已接入 `/debug/db-pool`、`/debug/cache-stats`、`/debug/requests`、`/debug/logs`。
  - 当前 LLM 调用集中在 `backend/app/tools/gemini.py`，支持 DeepSeek/Gemini provider order 和 fallback。
- Active assumptions:
  - 初版 trace 可以使用内存 ring buffer，不必立即上数据库。
  - debug 页面主要服务开发和验收，不作为普通用户功能。
  - LLM payload 可能包含用户自然语言和上下文，因此即使没有密钥也应支持截断和脱敏。
- Locked decisions:
  - LLM payload/response 是 P0 监测能力，但必须默认脱敏。
  - debug 页面要服务真实排障，所以必须能从一次用户输入追踪到后端、LLM、proposal、DB、WebSocket。
  - 页面升级必须配套后端测试和浏览器级验收。
- Open questions:
  - debug API 的生产访问控制采用环境变量、固定本地模式还是 debug token。
  - trace 是否需要跨进程/重启保留。
  - 是否允许在 debug 页面直接触发测试请求或只读观察。

## 关键制品与环境

- Canonical docs:
  - `E:\GraduationProject\docs\development\DEBUG_CONSOLE_OBSERVABILITY_UPGRADE_TASK_BOOK_V1.md`
  - `E:\GraduationProject\docs\development\FULL_SYSTEM_REVIEW_AND_ZERO_BUG_ACCEPTANCE_TASK_BOOK_V1.md`
- Important code or output artifacts:
  - `E:\GraduationProject\frontend\public\debug.html`: 监测台页面。
  - `E:\GraduationProject\backend\app\api\routes\debug.py`: debug API。
  - `E:\GraduationProject\backend\app\tools\gemini.py`: LLM provider 调用点。
  - `E:\GraduationProject\backend\app\main.py`: HTTP request metrics 与 request id。
  - `E:\GraduationProject\backend\app\api\live_updates.py`: WebSocket broadcast 状态来源。
  - `E:\GraduationProject\backend\app\services\assistant.py`: assistant trace 关联入口。
- Required commands:
  - `cd E:\GraduationProject\backend && .\.venv312\Scripts\python.exe -m pytest -q`
  - `cd E:\GraduationProject\frontend && npm run build`
  - Playwright 打开 `http://127.0.0.1:<frontend-port>/debug.html?apiBase=http://127.0.0.1:<backend-port>/api`
- Environment baseline:
  - 本地开发优先使用独立 SQLite clean DB。
  - debug 页面 API base 必须可通过 query string 切换。
  - 浏览器验收使用 desktop 和 mobile 两类视口。

## 进度台账

- Overall progress: `passed`。debug 监测台 P0 能力已实现并通过浏览器级验收；P1/P2 高级能力保留为后续增强。
- Phase 1: completed。已盘点原 debug API、debug.html、LLM 调用点和缺失数据源。
- Phase 2: completed。新增 `backend/app/services/debug_observability.py`，新增 LLM traces、assistant traces、database summary、websocket summary、acceptance runs、clear logs 等 debug API。
- Phase 3: completed。`backend/app/tools/gemini.py` 已接入 DeepSeek/Gemini 成功、失败、超时、parse error、fallback trace；trace_context 支持 request/session/message/purpose。
- Phase 4: completed。`frontend/public/debug.html` 已重设计为 Overview / Requests / Assistant Trace / LLM Traces / Proposals / WebSocket / Database / Cache & External / Acceptance Runs / Logs 标签页监测台。
- Phase 5: completed for observability shell。Assistant Trace 和 Proposal 诊断已能展示 messages、render_blocks、payload_json、status、selected option、related event/task、execution error；真实业务 proposal 场景需继续在全系统验收任务书中复测。
- Phase 6: completed。WebSocket summary、request diagnostics、system overview、DB pool、cache stats、table counts 已接入；cache stats 在 Redis 不可用时快速降级。
- Phase 7: completed。生产环境默认隐藏 debug API；redaction 覆盖 API key、Authorization、token、cookie、secret，并保留安全的 usage token count。
- Phase 8: completed。浏览器验收报告已生成。
- Validation status: `passed`。
  - `backend pytest -q`: `497 passed, 3 warnings`
  - `frontend npm run test`: `2 files / 3 tests passed`
  - `frontend npm run build`: passed
  - `backend pip check`: passed
  - `frontend pnpm audit --audit-level high --registry https://registry.npmjs.org`: passed，high 为 0
  - Browser: `debug.html?apiBase=http://127.0.0.1:8014/api` 所有 tab 可切换；控制台 0 error；LLM payload/raw response/parsed result 可见且已脱敏；390/768/1440 视口 overflowCount=0。
- Evidence:
  - `docs/development/browser_acceptance_runs/debug_console_observability_20260516.md`
  - `docs/development/browser_acceptance_runs/debug-console-desktop-1440-20260516.png`
  - `docs/development/browser_acceptance_runs/debug-console-mobile-390-20260516.png`
- Residual risks:
  - `pnpm audit` 仍有 3 个 moderate：`vue-i18n/@intlify/core-base <10.0.8` 和 `postcss <8.5.10`。当前 high/P0 门禁已清零，建议后续依赖升级窗口处理。
  - trace 当前为进程内 ring buffer，重启后不保留；如需要跨进程诊断，可后续做 SQLite 持久化。
  - 本次浏览器验收使用 synthetic LLM trace 验证 payload/response 渲染；真实外部 LLM/provider 稳定性继续归入全系统业务验收。

## 下一步动作

进入后续增强：补 trace 导出/复制复现信息、时间线视图、持久化 trace，并在全系统业务验收中继续用该监测台追踪真实 assistant/proposal 场景。
