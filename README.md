# MA-IPAAS 智能个人事务助手 / Intelligent Personal Affairs Assistant

MA-IPAAS（Multi-Agent Intelligent Personal Affairs Assistant System）是一个面向个人时间管理的智能事务助手。系统围绕日程、任务、提醒、出发建议和长期记忆构建，支持通过自然语言创建或调整安排，并在执行前使用 proposal 机制让用户确认关键写入操作。

MA-IPAAS is an intelligent personal affairs assistant for time and task management. It manages calendar events, tasks, reminders, departure guidance and long-term memory. Natural-language requests are converted into confirmable proposals before high-impact write operations are executed.

项目源于毕业设计场景，但代码结构按可维护的 Web 应用组织：后端提供 FastAPI REST/WebSocket 服务，前端提供 Vue 3 单页应用，后台任务由 Celery 和 Redis 驱动。

The project originated as a graduation project, but the codebase is organized as a maintainable web application: a FastAPI REST/WebSocket backend, a Vue 3 single-page frontend, and Celery/Redis for background jobs.

## 功能概览 / Features

- 自然语言助手：支持中文时间、地点、日程、任务和多轮补全理解。  
  Natural-language assistant for Chinese time expressions, locations, events, tasks and multi-turn slot filling.
- Proposal-first 写入：新增、修改、取消等高影响操作先生成待确认方案，确认后再执行。  
  Proposal-first writes: create, update and cancellation operations are proposed first and executed only after confirmation.
- 日程管理：支持事件创建、冲突检测、跨午夜时间段、默认时长推断和日/周/月视图。  
  Calendar management with event creation, conflict detection, cross-midnight ranges, default duration inference and day/week/month views.
- 任务管理：支持待办任务、优先级、预计时长、截止日期和任务排程建议。  
  Task management with priority, estimated duration, deadlines and scheduling suggestions.
- 主动提醒：支持出发提醒、晨间汇报、睡前复盘、deadline 风险和 pending proposal 跟进。  
  Proactive assistance for departure reminders, morning briefings, night reviews, deadline risks and pending proposal follow-ups.
- 长期记忆：支持地点别名、习惯候选、记忆确认/拒绝和记忆冲突澄清。  
  Long-term memory for place aliases and habits, with confirmation, rejection and conflict clarification.
- 地图与天气上下文：可接入高德地图和和风天气，用于通勤、出发和天气提示。  
  Map and weather context through Amap and QWeather integrations.
- Google Calendar：支持 OAuth 配置和日历同步相关服务。  
  Google Calendar OAuth configuration and calendar synchronization services.
- 多端体验：Web 前端支持桌面与移动布局，并保留 Tauri/Capacitor 集成目录。  
  Multi-platform readiness with responsive web UI and Tauri/Capacitor integration scaffolding.

## 技术栈 / Tech Stack

### 后端 / Backend

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x async ORM
- Alembic
- Pydantic v2
- Celery
- Redis
- SQLite
- WebSocket

### 前端 / Frontend

- Vue 3
- TypeScript
- Vite
- Pinia
- FullCalendar
- Tailwind CSS
- Vitest
- Tauri / Capacitor integration scaffolding

### 外部服务 / External Services

- DeepSeek / SiliconFlow compatible OpenAI API
- Google Gemini
- Google Calendar API
- Amap Web Service API
- QWeather API

## 快速开始 / Quick Start

### 前置条件 / Prerequisites

- Docker Desktop
- Node.js 18+
- pnpm
- Python 3.11+（仅在不使用 Docker 运行后端时需要）  
  Python 3.11+ if running the backend outside Docker

### 1. 克隆项目 / Clone

```bash
git clone <repository-url>
cd GraduationProject
```

### 2. 配置环境变量 / Configure Environment

复制环境变量模板：

Copy the example environment file:

```bash
cp .env.example .env
```

然后编辑 `.env`，填入实际需要的 API Key：

Then edit `.env` and fill in the API keys you actually need:

```env
APP_TIMEZONE=Asia/Shanghai
API_HOST_PORT=8000

LLM_PROVIDER=deepseek
LLM_FALLBACK_PROVIDER=gemini
DEEPSEEK_API_KEY=your_deepseek_or_siliconflow_api_key
GEMINI_API_KEY=your_gemini_api_key

MAP_PROVIDER=amap
MAP_API_KEY=your_amap_api_key

WEATHER_PROVIDER=qweather
QWEATHER_API_KEY=your_qweather_api_key

GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8888/auth/callback
```

如果只进行本地开发，地图、天气和 Google Calendar 凭据可以暂时保留为占位值，除非你正在测试对应集成。

For local-only development, map, weather and Google Calendar credentials can stay as placeholders unless you are testing those integrations.

### 3. 使用 Docker Compose 启动 / Start With Docker Compose

```bash
docker compose up -d --build
```

默认服务地址：

Default service URLs:

- Frontend: `http://127.0.0.1:8888`
- Backend API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Redis: `127.0.0.1:6379`

### 4. 单独运行前端 / Run Frontend Separately

如果你希望通过 Vite 开发服务器运行前端：

If you prefer running the frontend through Vite:

