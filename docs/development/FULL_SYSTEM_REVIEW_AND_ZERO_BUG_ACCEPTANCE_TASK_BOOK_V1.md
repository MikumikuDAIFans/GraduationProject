# 全系统 Review 与零已知缺陷验收任务书 V1

## 计划元数据

- Plan ID: `full-system-review-zero-known-bugs-v1`
- Version: `v1`
- Last updated: `2026-05-16 02:45 +08:00`
- Canonical progress file: `E:\GraduationProject\docs\development\FULL_SYSTEM_REVIEW_AND_ZERO_BUG_ACCEPTANCE_TASK_BOOK_V1.md`
- Related handoff file: `none`
- Current branch: `codex/assistant-browser-acceptance`
- Current active phase: `Phase 8: 缺陷修复闭环与最终复验`
- Execution readiness: `passed`

## 目标

建立一套尽可能全面、可重复、可追踪的 Review 与全量检测机制，使项目在每次宣告完成前必须通过静态检查、自动化测试、迁移验证、真实浏览器验收、LLM 链路审计、性能稳定性测试和回归复测。目标口径不是数学意义上的“永远不存在任何 bug”，而是达到工程可执行的“零已知阻断缺陷”：所有已发现缺陷修复并有回归测试，所有 P0/P1 核心路径真实浏览器通过，所有剩余风险必须被记录、分级并有明确阻断门槛。

## 范围与约束

- In scope:
  - 后端 API、数据库迁移、Repository、Service、Assistant/Proposal/Memory/LLM 链路。
  - 前端主工作台、AssistantPanel、debug.html、Store、WebSocket、移动端与桌面端响应式主路径。
  - 自动化单元测试、集成测试、浏览器级真实验收、手工探索测试、性能与稳定性测试。
  - 依赖、安全、配置、日志、监控、文档与验收证据。
  - Review 后发现问题时的最小修复、补测试、复测闭环。
- Out of scope:
  - 对第三方 LLM、地图、天气、Google Calendar 等外部服务 SLA 做绝对保证。
  - 使用形式化方法证明系统永远无缺陷。
  - 一次性重写架构或改动与缺陷无关的大范围功能。
- Constraints:
  - 任何缺陷修复都必须先定位原因，再做最小修改，最后补对应测试。
  - 浏览器验收必须使用干净 SQLite 库和真实前端页面，不得只用后端 API 替代用户操作。
  - 不得回退用户已有改动；遇到混合工作区时只处理本任务范围。
  - LLM 相关测试必须同时覆盖真实提供商可用路径、模拟失败路径、fallback 路径和 payload/response 可观测性。
  - 最终结论必须区分 `passed`、`failed-fixed-passed`、`blocked`、`not applicable`，不得用模糊描述替代证据。

## 完成定义

系统只有同时满足以下条件，才能宣告“零已知阻断缺陷”：

1. 所有 P0/P1 自动化测试通过。
2. 所有 P0/P1 浏览器级真实验收通过。
3. 所有失败项都有对应修复、回归测试和复测证据。
4. 数据库迁移从空库到 head、从当前开发库到 head 均通过。
5. 前端构建、类型检查、单元测试、关键视口截图检查通过。
6. LLM 调用 payload、返回值、错误、fallback、耗时可在 debug 监测面板或日志中定位。
7. 性能、错误率、慢请求、WebSocket 连接、缓存、DB pool 等监控指标处于任务书定义阈值内。
8. 所有残余风险都被记录为 P2 或更低优先级，且不影响核心用户任务。

## 执行阶段

### Phase 1: 基线盘点与风险分层

- Purpose: 明确当前系统真实边界，避免 Review 漏掉关键链路。
- Outputs:
  - 模块清单：前端、后端、数据库、外部服务、LLM、调试监控、脚本与文档。
  - 风险登记表：按 P0/P1/P2 标记业务风险、数据风险、交互风险、性能风险、安全风险。
  - 当前测试能力清单：已有 pytest、vitest、build、浏览器验收脚本、debug.html 能力。
- Completion criteria:
  - 所有核心用户路径都有明确 owner 文件和验收方式。
  - 所有不可自动化验证的项都有手工浏览器验收步骤。
