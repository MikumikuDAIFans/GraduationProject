## 计划元数据
- Plan ID: ma-ipaas-practical-build-plan
- Version: v1
- Last updated: 2026-03-25 01:35 Asia/Shanghai
- Canonical progress file: /E:/GraduationProject/plan_doc/TASK_BOOK.md
- Related handoff file: none
- Current branch: unknown
- Current active phase: Phase 2 - 后端骨架与数据层落地

## 目标
将毕业设计收敛为一套可逐步执行的个人事务助手实现方案，并基于已克隆的开源参考仓库建立稳定的工程基线。最终产出应支持日程规划、日程建议、冲突处理、主动提醒与建议推送，并保留未来以插件方式接入语音输入输出的扩展能力。

## 范围与约束
- In scope:
  - 基于参考仓库整理并定稿系统详细技术方案
  - 设计可落地的前端、后端、数据库、提醒引擎和插件扩展边界
  - 建立唯一的长期任务书，作为后续开发和交接的执行基线
  - 后续按阶段推进代码骨架、核心能力、提醒机制、UI 和答辩材料
- Out of scope:
  - 当前轮次不直接实现实时语音输入和模型语音输出
  - 当前轮次不做复杂多 Agent 平台化实现
  - 当前轮次不做完整生产部署和大规模性能优化
- Constraints:
  - 优先复用现有开源实现，不重复造轮子
  - 核心产品方向必须围绕个人事务、时间安排、主动提醒
  - 调度逻辑需采用规则优先、AI 辅助的稳妥方案
  - 目录下存在多份历史设计文档，后续应以本任务书和最新技术方案为准
  - 当前工作区不是 git 仓库，分支信息不可用

## 执行阶段
### Phase 1: 技术方案定稿与代码基线整理
- Purpose: 将现有分散文档和参考仓库信息统一成一套可执行的正式技术方案，并明确后续复用边界
- Outputs:
  - 详细技术方案文档
  - 长期任务书
  - 参考仓库复用矩阵
- Completion criteria:
  - 技术方案覆盖前端、后端、数据库、提醒引擎、接口、插件预留
  - 任务书确定后续阶段、验证方式和唯一下一步动作
  - 明确哪些参考仓库可直接改造、哪些只借思路
- Validation:
  - 文档文件已写入项目目录
  - 技术方案能支撑后续直接开始搭项目骨架
- Evidence:
  - `/E:/GraduationProject/plan_doc/IMPLEMENTABLE_TECHNICAL_SPEC_V2.md`
  - `/E:/GraduationProject/plan_doc/TASK_BOOK.md`

### Phase 2: 后端骨架与数据层落地
- Purpose: 建立后端工程基础，完成核心数据模型、Repository、基础 API 和任务队列接入
- Outputs:
  - FastAPI 项目骨架
  - SQLite 数据模型与迁移
  - 事件、任务、提醒基础 CRUD
  - Celery 与 Redis 接入
- Completion criteria:
  - 本地可运行 API 服务
  - 数据表可迁移
  - 事件、任务、提醒接口可用
- Validation:
  - 执行迁移成功
  - 关键 API 自测通过
  - 基础单元测试可运行
- Evidence:
  - 后端目录结构
  - migration 文件
  - API 路由与测试结果

### Phase 3: Assistant 工作流与工具层接入
- Purpose: 建立自然语言处理主工作流，并接入 Calendar、Task、Map、Notification 等工具
- Outputs:
  - Assistant 工作流节点与状态定义
  - 工具层模块
  - 助手消息接口
  - 基础冲突检测与建议逻辑
- Completion criteria:
  - 用户可通过自然语言创建、查询、修改日程
  - 系统可返回基础建议与冲突说明
- Validation:
  - 端到端演示至少覆盖 3 个典型场景
  - 工具调用链可追踪
- Evidence:
  - workflow 代码
  - tools 代码
  - 演示请求与响应样例

### Phase 4: 前端工作台与实时提醒
- Purpose: 建立日历 + 助手 + 提醒三区工作台，并完成主动提醒的基础实时展示
- Outputs:
  - 主工作台页面
  - 事件日历视图
  - 助手对话区
  - 提醒与建议区
  - WebSocket 推送
- Completion criteria:
  - 用户可在前端查看日程、收提醒、接收建议
  - 助手操作可以联动刷新日历
- Validation:
  - 本地联调通过
  - 至少覆盖创建事件、提醒推送、冲突高亮三个演示动作
- Evidence:
  - 前端页面
  - WebSocket 消息样例
  - 页面截图

### Phase 5: 调度增强、插件预留与答辩交付
- Purpose: 强化主动提醒、空档建议、出发提醒，并完善文档、图表、演示材料
- Outputs:
  - 提醒引擎增强
  - 插件接口预留
  - 系统架构图、时序图、数据库图
  - 答辩演示脚本和测试记录
- Completion criteria:
  - 系统能稳定演示主动提醒和合理安排时间
  - 论文与答辩所需技术材料齐备
- Validation:
  - 关键场景演示无阻塞
  - 图表与文档能与实现保持一致
- Evidence:
  - 图表文件
  - 演示脚本
  - 测试记录

## 决策记录
- Verified facts:
  - 已在 `/E:/GraduationProject/reference` 克隆 8 个参考仓库
  - 已产出简化方案、重构方案和参考表文档
  - 当前用户明确要求优先参考开源仓库实现方式，不重复造轮子
  - 当前用户要求系统必须覆盖日程规划、日程建议、冲突处理和主动提醒
  - 当前用户希望保留未来的语音输入输出插件接口，但现阶段不实现
  - 当前工作区不是 git 仓库，因此分支信息不可用
- Active assumptions:
  - 前端将以 `calendar-ai` 的交互思路为主，做 Vue 化适配
  - 地图与天气接口初期可先用模拟或简化实现，再逐步接正式 API
- Locked decisions:
  - 初版不以多 Agent 为核心卖点，先做单工作流 + 工具层 + 提醒引擎
  - 规则负责时间和冲突逻辑，AI 负责理解与解释
  - 主动提醒能力必须作为一等能力进入数据表、后台任务和前端界面
  - 后端主框架正式由 Django 切换为 `FastAPI`
  - 前端正式采用 `Vue 3 + TypeScript + Vite + TailwindCSS + FullCalendar + Pinia`
  - 移动端封装采用 `Capacitor`，桌面端封装采用 `Tauri 2`
  - 数据库正式改为 `SQLite`，保留 `Redis` 作为队列与缓存
  - 模型服务默认采用 `Google Gemini`
  - Gemini 模型固定为稳定版本 `models/gemini-2.5-flash`
  - 天气服务默认采用 `和风天气`
  - 地图服务默认采用 `高德地图开放平台`
  - Google Calendar 同步正式定为“本地 SQLite 为主、Google Calendar 为镜像”的单向主从方案
  - Google Calendar 外部事件导入正式定为“手动同步优先”，暂不做后台定时自动导入
  - Redis 与 Celery 在本地开发环境中统一采用 Docker 化运行
  - 项目所有后端组件正式约定运行在 Docker 容器中
  - 项目正式启用 `Google Calendar` 同步
  - 项目正式启用站内提醒与桌面通知双通道
  - 以本任务书作为后续持续维护的唯一主进度文件