```bash
cd frontend
pnpm install
pnpm dev
```

Vite 开发服务器默认使用 `http://127.0.0.1:8888`。

The Vite dev server uses `http://127.0.0.1:8888` by default.

### 5. 本地运行后端 / Run Backend Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS/Linux 使用：

On macOS/Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## 常用命令 / Common Commands

### 后端 / Backend

```bash
cd backend
python -m pytest
python -m pytest tests/test_assistant_text_protocol.py -q
alembic upgrade head
```

### 前端 / Frontend

```bash
cd frontend
pnpm install
pnpm test
pnpm build
```

### 浏览器验收 / Browser Acceptance

```bash
node scripts/assistant_browser_full_acceptance.mjs
```

运行指定场景：

Run selected scenarios:

```bash
$env:ACCEPTANCE_SCENARIO_FILTER="BAI-P0-001,BAI-P1-408"
node scripts/assistant_browser_full_acceptance.mjs
```

浏览器验收报告会生成在：

The browser acceptance harness creates reports under:

```text
docs/development/browser_acceptance_runs/
```

中间运行产物应归档到 `logs/recycle/`，不要散落在仓库根目录。

Intermediate local artifacts should be archived under `logs/recycle/` instead of being left in the repository root.

## 项目结构 / Project Structure

```text
GraduationProject/
├── backend/                         # FastAPI 后端 / FastAPI backend application
│   ├── alembic/                     # 数据库迁移 / Database migration scripts
│   ├── app/
│   │   ├── api/                     # API 路由、Schema、WebSocket 入口 / API routers, schemas and WebSocket entry points
│   │   ├── assistant_agents/        # 助手专家与编排辅助 / Assistant specialists and orchestration helpers
│   │   ├── core/                    # 配置、Celery、共享基础设施 / Settings, Celery app and shared infrastructure
│   │   ├── db/                      # 数据库会话与初始化 / Database session and initialization
│   │   ├── input_adapters/          # 后端输入适配器 / Backend input adapter abstractions
│   │   ├── jobs/                    # Celery 任务和定时任务 / Celery jobs and scheduled tasks
│   │   ├── output_adapters/         # 后端输出适配器 / Backend output adapter abstractions
│   │   ├── repositories/            # 数据访问层 / Data access layer
│   │   ├── schemas/                 # 共享 Schema / Shared schema definitions
│   │   ├── services/                # 业务逻辑与助手服务 / Business logic and assistant services
│   │   └── tools/                   # 外部服务封装 / External service wrappers
│   ├── scripts/                     # 后端工具脚本 / Backend utility scripts
│   ├── tests/                       # 后端测试 / Backend tests
│   ├── alembic.ini                  # Alembic 配置 / Alembic configuration
│   ├── Dockerfile                   # 后端容器镜像 / Backend container image
│   ├── pytest.ini                   # Pytest 配置 / Pytest configuration
│   └── requirements.txt             # Python 依赖 / Python dependencies
│
├── frontend/                        # Vue 3 前端 / Vue 3 frontend application
│   ├── android/                     # Capacitor Android 工程 / Capacitor Android project files
│   ├── ios/                         # Capacitor iOS 工程 / Capacitor iOS project files
│   ├── public/                      # 静态资源 / Static public assets
│   ├── src/
│   │   ├── api/                     # API 客户端 / API client helpers
│   │   ├── components/              # Vue 组件 / Vue UI components
│   │   ├── i18n/                    # 国际化资源 / Localization resources
│   │   ├── inputAdapters/           # 前端输入适配层 / Frontend input adapter layer
│   │   ├── outputAdapters/          # 前端输出适配层 / Frontend output adapter layer
│   │   ├── platform/                # 平台集成辅助 / Platform-specific integration helpers
│   │   ├── plugins/                 # 前端插件配置 / Frontend plugin setup
│   │   ├── stores/                  # Pinia 状态管理 / Pinia stores
│   │   ├── types/                   # TypeScript 类型声明 / Type declarations
│   │   └── utils/                   # 共享前端工具 / Shared frontend utilities
│   ├── src-tauri/                   # Tauri 桌面壳 / Tauri desktop shell
│   ├── tests/                       # 前端测试 / Frontend tests
│   ├── package.json                 # 前端脚本和依赖 / Frontend scripts and dependencies
│   ├── pnpm-lock.yaml               # pnpm 锁文件 / pnpm lockfile
│   └── vite.config.ts               # Vite 配置 / Vite configuration
│
├── docs/                            # 项目文档 / Project documentation
│   ├── academic/                    # 毕设和学术材料 / Graduation thesis and academic materials
│   ├── contributing/                # 贡献指南 / Contribution guide
│   ├── development/                 # 架构、实现和验收报告 / Architecture, implementation and acceptance reports
│   ├── project-management/          # 任务书、状态审查和检查清单 / Task books, status reviews and checklists
│   ├── testing/                     # 测试报告和测试说明 / Test reports and testing notes
│   └── user-guide/                  # 用户指南 / User-facing guides
│
├── reference/                       # 参考资料 / Reference materials
├── scripts/                         # 仓库级自动化和验收脚本 / Repository-level automation and acceptance scripts
├── logs/                            # 本地日志和回收区，Git 忽略 / Local ignored logs and recycle area
│   └── recycle/                     # 本地运行产物归档 / Archived local run artifacts
├── chroma_db/                       # 本地向量数据库存储，通常忽略 / Local vector database storage, normally ignored
├── docker-compose.yml               # 本地多服务部署 / Local multi-service deployment
├── .env.example                     # 环境变量模板 / Environment variable template
└── README.md                        # 项目入口文档 / Project entry document
```