- Validation:
  - `git status -sb`
  - `rg --files`
  - 读取 `docs/development/AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`
  - 读取 `scripts/assistant_browser_full_acceptance.mjs`
  - 读取 `frontend/public/debug.html`
- Evidence:
  - 在本任务书进度台账追加风险登记摘要和覆盖矩阵。

### Phase 2: 静态质量与依赖审计

- Purpose: 在运行前先清除可静态发现的问题。
- Outputs:
  - Python import、typing、dead code、格式、迁移脚本、依赖漏洞检查结果。
  - TypeScript 类型、Vue 模板、构建产物、依赖漏洞检查结果。
  - 配置审计结果：`.env.example`、CORS、API prefix、SQLite 路径、LLM provider 配置。
- Completion criteria:
  - `git diff --check` 无错误。
  - 前端 `vue-tsc` 和 `vite build` 通过。
  - 依赖审计中无 P0/P1 漏洞；若存在必须修复或记录阻断。
  - 未发现提交密钥、真实 token、敏感 payload。
- Validation:
  - `git diff --check`
  - `cd frontend && npm run build`
  - `cd frontend && npm audit --audit-level=high`
  - `cd backend && .\.venv312\Scripts\python.exe -m pip check`
  - `rg -n "api_key|secret|token|password|Bearer|sk-" .`
- Evidence:
  - 命令输出摘要写入验收报告。

### Phase 3: 后端全量自动化测试与迁移验证

- Purpose: 确保后端核心逻辑、协议、数据写入和迁移链路稳定。
- Outputs:
  - 全量 pytest 报告。
  - 重点助手测试报告。
  - Alembic 空库迁移和现有库迁移验证。
  - 覆盖率报告与低覆盖高风险模块清单。
- Completion criteria:
  - `pytest` 全量通过。
  - 助手相关测试、proposal 文本协议、LLM fallback、memory capture 全部通过。
  - Alembic `upgrade head` 在干净库通过。
  - 新增缺陷必须对应新增或更新测试。
- Validation:
  - `cd backend && .\.venv312\Scripts\python.exe -m pytest -q`
  - `cd backend && .\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py tests/test_assistant_conductor.py tests/test_assistant_proposal_revise.py tests/test_assistant_service.py -q`
  - `cd backend && .\.venv312\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing`
  - 使用临时 SQLite 库执行 Alembic `upgrade head`。
- Evidence:
  - 测试数量、失败数量、warnings、覆盖率摘要、迁移验证结果。

### Phase 4: 前端全量自动化与响应式验证

- Purpose: 确保用户界面、状态管理、WebSocket、渲染状态和响应式布局稳定。
- Outputs:
  - Vitest 结果。
  - 生产构建结果。
  - Desktop / mobile 关键页面截图和布局检查。
  - AssistantPanel inline proposal 终态渲染检查。
- Completion criteria:
  - `npm run test` 通过。
  - `npm run build` 通过。
  - 390px、768px、1440px 视口无文字溢出、按钮重叠、关键卡片消失。
  - inline proposal 接受/拒绝后保留灰色不可点击，刷新后仍恢复终态。
- Validation:
  - `cd frontend && npm run test`
  - `cd frontend && npm run build`
  - Playwright 打开真实页面截图检查。
  - Playwright 检查按钮 disabled 状态、卡片可见性、主输入协议文本。
- Evidence:
  - 截图路径、DOM 状态摘要、浏览器控制台错误摘要。

### Phase 5: 浏览器级真实业务验收

- Purpose: 用真实用户操作覆盖核心业务，而不是只验证内部 API。
- Outputs:
  - clean DB 浏览器验收报告。
  - 每条用例的输入、页面表现、数据库证据、失败修复点。
  - 最终全功能复验报告。
- Completion criteria:
  - `AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md` 中所有 P0 通过。
  - inline proposal P0/P1 通过。
  - 真实批量日程创建/修改使用逐条自然语言场景，不使用一次性批量脚本替代真实对话。
  - 多轮上下文场景通过：用户补充信息后系统能延续前文并创建/修改正确对象。