- Open questions:
  - none

## 关键制品与环境
- Canonical docs:
  - `/E:/GraduationProject/plan_doc/IMPLEMENTABLE_TECHNICAL_SPEC_V2.md`
  - `/E:/GraduationProject/plan_doc/TASK_BOOK.md`
  - `/E:/GraduationProject/MA-IPAAS_Doc/PRACTICAL_SIMPLE_ASSISTANT_PLAN.md`
  - `/E:/GraduationProject/MA-IPAAS_Doc/OPEN_SOURCE_REFERENCE_TABLE.md`
- Important code or output artifacts:
  - `/E:/GraduationProject/reference/calendar-ai`: 前端页面结构、日历接口和助手交互参考
  - `/E:/GraduationProject/reference/calendar-mcp`: Calendar Tool 设计参考
  - `/E:/GraduationProject/reference/todo-work-agent`: 工作流、Repository、工具层和测试参考
  - `/E:/GraduationProject/reference/spec-to-agents`: 模块组织、workflow 分层参考
- Required commands:
  - `Get-ChildItem "E:\GraduationProject\reference"`: 查看本地参考仓库
  - `Get-Content -Raw "E:\GraduationProject\plan_doc\IMPLEMENTABLE_TECHNICAL_SPEC_V2.md"`: 读取最新技术方案
  - `Get-Content -Raw "E:\GraduationProject\plan_doc\TASK_BOOK.md"`: 读取主任务书
- Environment baseline:
  - 工作目录为 `E:\GraduationProject`
  - 当前主要产物为文档和参考仓库，尚未进入正式代码搭建阶段
  - 后续默认技术基线为 FastAPI + Pydantic + SQLAlchemy + Alembic + Celery + Redis + SQLite + Vue 3

## 进度台账
- Overall progress: 已完成参考仓库收集、技术方案定稿、关键技术选型、外部依赖人工准备清单以及根目录环境文件生成
- Phase 1: done
- Phase 2: in progress
- Phase 3: pending
- Phase 4: pending
- Phase 5: pending
- Validation status: 已完成 Gemini、高德地图、和风天气、Google OAuth 配置的基础可用性测试，并生成 API 测试记录；Redis/Celery 尚未开始运行验证，代码骨架尚未搭建
- Residual risks:
  - Google Calendar 真正读写仍需后续完成用户授权流程
  - Redis 尚未安装，队列与提醒任务还未进入运行验证
  - 若直接复制部分开源代码，仍需逐项确认许可证适配性

## 下一步动作
开始搭建后端代码骨架，并先安装 Redis，随后落地 SQLite 数据模型、FastAPI 项目结构和基础事件/任务/提醒表。
## 当前下一步（更新于 2026-03-28，第二次）
已完成：
- 跨面板联动（点击摘要卡聚焦相关任务/事件/助手线程，各面板高亮+滚动）
- AssistantPanel inbox item 新增 "View Task" 按钮
- CalendarPanel focus_block 新增 "Ask Assistant" 快捷续接按钮
- InsightsPanel suggestion 新增 "Use This Slot" 带任务名的智能提示
- SummaryPanel 动作按钮触发后自动滚动到助手面板
- 助手消息区支持 Markdown 渲染（marked.js + scoped CSS）
- 后端新增 2 个摘要卡联动测试（59 passed）
- 前端 production build 通过

下一步可选方向（按优先级）：
1. 从日历面板/InsightsPanel 快速创建任务（quick-create modal/inline form），减少对助手对话的依赖。
2. 强化 Phase 5 答辩材料：系统架构图、时序图、数据库 ER 图、演示脚本。
3. 进一步强化助手中文规划回复的结构化程度（Gemini prompt 工程）。
## Incremental Update - 2026-03-25 20:15 Asia/Shanghai
- Phase 2 implementation started and is now materially unblocked.
- Completed in this round:
  - Bootstrapped `/E:/GraduationProject/backend` with FastAPI app entry, config loading, API router assembly, and package layout.
  - Implemented SQLite data layer with SQLAlchemy 2 models for `user_profile`, `events`, `tasks`, `reminders`, `assistant_sessions`, `assistant_messages`, and `schedule_change_logs`.
  - Added async repository layer for events/tasks/reminders and wired real service dependencies into FastAPI routes.
  - Added baseline API endpoints for `health`, `events`, `tasks`, and `reminders`.
  - Added Alembic configuration and initial migration `0001_initial_schema`.
  - Added Docker infrastructure files: `/E:/GraduationProject/docker-compose.yml`, `/E:/GraduationProject/backend/Dockerfile`, Celery app, reminder scan job, and Redis wait script.
  - Brought up Redis successfully with Docker and verified `redis-cli ping -> PONG`.
- Validation completed:
  - `E:/GraduationProject/backend/.venv312/Scripts/python.exe -m pytest -q -c pytest.ini tests` -> `3 passed`
  - `E:/GraduationProject/backend/.venv312/Scripts/python.exe -m alembic -c alembic.ini upgrade head` -> success
  - Real API smoke test passed for create/list/update flow across `events`, `tasks`, and `reminders`
- Evidence:
  - `/E:/GraduationProject/backend/app/main.py`
  - `/E:/GraduationProject/backend/app/models.py`
  - `/E:/GraduationProject/backend/app/api/`
  - `/E:/GraduationProject/backend/app/db/`
  - `/E:/GraduationProject/backend/app/repositories/`
  - `/E:/GraduationProject/backend/app/core/celery_app.py`
  - `/E:/GraduationProject/backend/app/jobs/reminders.py`
  - `/E:/GraduationProject/backend/alembic/versions/0001_initial_schema.py`
  - `/E:/GraduationProject/docker-compose.yml`
- Current blocker:
  - Full Docker build for `api/celery_worker/celery_beat` is blocked by local Docker registry certificate/network issues when pulling `python:3.11-slim` (`auth.docker.io` certificate mismatch / TLS handshake failure). This is an environment/network blocker, not an application code blocker.
- Updated next action:
  - Resolve Docker daemon registry certificate issue, then run `docker compose up -d --build api celery_worker celery_beat`
  - After containers are healthy, continue Phase 2 by adding initial assistant/session APIs and reminder scheduling refinement