## 架构概览 / Architecture Overview

系统采用分层架构：

The system follows a layered architecture:

```text
Frontend UI
  ↓ REST / WebSocket
FastAPI routes
  ↓
Services and assistant orchestration
  ↓
Repositories
  ↓
SQLite / local storage / external service APIs
```

助手流程围绕 proposal 生命周期设计：

The assistant flow is designed around a proposal lifecycle:

1. 用户发送自然语言请求。  
   The user sends a natural-language request.
2. 后端基于日程、任务、记忆和当前线程状态构建运行时上下文。  
   The backend builds runtime context from calendar events, tasks, memory and active thread state.
3. 助手判断意图，返回回答、澄清问题或一个/多个待确认方案。  
   The assistant interprets intent and returns either an answer, a clarification or one or more proposals.
4. 写入操作在用户确认 proposal 前保持 pending 状态。  
   Write operations remain pending until the user confirms a proposal.
5. Proposal manager 幂等执行已确认动作并记录执行状态。  
   The proposal manager executes confirmed actions idempotently and records execution status.

这一设计用于降低自然语言歧义导致误写入的风险。

This design reduces the risk of accidental writes caused by ambiguous natural-language input.

## 测试状态 / Testing Status

近期验证结果：

Recent validation includes:

- 后端 assistant/proposal/memory 相关测试：`89 passed`  
  Backend assistant/proposal/memory tests: `89 passed`
- 前端测试：`3 passed`  
  Frontend tests: `3 passed`
- 前端生产构建：通过  
  Frontend production build: passed
- 浏览器全量验收：`99 total, 94 passed, 0 failed, 5 tracked`  
  Browser full acceptance report: `99 total, 94 passed, 0 failed, 5 tracked`

最新已提交的验收报告：

The latest committed acceptance report is under:

```text
docs/development/browser_acceptance_runs/assistant_browser_full_acceptance_20260515053916.md
```

`tracked` 浏览器场景需要更确定性的 provider 或浏览器网络 mock，当前全量浏览器 harness 仅记录追踪。

The tracked browser cases require deterministic provider or browser-network mocks beyond the current full browser harness.

## 文档 / Documentation

完整文档索引见 [docs/README.md](docs/README.md)。

See [docs/README.md](docs/README.md) for the full documentation index.

常用入口：

Useful entry points:

- [Architecture](docs/development/ARCHITECTURE.md)
- [Technical Spec](docs/development/TECHNICAL_SPEC.md)
- [Current Implementation Status](docs/development/CURRENT_IMPLEMENTATION_STATUS.md)
- [User Guide](docs/user-guide/USER_GUIDE.md)
- [Contributing](docs/contributing/CONTRIBUTING.md)

部分文档是毕业设计材料，可能保留历史规划状态。判断当前行为时，请优先参考代码、测试和最新验收报告。

Some documents are graduation-project materials and may preserve historical planning state. For current behavior, prefer the code, tests and latest acceptance reports.

## 配置说明 / Configuration Notes

- `.env` 包含本地密钥，不应提交。  
  `.env` contains local secrets and must not be committed.
- `.env.example` 记录期望的环境变量。  
  `.env.example` documents expected variables.
- `client_secret.json` 被 Git 忽略，应视为本地 Google OAuth 凭据文件。  
  `client_secret.json` is ignored by Git and should be treated as a local Google OAuth credential file.
- 运行时数据库、Chroma 数据、日志和构建产物均应保持忽略。  
  Runtime databases, Chroma data, logs and generated build outputs should stay ignored.
- 本地清理产物应归档到 `logs/recycle/`。  
  Local cleanup artifacts should go under `logs/recycle/`.

## 贡献 / Contributing

1. 保持改动聚焦，不提交本地生成产物。  
   Keep changes focused and avoid committing generated local artifacts.
2. 提交 PR 前运行相关后端和前端测试。  
   Run relevant backend and frontend tests before opening a PR.
3. 修改助手行为时，尽量补充或更新验收覆盖。  
   For assistant behavior changes, add or update acceptance coverage where practical.
4. 文档应与真实实现保持一致。  
   Keep documentation aligned with the actual implementation.

更多说明见 [docs/contributing/CONTRIBUTING.md](docs/contributing/CONTRIBUTING.md)。

See [docs/contributing/CONTRIBUTING.md](docs/contributing/CONTRIBUTING.md) for more details.

## 许可证 / License

当前仓库尚未包含开源许可证文件。在项目所有者添加许可证前，默认保留所有权利。

No open-source license file is currently included in this repository. Until a license is added by the project owner, all rights are reserved by default.