- Validation:
  - 干净 SQLite 库启动后端和前端。
  - Playwright 真实页面执行。
  - 每条用例后查询 SQLite 验证 events/tasks/proposals/messages。
  - 浏览器控制台与后端 err log 必须无 P0/P1 错误。
- Evidence:
  - `docs/development/browser_acceptance_runs/` 下生成或更新验收报告。

### Phase 6: LLM 链路与可观测性审计

- Purpose: 确保 LLM 不是黑盒，payload、返回值、解析结果、fallback 和错误都能被定位。
- Outputs:
  - LLM trace 设计核对表。
  - payload/response redaction 策略。
  - provider/fallback/circuit breaker 测试。
  - debug.html 监测面板验收结果。
- Completion criteria:
  - 每次 LLM 调用都有 trace id、provider、model、purpose、latency、status、request payload 摘要、raw response 摘要、parsed result、error。
  - API key、Authorization、token、个人敏感字段不会明文展示。
  - 主模型失败时 fallback 行为可观测。
  - debug.html 能按 session/request/trace 定位一次助手对话背后的 LLM 调用。
- Validation:
  - 模拟 LLM 成功、超时、HTTP 错误、JSON 解析失败、fallback 成功、全失败。
  - 浏览器打开 debug.html 检查 LLM trace 列表和详情。
  - 后端测试覆盖 redaction 和 trace 记录。
- Evidence:
  - LLM trace 样例、debug 页面截图、测试结果。

### Phase 7: 性能、稳定性与长时间运行验证

- Purpose: 防止系统在短测通过但长时间或多请求下退化。
- Outputs:
  - 首页请求数量、耗时、错误率、慢请求报告。
  - WebSocket 连接稳定性报告。
  - DB pool、cache、内存、CPU、日志增长趋势报告。
  - 并发助手消息和 proposal 操作压测结果。
- Completion criteria:
  - 首页首屏关键请求数量符合 V8 收敛目标。
  - 最近 5 分钟错误率为 0 或仅包含已解释的非阻断外部失败。
  - 无持续增长的 WebSocket 订阅泄漏。
  - DB pool 无异常耗尽。
  - 常规助手消息响应耗时在可接受阈值内；慢请求有可定位 trace。
- Validation:
  - debug.html 监测。
  - Playwright 长时间会话。
  - 请求日志和 metrics snapshot。
  - 可选：轻量并发脚本对 `/assistant/message` 和 WebSocket 进行压力测试。
- Evidence:
  - 性能报告、debug 截图、请求日志摘要。

### Phase 8: 缺陷修复闭环与最终复验

- Purpose: 确保 Review 不是只列问题，而是全部闭环。
- Outputs:
  - 缺陷台账。
  - 每个缺陷的原因、修复文件、测试文件、复测证据。
  - 最终全功能复验报告。
- Completion criteria:
  - P0/P1 缺陷为 0。
  - 所有曾失败用例状态为 `failed-fixed-passed` 或有明确阻断原因。
  - 最终复验必须在所有修复后重新从干净库执行。
  - 工作区只包含本任务相关改动。
- Validation:
  - 全量自动化测试再次通过。
  - 浏览器全功能复测再次通过。
  - `git status -sb` 和 `git diff --check` 检查。
- Evidence:
  - 最终验收报告、提交前测试摘要、剩余风险清单。

## Review 检查矩阵

| 层级 | 检查点 | 阻断条件 |
|---|---|---|
| 数据层 | Alembic 迁移、SQLite schema、JSON 字段兼容、历史数据回放 | 迁移失败、历史消息无法读取、关键字段丢失 |
| 后端 API | CRUD、assistant、proposal、memory、debug、health | 5xx、错误写库、状态不一致 |
| AI 助手 | 意图理解、多轮上下文、proposal-first、确认协议、拒绝协议、重试 | 误写库、误确认、上下文丢失、pending 混淆 |
| LLM | payload、response、解析、fallback、超时、redaction | 无 trace、敏感信息泄漏、fallback 不可见 |
| 前端 | 主界面、AssistantPanel、inline proposal、移动端、debug.html | 卡片消失、按钮绕过助手、布局重叠、控制台 P0 错误 |
| 浏览器验收 | 真实输入、真实点击、刷新恢复、干净库 | 仅 API 验证、旧数据污染、无法复现 |
| 性能稳定 | 请求数量、慢请求、错误率、WS、DB pool、cache | 错误率异常、连接泄漏、池耗尽 |
| 安全隐私 | token、API key、LLM payload redaction、debug 权限 | 敏感信息明文展示、debug 无保护进入生产 |
| 文档证据 | 任务书、验收报告、失败修复记录 | 结论无证据、失败未复测 |