- Follow-up update - 2026-03-25 22:35 Asia/Shanghai:
  - Dockerized backend stack is now running successfully: `redis`, `api`, `celery_worker`, and `celery_beat`.
  - Added minimal assistant endpoints: `POST /api/assistant/message` and `GET /api/assistant/sessions/{id}`.
  - Verified container health endpoint on `http://127.0.0.1:8000/api/health`.
  - Verified assistant session/message persistence through the containerized API.
  - Temporary local workaround in use: compose currently builds from local image `vcptoolbox-app` because Docker Hub certificate/proxy configuration is broken on this machine. Switch back to `python:3.11-slim` after registry trust is repaired.
- Follow-up update - 2026-03-25 23:25 Asia/Shanghai:
  - `POST /api/assistant/message` is now wired to Gemini (`models/gemini-2.5-flash`) with real event/task/session context.
  - `GET /api/assistant/sessions/{id}` now returns persisted user and assistant messages for the same conversation.
  - Verified live container call on `http://127.0.0.1:8000/api/assistant/message` returned a real model-generated scheduling suggestion.
  - Verified session replay on `http://127.0.0.1:8000/api/assistant/sessions/4` with persisted user/assistant messages.
  - Current assistant implementation still returns text-only replies and does not yet execute schedule mutations; next step is structured intent parsing plus event/task write actions.
- Follow-up update - 2026-03-25 23:40 Asia/Shanghai:
  - Assistant now supports structured action execution for baseline `create_task` and guarded `create_event` flows.
  - Verified live task creation through `POST /api/assistant/message`, then confirmed persistence via `GET /api/tasks`.
  - Verified guarded event creation with time extraction fallback, then confirmed persistence via `GET /api/events`.
  - Assistant message records now persist executed action metadata in `tool_calls_json`.
  - Next step: refine action schema, add conflict detection before writes, and convert more assistant outputs into safe structured mutations.
- Follow-up update - 2026-03-26 00:05 Asia/Shanghai:
  - Added guarded write path before assistant-created events are persisted.
  - Assistant now checks overlapping `events` before executing `create_event`.
  - Added lightweight fallback extraction for explicit time ranges and event titles from raw user text.
  - Verified real task creation, real event creation, and conflict interception through the containerized assistant API.
  - Tests increased to `8 passed`.
- Follow-up update - 2026-03-26 00:20 Asia/Shanghai:
  - Conflict interception now returns alternative same-day candidate slots instead of only rejecting the write.
  - Verified live assistant response includes `conflict_warning` plus suggested replacement ranges.
  - Unit tests increased to `9 passed`.
  - Current next step: replace the simple same-day gap finder with stronger rule-based scheduling suggestions and start exposing these suggestions more explicitly to the frontend.
- Follow-up update - 2026-03-26 00:35 Asia/Shanghai:
  - Added formal suggestion APIs: `GET /api/suggestions/today` and `GET /api/suggestions/next`.
  - Added lightweight rule-based slot recommendation service for pending tasks based on event gaps.
  - Verified both suggestion endpoints through the running Dockerized API.
  - Test suite increased to `11 passed`.
- Follow-up update - 2026-03-26 02:55 Asia/Shanghai:
  - Reminder worker now generates `event_start` reminders for upcoming events within the next 24 hours.
  - Verified Celery task execution through the running worker and confirmed reminder records via `GET /api/reminders`.
  - Reminder job is now beyond a stub and participates in the end-to-end backend flow.
  - Test suite increased to `13 passed`.
- Follow-up update - 2026-03-26 03:05 Asia/Shanghai:
  - Added a minimal frontend workspace under `frontend/` using Vue 3 + TypeScript + Vite + TailwindCSS + FullCalendar + Pinia.
  - Frontend now renders live calendar events, reminders, suggestions, and assistant conversations from the running backend API.
  - Verified end-to-end browser interaction: sending an assistant message from the frontend created a real task and refreshed suggestion cards.
  - Test suite increased to `13 passed`, frontend production build passed, and frontend dev server rendered successfully.
- Follow-up update - 2026-03-26 03:15 Asia/Shanghai:
  - Added `/ws/notifications` live workspace stream for reminders and suggestions.
  - Frontend now subscribes to backend WebSocket updates and supports browser notification prompts.
  - Verified frontend page loads without console errors after WebSocket support was added.
  - Frontend remains a minimal workstation shell, but now includes live data refresh instead of pure request/response only.
- Follow-up update - 2026-03-26 03:35 Asia/Shanghai:
  - Added external context APIs for Amap geocoding/travel estimation and QWeather current weather lookup.
  - Frontend workspace now renders live weather and commute panels using real backend context APIs.
  - Verified real Amap and QWeather responses through the running backend and browser UI.
  - Test suite increased to `14 passed`.
- Follow-up update - 2026-03-26 07:40 Asia/Shanghai:
  - Added `profile` read/write API and frontend profile editor.
  - User profile now persists home/work locations, transport preference, and daily defaults.
  - Profile save flow now geocodes home/work names into coordinates for downstream travel/weather use.
  - Verified frontend profile panel, weather panel, and commute panel render together with persisted profile data.
  - Test suite increased to `15 passed`.
- Follow-up update - 2026-03-27 07:40 Asia/Shanghai:
  - Added persisted user profile flow end-to-end, including backend `GET/PUT /api/profile` and frontend profile editor.
  - Profile save now geocodes home/work locations into coordinates for downstream commute/weather use.
  - Frontend workspace now derives travel and weather context from persisted profile data instead of fixed defaults.
  - Test suite increased to `15 passed`.
- Follow-up update - 2026-03-27 08:05 Asia/Shanghai:
  - Event create flow now geocodes destination, estimates commute, and persists `travel_duration_minutes` plus `departure_time`.
  - Reminder worker now generates `departure` reminders in addition to `event_start` reminders when `departure_time` is available.
  - Frontend calendar area now renders departure guide cards for travel-aware events.
  - Verified real event creation with computed departure metadata and confirmed generated departure reminder via `GET /api/reminders`.
- Follow-up update - 2026-03-27 08:15 Asia/Shanghai:
  - Event create/update flow now computes `location_coords`, `travel_duration_minutes`, and `departure_time` for travel-aware events.
  - Reminder worker now generates `departure` reminders when `departure_time` exists and the event falls inside the scanning window.
  - Frontend calendar area now shows departure guide cards for travel-aware events and reminders area reflects departure notifications.
  - Test suite increased to `16 passed`.
- Follow-up update - 2026-03-27 09:10 Asia/Shanghai:
  - Suggestion engine now emits `departure_plan` and `weather_watch` items in addition to task slot suggestions.
  - Assistant create-event path now routes through the travel-aware event service.
  - Frontend insights area can render typed suggestion cards, including departure and weather context.
  - Test suite increased to `17 passed`.
