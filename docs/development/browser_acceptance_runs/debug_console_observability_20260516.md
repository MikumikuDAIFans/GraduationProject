# debug.html 监测台浏览器级验收报告 - 2026-05-16

## 环境

- Backend: `http://127.0.0.1:8014`
- Frontend: `http://127.0.0.1:8890`
- Debug URL: `http://127.0.0.1:8890/debug.html?apiBase=http://127.0.0.1:8014/api`
- SQLite: `backend/data/debug_observability_20260516.db`
- Browser: Playwright MCP
- 时间: `2026-05-16 01:37-01:49 +08:00`

## 修复闭环

| 项 | 初始表现 | 修复 | 复测结果 |
|---|---|---|---|
| database summary 干净库 500 | `GET /api/debug/database/summary` 在空 schema 库上报 `no such table: events` | `init_db()` 主动加载模型；database summary 对缺表降级为 `status=degraded` 而不是 500 | passed |
| Redis 不可用导致慢请求噪音 | `/api/debug/cache-stats` 在无 Redis 时约 2700ms | 增加 0.2s connect/socket timeout 并关闭连接 | passed，实测约 188ms |
| 无真实 LLM key 时无法验收 payload/response 渲染 | 只能等待真实助手触发 LLM | 增加受 debug gating 保护的 `POST /api/debug/llm/traces/sample` 和页面 `Add sample trace` | passed |
| usage token 计数被误脱敏 | `prompt_tokens` / `completion_tokens` 显示 `[REDACTED]` | redaction 对安全 token count 字段放行，仍脱敏 `access_token` / `Authorization` / `api_key` | passed |
| 前端依赖 high 漏洞 | `pnpm audit --audit-level high` 报 25 high | 升级 `axios`、`vite`，用 `pnpm.overrides` 约束 `tar`、`glob`、`minimatch`、`@xmldom/xmldom`、`lodash` | passed，high 为 0 |

## 浏览器实测结果

| 用例 | 操作 | 证据 | 结果 |
|---|---|---|---|
| 页面启动 | 打开 debug URL，等待自动刷新 | 顶栏显示 `Connected`；Overview 显示 error rate、LLM success rate、DB pool、WebSocket | passed |
| 控制台错误 | 干净标签页加载后读取 console | `Total messages: 0 (Errors: 0, Warnings: 0)` | passed |
| 标签页切换 | 依次点击 Overview / Requests / Assistant Trace / LLM Traces / Proposals / WebSocket / Database / Cache & External / Acceptance Runs / Logs | Playwright 断言每个 tab 都进入 active 状态 | passed |
| LLM trace 展开 | 打开 LLM Traces，展开 sample trace | 可见 request payload、raw response、parsed result / error | passed |
| 脱敏 | 检查 sample trace 文本 | `Authorization` 和 `api_key` 显示 `[REDACTED]`；`prompt_tokens=28`、`completion_tokens=8` 保留 | passed |
| 响应式 | 1440 / 768 / 390 视口检查 button、input、metric、card 溢出 | `overflowCount=0`，`Connected` 保持 | passed |
| 截图证据 | 保存桌面和移动端截图 | `debug-console-desktop-1440-20260516.png`、`debug-console-mobile-390-20260516.png` | passed |

## 自动化验证

- `cd backend && .\.venv312\Scripts\python.exe -m pytest -q`: `497 passed, 3 warnings`
- `cd frontend && npm run test`: `2 files / 3 tests passed`
- `cd frontend && npm run build`: passed, Vite `6.4.2`
- `cd backend && .\.venv312\Scripts\python.exe -m pip check`: `No broken requirements found.`
- `cd frontend && pnpm audit --audit-level high --registry https://registry.npmjs.org`: passed, high 为 0
- `git diff --check`: passed，仅 CRLF 工作区提示

## 残余风险

- `pnpm audit --registry https://registry.npmjs.org` 仍有 3 个 moderate：`vue-i18n/@intlify/core-base <10.0.8` 和 `postcss <8.5.10`。当前 high 门禁已清零；moderate 应纳入后续依赖升级窗口。
- `debug_observability` 为进程内 ring buffer，进程重启后 trace 不保留；符合当前任务书初版决策，后续可升级 SQLite 持久化。
- 本次 debug 页面验收使用 synthetic LLM trace 验证 payload/response 渲染和脱敏；真实 provider 调用链路已由后端单测覆盖，真实外部服务稳定性仍需在全业务验收中继续验证。