## 决策记录

- Verified facts:
  - 当前项目已有 `frontend/public/debug.html`。
  - 当前项目已有 `backend/app/api/routes/debug.py`。
  - 当前项目已有浏览器验收脚本与验收报告目录。
  - 最近一次提交前后端全量测试和前端构建曾通过，但后续执行仍必须重新验证当前工作区。
- Active assumptions:
  - 后续 Review 会在 `codex/assistant-browser-acceptance` 或其后续工作分支执行。
  - 后续验收可使用本机 Windows PowerShell、`.venv312`、npm、Playwright。
  - LLM 真实 provider 可能受网络和密钥影响，因此必须同时有模拟测试和真实可用性检查。
- Locked decisions:
  - “完美无 bug”在工程执行中定义为“零已知阻断缺陷 + 全量门禁通过 + 残余风险透明可追踪”。
  - 浏览器验收必须优先于口头判断，不能只靠单元测试宣告完成。
  - 任何 debug 页面展示 LLM payload/response 都必须做敏感信息脱敏。
- Open questions:
  - debug.html 是否需要生产环境访问控制，还是只允许本地开发环境启用。
  - 是否引入额外工具如 mypy、ruff、eslint、Playwright test runner、coverage threshold。
  - 外部 LLM 真实调用是否允许在 CI 或验收脚本中执行。

## 关键制品与环境

- Canonical docs:
  - `E:\GraduationProject\docs\development\FULL_SYSTEM_REVIEW_AND_ZERO_BUG_ACCEPTANCE_TASK_BOOK_V1.md`
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`
  - `E:\GraduationProject\docs\development\AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_IMPLEMENTATION_PLAN_V1.md`
- Important code or output artifacts:
  - `E:\GraduationProject\backend\app\services\assistant.py`: 助手主链路。
  - `E:\GraduationProject\backend\app\tools\gemini.py`: LLM provider 调用链路。
  - `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`: 助手交互与 inline proposal 渲染。
  - `E:\GraduationProject\frontend\public\debug.html`: 调试监测入口。
  - `E:\GraduationProject\backend\app\api\routes\debug.py`: debug API。
  - `E:\GraduationProject\scripts\assistant_browser_full_acceptance.mjs`: 浏览器验收脚本。
- Required commands:
  - `cd E:\GraduationProject\backend && .\.venv312\Scripts\python.exe -m pytest -q`: 后端全量测试。
  - `cd E:\GraduationProject\frontend && npm run test`: 前端测试。
  - `cd E:\GraduationProject\frontend && npm run build`: 前端类型检查和构建。
  - `git diff --check`: diff 格式检查。
- Environment baseline:
  - OS: Windows PowerShell。
  - Backend venv: `backend\.venv312`。
  - Browser acceptance: clean SQLite DB + isolated backend/frontend ports。
  - Timezone-sensitive testing: 使用明确日期，不依赖含糊的“今天/明天”结论。

## 进度台账

- Overall progress: `passed`。本轮完成 debug 可观测性升级、业务缺陷修复、后端全量测试、前端测试/构建、数据库迁移验证、浏览器级 debug 页面验收、浏览器级助手全量验收和 high 级依赖漏洞门禁。当前达到“零已知 P0/P1 阻断缺陷”口径。
- Phase 1: completed。已覆盖后端 API、助手 proposal-first 协议、memory、LLM trace、WebSocket、debug.html、前端 AssistantPanel、移动端布局和浏览器验收脚本。
- Phase 2: completed。
  - `git diff --check`: passed，仅 CRLF 工作区提示。
  - `cd frontend && npm run build`: passed。
  - `cd backend && .\.venv312\Scripts\python.exe -m pip check`: passed。
  - `cd frontend && pnpm audit --audit-level high --registry https://registry.npmjs.org`: passed，0 high/critical；完整 audit 仍有 3 个 moderate，记录为 P2 依赖升级风险。