- Follow-up update - 2026-03-27 09:20 Asia/Shanghai:
  - Suggestion engine now produces typed `departure_plan`, `weather_watch`, and `task_slot` items together.
  - Assistant prompt path now includes persisted profile plus external weather/commute context.
  - Travel-aware event creation is routed through the unified event service and shares departure-time computation logic.
  - Test suite increased to `17 passed`.
- Follow-up update - 2026-03-27 10:20 Asia/Shanghai:
  - Added backend Google Calendar one-way mirror sync foundation without redoing prior API validation or technical selection work.
  - Extended `user_profile` with Google OAuth/token and sync status fields, and extended `events` with mirror metadata (`external_calendar_id`, `external_etag`, `sync_status`, `last_synced_at`).
  - Added `GoogleCalendarClient` and `GoogleCalendarService` to support OAuth start/callback, status query, manual sync, and local-event mirror writes.
  - Added new API endpoints: `GET /api/google-calendar/status`, `GET /api/google-calendar/auth/start`, `GET /api/google-calendar/auth/callback`, and `POST /api/google-calendar/sync`.
  - Wired event create/update/delete flow to mirror local events to Google Calendar when the user is connected, while skipping `google_imported` events to preserve the local-primary single-direction design.
  - Manual sync now supports two paths in one pass: push eligible local events to Google Calendar, and import remote-only Google events into local SQLite with `source=google_imported`.
  - Added Alembic migration `0002_google_calendar_sync_state` and verified the current database upgraded to `0002_google_calendar_sync_state (head)`.
  - Added backend tests for Google Calendar routes and sync service; backend pytest is now `20 passed`.
  - Updated backend dependencies to include Google Calendar client libraries and updated `.env.example` with `GOOGLE_CALENDAR_ID`.
  - Rebuilt `api`, `celery_worker`, and `celery_beat` containers with the new Google dependencies, then verified live `GET /api/google-calendar/status` and `GET /api/google-calendar/auth/start` responses from the running API.
  - Recommended next implementation step: expose Google Calendar connect/sync status in the frontend profile or context area, then strengthen assistant Chinese time/location extraction so sync-aware event creation is easier to demo end to end.
- Follow-up update - 2026-03-27 13:10 Asia/Shanghai:
  - Completed the frontend Google Calendar sync console module instead of stopping at backend-only support.
  - Added frontend store support for Google Calendar status fetch, OAuth redirect launch, callback completion handling, manual sync execution, sync result feedback, and callback error recovery.
  - Added a dedicated Google Calendar panel to the workstation UI so the user can see connection state, redirect URI, last sync metadata, and the latest sync result without leaving the main workspace.
  - Aligned frontend dev server port to `8888` so the existing Google OAuth redirect URI can land on the frontend callback page, which then exchanges the code through the backend callback API.
  - Added callback-path handling in the frontend app so `/auth/callback?code=...&state=...` can complete authorization and `/auth/callback?error=...` can return the user to the workspace with an inline error message.
  - Enhanced the calendar panel to visually distinguish local-primary events, imported Google events, and sync-state badges, improving live demo readability after sync.
  - Updated backend CORS allowlist for `127.0.0.1/localhost` ports `8888` and `4173` so the frontend can call the backend during local demo and preview flows.
  - Validation completed:
    - `pnpm run build` passed for the frontend.
    - `backend pytest` remains `20 passed`.
    - Browser-level verification confirmed the Google Calendar panel renders on the workspace page.
    - Browser-level verification confirmed `/auth/callback?error=access_denied` returns to the workspace and shows inline feedback in the Google Calendar panel.
  - Recommended next implementation step: strengthen assistant Chinese time/location extraction and complex intent parsing so the Google-connected demo can go from natural-language event creation to mirrored calendar sync in one continuous flow.
- Follow-up update - 2026-03-27 13:45 Asia/Shanghai:
  - Completed the next backend assistant module: stronger Chinese time/location extraction, richer rule-based fallback intent handling, and more context-aware assistant replies.
  - Assistant event parsing now supports more Chinese expressions including relative dates (`明天`, `后天`), weekday references (`下周一`), period words (`上午`, `下午`, `晚上`), Chinese numerals (`三点`, `十一点`), and explicit Chinese time ranges.
  - Assistant can now extract event locations from Chinese messages and use them when creating travel-aware events through the existing event service.
  - Assistant task parsing now supports richer Chinese task cues, including duration extraction, simple deadline extraction, preferred period detection, and split-task hints.
  - Added a rule-based fallback path so that when Gemini reply content is vague or returns no executable actions, clear Chinese schedule-creation requests can still be converted into safe backend actions.
  - Added schedule-guidance reply generation for planning-style Chinese requests, with free-slot summaries and optional commute/weather context woven into the reply.
  - Improved assistant action summaries so successful event replies can mention location, departure guidance, travel duration, and task deadlines more naturally.
  - Hardened repository user bootstrap logic against duplicate user creation races by handling `user_profile.username` integrity collisions during `get_or_create_user`.
  - Validation completed:
    - `backend pytest` increased to `26 passed`.
    - Added assistant regression tests covering Chinese time range extraction, weekday parsing, location extraction, task deadline parsing, schedule-guidance replies, and rule-based fallback when Gemini returns no actions.
    - Live API smoke verification succeeded with an isolated user: a Chinese request equivalent to “帮我安排明天下午三点到四点在图书馆开组会” produced a created event action and the event was readable through `GET /api/events`.
  - Recommended next implementation step: continue with more complete rule scheduling / task splitting, or connect the enhanced assistant action/result details more clearly into the frontend assistant panel for demo storytelling.
- Follow-up update - 2026-03-27 14:05 Asia/Shanghai:
  - Completed the next rule-scheduling module by turning `can_split` tasks into actual split-slot suggestions instead of a passive stored field.
  - Reworked the suggestion engine to respect profile working-window defaults (`wake_up_time`, `sleep_time`) when computing daily free slots.
  - Added preferred-period-aware slot adjustment so tasks marked for `morning`, `afternoon`, or `evening` are suggested inside the matching part of a free block rather than just anywhere in the day.
  - Added focused block planning using `preferences_json.focus_block_minutes`, allowing long tasks to be split into multiple structured suggestion segments with a shared split group and explicit segment numbering.
  - Added new suggestion metadata (`split_group`, `segment_index`, `segment_total`, `estimated_minutes`) and preserved compatibility with the existing suggestion endpoints.
  - Updated the frontend insights area so split suggestions are visually distinct and display segment numbering for demo readability.
  - Validation completed:
    - `backend pytest` increased to `29 passed`.
    - `pnpm run build` passed for the frontend after the suggestion metadata/UI updates.
    - Live API smoke verification succeeded with an isolated user: a 180-minute `can_split=true` task with `preferred_period=afternoon` produced three `task_split_slot` suggestions from `GET /api/suggestions/next`.
  - Remaining next step after this module: either feed these split-task plans more directly into assistant planning replies, or move on to deeper assistant integration of weather/commute/profile in complex event suggestion narratives.
- Follow-up update - 2026-03-27 14:20 Asia/Shanghai:
  - Completed the next assistant-planning integration module by wiring the rule scheduling engine directly into assistant planning replies and structured assistant actions.
  - Assistant planning-style requests now emit `suggest_schedule` actions containing structured suggestion items, instead of returning only plain text.
  - Assistant replies for planning requests now summarize concrete proposed slots, including split-task segment numbering when the suggestion engine generates multi-block plans.
  - Assistant task-creation flow now attempts to attach follow-up scheduling suggestions for the newly created task, so long tasks can immediately surface suggested execution blocks after creation.
  - Expanded rule-based planning intent detection to better catch natural Chinese guidance phrases such as “安排进去 / 插进去 / 安排一下”, reducing reliance on Gemini action output for planning-style requests.
  - Upgraded the frontend assistant panel so the latest assistant actions are rendered as readable cards rather than raw JSON, including specific handling for `create_event`, `create_task`, `conflict_warning`, and `suggest_schedule`.
  - Validation completed:
    - `backend pytest` increased to `32 passed`.
    - `pnpm run build` passed for the frontend after the assistant panel UI changes.
    - Live API smoke verification succeeded with an isolated user: after creating a 180-minute split-capable task, a Chinese planning request equivalent to “明天把写论文安排进去” returned a `suggest_schedule` action with three split segments and a natural-language summary.
  - Residual note:
    - The standalone `GET /api/suggestions/next` endpoint in this environment can still be sensitive to runtime-date differences, but assistant-integrated planning now explicitly selects target dates from the user message and returns the expected schedule suggestions directly.
- Follow-up update - 2026-03-27 14:35 Asia/Shanghai:
  - Completed the next assistant context-enrichment module by wiring weather, commute, and profile data more deeply into event-advice and event-creation replies.
  - Assistant now distinguishes planning-style event advice requests such as “几点出发 / 要不要带伞 / 路上多久” from direct create intents, so these questions can be answered as contextual guidance instead of forcing a write action.
  - Added event-specific context enrichment for assistant replies:
    - resolve destination location when possible,
    - choose a commute origin from profile home/work defaults based on user phrasing,
    - estimate route duration and distance,
    - fetch current destination-area weather when possible,
    - generate simple weather-sensitive advice for umbrella/outdoor scenarios.
  - Event creation replies and action payloads now carry richer context summaries (`commute_summary`, `weather_summary`, `advice_summary`) for downstream UI rendering.
  - Assistant planning/advice requests that can be answered by local rules now short-circuit Gemini, reducing unnecessary latency for deterministic context-rich replies.
  - Updated the frontend assistant panel so create-event action cards can surface commute/weather/advice summaries rather than only time and title.
  - Validation completed:
    - `backend pytest` increased to `35 passed`.
    - `pnpm run build` passed for the frontend after the assistant card enhancements.
    - Live API smoke verification succeeded with an isolated user profile plus a Chinese advisory request equivalent to “明天下午三点去图书馆开组会，我几点出发，要不要带伞”, returning a contextual assistant reply that referenced destination weather and umbrella-related advice without creating a new event.
    - Additional live API smoke verification succeeded for a commute-oriented query equivalent to “明天下午三点去北京大学开会，我几点出发”, returning a contextual assistant reply that referenced both estimated commute time/distance and destination weather.
  - Remaining next step:
    - move from advice-only to confirmable execution, so assistant can take a generated split schedule or context-enriched event recommendation and convert it into multiple persisted events/tasks after an explicit accept step.
- Follow-up update - 2026-03-27 14:25 Asia/Shanghai:
  - Completed the next confirmation-execution module by turning assistant planning output into a confirmable pending plan and a real execution step.
  - Assistant sessions now preserve pending schedule plans in `assistant_sessions.context_json` instead of dropping them after a suggestion-only response.
  - Added explicit confirmation/cancellation handling for follow-up messages such as “按这个安排执行” and “取消这个计划”.
  - When the user confirms a pending schedule plan, assistant now converts the suggested blocks into persisted local `focus_block` events through the normal event service rather than just repeating the suggestion text.
  - Added structured `apply_schedule` assistant actions alongside the per-event creation actions so the frontend can show one summary action plus the individual created schedule blocks.
  - Updated the assistant panel with direct confirm/cancel controls for the latest `suggest_schedule` action and dedicated rendering for `apply_schedule`.
  - Validation completed:
    - `backend pytest` increased to `38 passed`.
    - `pnpm run build` passed for the frontend after the confirm/apply assistant panel updates.
    - Live API smoke verification succeeded with an isolated user flow:
      1. create a split-capable long task,
      2. ask assistant to arrange it,
      3. receive a `suggest_schedule` action,
      4. send “按这个安排执行”,
      5. receive an `apply_schedule` action,
      6. verify the generated blocks exist through `GET /api/events`.
  - Remaining next step:
    - move from task-schedule confirmation into broader confirmable execution, such as confirming context-enriched event advice or allowing assistant to mark planned blocks back onto related tasks with stronger lifecycle tracking.
- Follow-up update - 2026-03-27 14:30 Asia/Shanghai:
  - Completed the next broader confirmable-execution module by extending the pending-confirmation flow from split-task schedules to context-enriched event proposals.
  - Generalized assistant session pending state from schedule-only storage to a more generic pending action model in `assistant_sessions.context_json`.
  - Event-advice requests that include enough time/location context now emit `propose_event` actions rather than staying text-only, allowing the assistant to present a concrete, context-enriched event proposal for confirmation.
  - Added support for confirmation phrases like “按这个建议创建”, so users can confirm an advised event directly instead of manually retyping the event details.
  - Confirming a pending event proposal now creates a real event through the standard event service and returns both `apply_event_proposal` and `create_event` actions.
  - Updated the frontend assistant panel to render event proposals and applied-event results, with direct confirm/cancel controls alongside the existing schedule-plan controls.
  - Validation completed:
    - `backend pytest` increased to `39 passed`.
    - `pnpm run build` passed for the frontend after the event-proposal assistant UI updates.
    - Live API smoke verification succeeded with an isolated advisory flow:
      1. ask assistant a Chinese event-advice question equivalent to “明天下午三点去北京大学开会，我几点出发，要不要带伞”,
      2. receive a `propose_event` action with commute/weather context,
      3. send “按这个建议创建”,
      4. receive `apply_event_proposal`,
      5. verify the created event exists through `GET /api/events`, including travel-aware metadata such as `travel_duration_minutes` and `departure_time`.
  - Remaining next step:
    - strengthen task lifecycle linkage so confirmed focus blocks and suggested plans feed back into task progress/state instead of remaining loosely associated by conversation only.