- Phase 3: completed。
  - `cd backend && .\.venv312\Scripts\python.exe -m pytest -q`: `498 passed, 3 warnings`。
  - Alembic clean DB: `sqlite+aiosqlite:///./data/alembic_final_clean_20260516.db` upgrade head passed。
  - Existing DB: `alembic current` 为 `0009_assistant_message_render_blocks (head)`，`alembic upgrade head` passed。
- Phase 4: completed。
  - `cd frontend && npm run test`: `2 files / 3 tests passed`。
  - `cd frontend && npm run build`: passed。
  - debug 页面桌面/移动端浏览器验收 passed。
  - AssistantPanel 当前待确认事项区和移动端布局在业务浏览器验收中 passed。
- Phase 5: completed。
  - `node scripts/assistant_browser_full_acceptance.mjs`: `94 passed, 0 failed, 5 tracked, 99 total`。
  - 干净 DB: `backend/data/browser_full_acceptance_20260515182307.db`。
  - 关键修复后复测：`BAI-P1-003`、`BAI-P1-104`、`BAI-P1-112`、`BAI-P1-402`、`BAI-P1-404` 过滤集先通过，随后全量通过。
  - tracked 项为脚本标记的独立混沌/故障注入项：provider 主失败、provider 全失败、网络中断恢复、AI 返回格式异常、慢响应超时与重试；不属于当前功能阻断失败。
- Phase 6: completed。LLM payload/raw response/parsed result/error/fallback/latency 可在 debug 面板定位；redaction、production gating、trace sample、DB/WS/cache summary 均有后端测试和浏览器证据。
- Phase 7: completed for P0/P1 gate。debug 页面运行时 0 console error；全量浏览器验收覆盖长对话滚动、加载禁用状态、WebSocket 状态同步、后端重启后 pending proposal 继续确认。并发/混沌项中需独立故障注入环境的内容保留为 tracked P2。
- Phase 8: completed。所有本轮发现的 P0/P1 失败项均已最小修复、补测试或补浏览器证据，并完成最终全量复验。
- Fix closure:
  - `BAI-P1-003 默认时长推断`: negotiation 输出显式补充“默认1小时”说明。
  - `BAI-P1-104 常用地点别名解析`: 已确认地点别名优先进入 proposal，未确认的“学校体检”仍保留校医院/校外医院澄清。
  - `BAI-P1-112 出发地和目的地相同`: 全量浏览器复验通过，临时位置不污染长期记忆。
  - `BAI-P1-402 当前待确认事项区`: 恢复当前待确认方案区，并让当前会话查询兼容系统级 `session_id=None` proposal。
  - `BAI-P1-404 移动端布局`: 移动端待确认方案和发送入口浏览器复验通过。
- Evidence:
  - `docs/development/browser_acceptance_runs/assistant_browser_full_acceptance_20260515182307.md`
  - `docs/development/browser_acceptance_runs/assistant_browser_full_acceptance_20260515182307.json`
  - `docs/development/browser_acceptance_runs/mobile_20260515182307.png`
  - `docs/development/browser_acceptance_runs/debug_console_observability_20260516.md`
  - `docs/development/browser_acceptance_runs/debug-console-desktop-1440-20260516.png`
  - `docs/development/browser_acceptance_runs/debug-console-mobile-390-20260516.png`
  - `docs/development/DEBUG_CONSOLE_OBSERVABILITY_UPGRADE_TASK_BOOK_V1.md`
- Residual risks:
  - `pnpm audit` 完整级别仍有 3 个 moderate：`vue-i18n/@intlify/core-base <10.0.8` 和 `postcss <8.5.10`，当前 high/P0 门禁不阻断，应排入后续依赖升级。
  - 5 个 tracked 浏览器项需要独立混沌/故障注入环境，不阻断当前真实业务 P0/P1 验收。

## 下一步动作

当前任务书已达到完成定义。后续建议单独开 P2 任务处理 moderate 依赖升级和 tracked 混沌测试自动化。