- Follow-up update - 2026-03-27 14:40 Asia/Shanghai:
  - Completed the next task-lifecycle linkage module by strongly connecting confirmed focus blocks back to their originating tasks.
  - Added `linked_task_id` to `events`, so focus-block events created from split-task execution now persist an explicit task linkage instead of remaining conversation-only artifacts.
  - Extended task read models with derived lifecycle metrics:
    - `scheduled_minutes`
    - `scheduled_blocks_count`
    - `remaining_minutes`
    - `completion_ratio`
  - Task service now computes these lifecycle metrics from linked events and can actively synchronize task state after confirmed schedule execution.
  - Confirmed split-plan execution now updates task state to `scheduled`, sets `linked_event_id` to the first generated focus block, and returns linked task progress data inside the `apply_schedule` assistant action.
  - Updated frontend assistant feedback so applied schedule cards can surface linked task lifecycle info (scheduled minutes, block count, status) instead of showing only the raw created event list.
  - Added lightweight calendar display support so focus-block events can expose their task association more clearly in the workspace timeline.
  - Validation completed:
    - `backend pytest` increased to `41 passed`.
    - `pnpm run build` passed for the frontend after the task-lifecycle UI updates.
    - Alembic migration `0003_event_task_linkage` applied successfully and database is now at `0003_event_task_linkage (head)`.
    - Live API smoke verification succeeded with an isolated lifecycle flow:
      1. create a 180-minute split-capable task,
      2. ask assistant to schedule it,
      3. confirm the generated split plan,
      4. verify `GET /api/events` returns three `focus_block` events with `linked_task_id`,
      5. verify `GET /api/tasks` returns the originating task as `status=scheduled`, `scheduled_minutes=180`, `scheduled_blocks_count=3`, `remaining_minutes=0`, and `completion_ratio=1.0`.
  - Remaining next step:
    - extend lifecycle linkage from “scheduled” into finer-grained execution/completion states so focus blocks can drive task progress after the user actually finishes or checks off planned work.
- Follow-up update - 2026-03-27 14:45 Asia/Shanghai:
  - Completed the next execution-progress module by letting focus-block completion/cancellation feed back into task lifecycle state and progress metrics.
  - Task lifecycle derivation now distinguishes planning progress from execution progress:
    - planning-side metrics: `scheduled_minutes`, `scheduled_blocks_count`, `remaining_minutes`, `completion_ratio`
    - execution-side metrics: `completed_minutes`, `completed_blocks_count`, `execution_ratio`
  - Task state derivation is now stronger:
    - `pending` when no active blocks remain,
    - `scheduled` when blocks exist but none are completed,
    - `in_progress` when at least one linked focus block is completed,
    - `done` when completed minutes cover the estimated task duration (unless already explicitly marked done).
  - Event update/delete paths now synchronize linked task lifecycle state automatically, so status changes to `focus_block` events are reflected in task progress without needing assistant involvement.
  - Updated the frontend workspace so focus blocks can be marked `completed` or `canceled` directly from the calendar/highlight cards, and the assistant/apply cards can surface linked task execution state.
  - Validation completed:
    - `backend pytest` increased to `44 passed`.
    - `pnpm run build` passed for the frontend after the execution-progress UI updates.
    - Live API smoke verification succeeded with an isolated lifecycle flow:
      1. create a split-capable task,
      2. ask assistant to generate and apply a split schedule,
      3. mark one block `completed`,
      4. mark one block `canceled`,
      5. verify `GET /api/tasks` returns the linked task as `status=in_progress`, `scheduled_minutes=120`, `completed_minutes=60`, `completed_blocks_count=1`, `remaining_minutes=60`, `completion_ratio=0.67`, and `execution_ratio=0.33`.
  - Remaining next step:
    - decide whether task completion should become partially automatic when all linked focus blocks are completed, and whether completed/canceled block feedback should also generate reminder/suggestion follow-ups.
- Follow-up update - 2026-03-28 01:58 Asia/Shanghai:
  - Completed the next auto-replanning and follow-up reminder module on top of focus-block execution feedback.
  - Suggestion generation now replans from task **remaining work** instead of always using original estimated duration, and distinguishes between:
    - `task_resume_slot` for continuing work already in progress
    - `task_replan_slot` for replacing canceled focus blocks
  - Event state changes on linked `focus_block` items now create immediate task-level reminders:
    - `task_progress` after a completed block
    - `task_replan` after a canceled block when work remains
  - The frontend Insights area now understands and visually labels the new reminder/suggestion types, so replanning signals are visible without opening raw JSON.
  - The frontend calendar/highlight cards already exposed complete/cancel actions from the previous module; this round makes those actions cascade into new suggestions and reminders automatically.
  - Validation completed:
    - `backend pytest` increased to `47 passed`.
    - frontend production build passed after the new suggestion/reminder label updates.
    - Live API smoke verification succeeded with an isolated replanning flow:
      1. create a split-capable task,
      2. apply a split plan,
      3. mark one block completed and another canceled,
      4. verify `GET /api/suggestions/next` returns `task_replan_slot` items for the remaining work,
      5. verify `GET /api/reminders` returns both `task_progress` and `task_replan` reminders.
  - Remaining next step:
    - extend the reminder/suggestion loop one step further so the assistant itself can proactively surface these execution-change follow-ups in conversation, not just through workspace polling and manual refresh.
- Follow-up update - 2026-03-28 02:05 Asia/Shanghai:
  - Completed the next assistant follow-up module by feeding execution-change signals back into assistant conversation handling.
  - Assistant now recognizes progress-followup questions such as “现在进展如何 / 接下来怎么安排 / 继续安排 / 还剩多少” as a dedicated intent instead of treating them as generic planning requests.
  - Added assistant-side access to recent task follow-up reminders (`task_progress`, `task_replan`) and current task lifecycle metrics, so replies can summarize both what just happened and what work remains.
  - For progress-followup requests, assistant now returns:
    - a natural-language progress digest,
    - recent execution-change reminders,
    - and a fresh `suggest_schedule` action based on remaining work, when a follow-up replan is available.
  - This closes the loop from:
    1. user executes or cancels focus blocks,
    2. backend recalculates task progress,
    3. reminders/suggestions are generated,
    4. assistant can then explain the latest state and propose the next schedule directly in conversation.
  - Validation completed:
    - `backend pytest` increased to `49 passed`.
    - frontend production build passed.
    - Live API smoke verification succeeded with an isolated follow-up flow:
      1. create a split-capable task,
      2. apply a split schedule,
      3. complete one block and cancel another,
      4. ask assistant “现在进展如何，接下来怎么安排”,
      5. verify the reply includes both progress summary and recent follow-up reminders,
      6. verify assistant returns a new `suggest_schedule` action containing `task_replan_slot` items for the remaining work.
  - Remaining next step:
    - decide whether the assistant should push these follow-up summaries proactively without waiting for the user to ask, for example through a dedicated conversational inbox item or assistant-triggered notification workflow.
- Follow-up update - 2026-03-28 02:22 Asia/Shanghai:
  - Completed the next proactive conversational inbox module by exposing execution follow-ups as a dedicated assistant inbox feed instead of relying only on ad-hoc questions or raw reminder lists.
  - Added `GET /api/assistant/inbox`, backed by assistant-side aggregation of:
    - recent task follow-up reminders (`task_progress`, `task_replan`),
    - active task execution state,
    - current replan/resume suggestions.
  - Extended the workspace WebSocket snapshot to include `assistant_inbox`, so follow-up cards can refresh proactively alongside reminders and suggestions.
  - Updated frontend workspace state to fetch and subscribe to the assistant inbox feed.
  - Updated the assistant panel to render follow-up inbox cards at the top of the conversation area, each with actionable quick actions such as:
    - `Review Plan`
    - `Continue Planning`
    - `Use in Assistant`
  - These cards route back into the assistant conversation by sending ready-made prompts like “现在进展如何，接下来怎么安排”, creating a stronger conversational follow-up loop.
  - Validation completed:
    - `backend pytest` increased to `50 passed`.
    - frontend production build passed after the assistant inbox UI changes.
    - Live API smoke verification succeeded with an isolated inbox flow:
      1. create and apply a split schedule,
      2. complete one block and cancel another,
      3. call `GET /api/assistant/inbox`,
      4. verify the inbox contains task replan, task progress, task status, and suggestion-derived follow-up cards with assistant-ready action messages.
  - Remaining next step:
    - decide whether the assistant should emit these follow-up items as actual persisted assistant messages or notification-to-chat entries automatically, instead of keeping them as a separate aggregated inbox feed.
- Follow-up update - 2026-03-28 02:35 Asia/Shanghai:
  - Completed the next proactive assistant-thread module by promoting follow-up inbox items into actual persisted assistant messages in the current chat session.
  - Added `GET /api/assistant/current`, which:
    - returns the current/active assistant session,
    - syncs newly generated inbox follow-ups into that session as assistant messages,
    - returns the latest assistant inbox payload alongside the hydrated session.
  - Added assistant-side de-duplication using session context (`surfaced_inbox_ids`) so the same inbox follow-up is not inserted into the message thread repeatedly.
  - Updated frontend workspace hydration to prefer `/api/assistant/current`, so opening the workstation now loads the assistant thread with proactive follow-up messages already inserted, instead of waiting for the user to send a new message first.
  - The assistant panel still keeps the dedicated inbox cards, but those items now also show up in the conversation history as proper assistant messages with structured follow-up metadata.
  - Validation completed:
    - `backend pytest` increased to `51 passed`.
    - frontend production build passed after the proactive assistant-thread integration.
    - Live API smoke verification succeeded with an isolated proactive-thread flow:
      1. create and apply a split task schedule,
      2. complete one block and cancel another,
      3. call `GET /api/assistant/current`,
      4. verify the current session contains newly inserted assistant follow-up messages for task progress, task replan, task status, and suggestion-derived follow-up guidance,
      5. verify session context stores `surfaced_inbox_ids` to prevent duplicate insertion.
  - Remaining next step:
    - decide whether these proactive assistant follow-up messages should also trigger stronger desktop/browser notification behavior or richer message grouping/threading so the assistant feed stays readable as more autonomous updates accumulate.
- Follow-up update - 2026-03-28 02:47 Asia/Shanghai:
  - Completed the next assistant follow-up grouping module by collapsing multiple same-task proactive updates into a single grouped summary item/message.
  - Assistant inbox aggregation now groups recent `task_progress`, `task_replan`, `task_status`, and suggestion-derived follow-ups for the same task into one `task_followup_group` item instead of emitting multiple parallel cards.
  - When a grouped follow-up is surfaced into the assistant thread, older same-task proactive messages are hidden from the session response through `hidden_message_ids`, keeping the visible message stream cleaner.
  - Session context now keeps lightweight tracking for grouped follow-up threading:
    - `surfaced_inbox_ids`
    - `hidden_message_ids`
    - `task_followup_message_ids`
  - The frontend assistant panel now renders grouped follow-up inbox cards with their nested entries visible, so the user still sees the underlying progress/replan/status details without flooding the top-level list.
  - Validation completed:
    - `backend pytest` increased to `54 passed`.
    - frontend production build passed after the grouped follow-up UI changes.
    - Live API smoke verification succeeded with an isolated grouped-follow-up flow:
      1. create and apply a split task schedule,
      2. complete one block and cancel another,
      3. verify `GET /api/assistant/inbox` returns a single `task_followup_group` instead of separate task progress/replan/status cards,
      4. verify `GET /api/assistant/current` returns the grouped proactive assistant message while older same-task proactive messages are hidden from the visible session stream.
  - Remaining next step:
    - decide whether grouped proactive threads should support explicit read/archive controls and thread compaction windows, so long-running users can actively manage the assistant feed instead of relying only on automatic hiding rules.
- Follow-up update - 2026-03-28 03:51 Asia/Shanghai:
  - Completed the next assistant-thread management module by adding explicit read/archive controls plus persistence and retention metadata for proactive follow-up threads.
  - Assistant inbox items now expose thread-management metadata:
    - `thread_id`
    - `read`
    - `archived`
    - `entry_count`
    - `updated_at`
  - Added thread-management endpoint:
    - `POST /api/assistant/inbox/{item_id}?action=read|archive`
  - Inbox state is now persisted in session context (`inbox_item_state`), so read/archive decisions survive refreshes and can be applied consistently to both inbox cards and the visible assistant conversation stream.
  - Archiving a grouped thread removes it from the assistant inbox and keeps its proactive grouped message hidden from the visible session flow.
  - Reading a grouped thread keeps it visible but marks it as read and timestamps the action via `updated_at`, so the UI can de-emphasize it without losing the thread.
  - Added compacting/cleanup support for inbox state persistence so the thread-state map stays bounded instead of growing indefinitely.
  - Validation completed:
    - `backend pytest` increased to `56 passed`.
    - frontend production build passed after the thread-management UI updates.
    - Live API smoke verification succeeded with an isolated management flow:
      1. create a grouped follow-up thread,
      2. mark it read,
      3. verify `GET /api/assistant/inbox` returns the same thread with `read=true` and a populated `updated_at`,
      4. archive it,
      5. verify `GET /api/assistant/inbox` returns no visible items,
      6. verify `GET /api/assistant/current` keeps the archived grouped thread hidden from the visible assistant session stream while persisting the state in `context_json.inbox_item_state`.
  - Remaining next step:
    - define the long-term cleanup policy for thread state and grouped follow-up history, such as automatic expiry of archived threads from session context and optional unread counters/summary badges at the workspace level.
- Follow-up update - 2026-03-28 03:45 Asia/Shanghai:
  - Completed the next assistant-thread management module by adding explicit read/archive controls and inbox-state persistence for proactive follow-up threads.
  - Assistant inbox items now expose management state:
    - `thread_id`
    - `read`
    - `archived`
    - `entry_count`
  - Added management endpoint:
    - `POST /api/assistant/inbox/{item_id}?action=read|archive`
  - Assistant now persists inbox management state in session context (`inbox_item_state`) and applies it when building the inbox feed.
  - Archiving a grouped follow-up thread now removes it from the assistant inbox and keeps its grouped proactive assistant message hidden from the visible session stream.
  - Reading a grouped follow-up thread keeps it visible but marks it as read, allowing the UI to visually de-emphasize it without losing context.
  - Added compacting logic for inbox state persistence so the management map does not grow without bound.
  - Updated the assistant panel UI with explicit `Mark Read` and `Archive` controls on proactive inbox cards.
  - Validation completed:
    - `backend pytest` increased to `55 passed`.
    - frontend production build passed after the inbox-management UI updates.
    - Live API smoke verification succeeded with an isolated management flow:
      1. create a grouped proactive follow-up thread,
      2. mark it read,
      3. verify `GET /api/assistant/inbox` returns the same thread with `read=true`,
      4. archive it,
      5. verify `GET /api/assistant/inbox` returns no visible items,
      6. verify `GET /api/assistant/current` keeps the archived thread hidden from the visible assistant session stream and records the state in `context_json.inbox_item_state`.
  - Remaining next step:
    - define a true lifecycle policy for long-running assistant threads, such as automatic expiry/cleanup windows, unread counters, or per-task thread retention rules, so the feed stays manageable over weeks instead of just during a demo session.
- Follow-up update - 2026-03-28 03:56 Asia/Shanghai:
  - Completed the next long-term thread-retention module by adding unread counters, read timestamps, and automatic archived-state cleanup for proactive assistant threads.
  - Assistant inbox now exposes `unread_total`, allowing the workspace header and assistant panel to show follow-up counts without recomputing them client-side.
  - Read/archive state now carries `updated_at`, so thread actions have an explicit management timestamp instead of only a boolean flag.
  - Added automatic cleanup of archived inbox state entries after a retention window, so session context can gradually shed old archived thread metadata instead of growing forever.
  - Updated the workspace header and assistant panel to surface the assistant follow-up unread count, making the proactive assistant feed visible even when the user is focused elsewhere in the workspace.
  - Validation completed:
    - `backend pytest` increased to `56 passed`.
    - frontend production build passed after unread badge and retention updates.
    - Live API smoke verification succeeded with an isolated retention flow:
      1. create a grouped proactive follow-up thread,
      2. verify `GET /api/assistant/inbox` reports `unread_total=1`,
      3. mark the thread read and verify `unread_total=0` plus a populated `updated_at`,
      4. archive the thread and verify it disappears from the visible inbox while remaining hidden from the current assistant session stream.
  - Remaining next step:
    - decide whether unread/archived thread counts should be elevated into stronger workspace-level notification or summary surfaces, or whether the current badge plus inbox/session model is enough for the final demo scope.
- Follow-up update - 2026-03-28 04:09 Asia/Shanghai:
  - Completed the next workspace digest module by adding a backend-driven assistant summary surface for the whole workstation instead of relying only on per-panel details.
  - Added `GET /api/assistant/summary`, which aggregates:
    - unread proactive follow-up count,
    - the current primary task and its execution state,
    - the next most relevant suggestion/replan move,
    - the next upcoming reminder.
  - Extended the workspace WebSocket snapshot to include `assistant_summary`, keeping the digest aligned with the rest of the live workspace data model.
  - Added a dedicated frontend summary panel (“Assistant Digest”) and wired it into workspace hydration/live refresh so the demo can show a one-glance assistant overview without scanning multiple sections.
- Follow-up update - 2026-03-28 (cross-panel linkage module):
  - Completed the cross-panel focus navigation module: clicking a summary card now highlights and scrolls to the related task/event/assistant thread.
  - Changes made:
    - Extended `AssistantSummaryCard` frontend type to include `related_task_id`, `related_event_id`, `thread_id`, and `meta`.
    - Added `focusedTaskId` / `focusedEventId` state + `focusTask` / `focusEvent` / `clearFocus` actions to the workspace store.
    - `SummaryPanel`: cards are now clickable — clicking a card with `related_task_id` fires `focusTask`, `related_event_id` fires `focusEvent`, `thread_id`-only fires `focusAssistant`; link badges render under the action button for discoverability.
    - `CalendarPanel`: accepts `focusedEventId` and `focusedTaskId` props; focused event cards get an indigo ring highlight + auto-scroll; added “Ask Assistant” button on focus_block cards with a linked task (emits task-specific continuation prompt + scrolls to assistant panel).
    - `InsightsPanel`: accepts `focusedTaskId`; focused task card gets indigo ring + auto-scroll; added `slotMessage` helper that includes task name in “Use This Slot” prompts; added “Plan in Assistant” shortcut on each task card.
    - `AssistantPanel`: added `focusTask` emit and a “View Task” button on inbox items with `related_task_id`.
    - `App.vue`: wired `handleFocusTask` / `handleFocusEvent` / `handleFocusAssistant` with scroll-to-panel behavior; `sendAndFocusAssistant` scrolls to assistant before sending so response is visible.
  - Tests:
    - Added `test_build_summary_cards_top_task_has_related_task_id` and `test_build_summary_cards_followups_card_unread_total` to verify cross-panel linkage metadata is present in backend summary output.
    - Backend pytest: 59 passed.
    - Frontend production build: passed.
  - Remaining next step:
    - Consider adding a visual “focus trail” indicator in the workspace header showing what is currently focused, or move to the next functional module such as richer assistant message rendering (markdown support) or a task quick-create shortcut from the calendar panel.
  - Surfaced the unread follow-up count both in the workspace header and inside the assistant panel, reinforcing the proactive-assistant state at multiple levels of the UI.
  - Validation completed:
    - `backend pytest` remained green at `56 passed`.
    - frontend production build passed after the summary panel integration.
    - Live API smoke verification succeeded with an isolated summary flow:
      1. create/apply a split task schedule,
      2. complete one block and cancel another,
      3. call `GET /api/assistant/summary`,
      4. verify the response includes digest cards for unread follow-ups, top task progress, next suggested move, and next reminder.
  - Remaining next step:
    - decide whether the final demo should invest in richer cross-panel orchestration (for example, clicking a summary card to focus/open the relevant task/event/assistant thread), or whether the current digest plus assistant action buttons is sufficient for the graduation presentation scope.
