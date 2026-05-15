# MA-IPAAS

Multi-Agent Intelligent Personal Affairs Assistant System

MA-IPAAS 是一个面向个人时间管理的智能事务助手。系统围绕日程、任务、提醒、出发建议和长期记忆构建，支持通过自然语言创建或调整安排，并在执行前使用 proposal 机制让用户确认关键写入操作。

项目源于毕业设计场景，但代码结构按可维护的 Web 应用组织：后端提供 FastAPI REST/WebSocket 服务，前端提供 Vue 3 单页应用，后台任务由 Celery 和 Redis 驱动。

## 功能概览

- 自然语言助手：支持中文时间、地点、日程、任务和多轮补全理解。
- Proposal-first 写入：新增、修改、取消等高影响操作先生成待确认方案，确认后再执行。
- 日程管理：支持事件创建、冲突检测、跨午夜时间段、默认时长推断和日/周/月视图。
- 任务管理：支持待办任务、优先级、预计时长、截止日期和任务排程建议。
- 主动提醒：支持出发提醒、晨间汇报、睡前复盘、deadline 风险和 pending proposal 跟进。
- 长期记忆：支持地点别名、习惯候选、记忆确认/拒绝和记忆冲突澄清。
- 地图与天气上下文：可接入高德地图和和风天气，用于通勤、出发和天气提示。
- Google Calendar：支持 OAuth 配置和日历同步相关服务。
- 多端体验：Web 前端支持桌面与移动布局，并保留 Tauri/Capacitor 集成目录。

## 技术栈

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x async ORM
- Alembic
- Pydantic v2
- Celery
- Redis
- SQLite
- WebSocket

### Frontend

- Vue 3
- TypeScript
- Vite
- Pinia
- FullCalendar
- Tailwind CSS
- Vitest
- Tauri / Capacitor integration scaffolding

### External Services

- DeepSeek / SiliconFlow compatible OpenAI API
- Google Gemini
- Google Calendar API
- Amap Web Service API
- QWeather API

## Quick Start

### Prerequisites

- Docker Desktop
- Node.js 18+
- pnpm
- Python 3.11+ if running the backend outside Docker

### 1. Clone

```bash
git clone <repository-url>
cd GraduationProject
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

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

For local-only development, map, weather and Google Calendar credentials can be left as placeholders unless you are testing those integrations.

### 3. Start With Docker Compose

```bash
docker compose up -d --build
```

Default service URLs:

- Frontend: `http://127.0.0.1:8888`
- Backend API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Redis: `127.0.0.1:6379`

### 4. Run Frontend Separately

If you prefer running the frontend through Vite:

```bash
cd frontend
pnpm install
pnpm dev
```

The Vite dev server uses `http://127.0.0.1:8888` by default.

### 5. Run Backend Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Common Commands

### Backend

```bash
cd backend
python -m pytest
python -m pytest tests/test_assistant_text_protocol.py -q
alembic upgrade head
```

### Frontend

```bash
cd frontend
pnpm install
pnpm test
pnpm build
```

### Browser Acceptance

```bash
node scripts/assistant_browser_full_acceptance.mjs
```

Run selected scenarios:

```bash
$env:ACCEPTANCE_SCENARIO_FILTER="BAI-P0-001,BAI-P1-408"
node scripts/assistant_browser_full_acceptance.mjs
```

The browser acceptance harness creates reports under:

```text
docs/development/browser_acceptance_runs/
```

Intermediate local artifacts should be archived under `logs/recycle/` instead of being left in the repository root.

## Project Structure

```text
GraduationProject/
├── backend/                         # FastAPI backend application
│   ├── alembic/                     # Database migration scripts
│   ├── app/
│   │   ├── api/                     # API routers, schemas and WebSocket entry points
│   │   ├── assistant_agents/        # Assistant specialists and orchestration helpers
│   │   ├── core/                    # Settings, Celery app and shared infrastructure
│   │   ├── db/                      # Database session and initialization
│   │   ├── input_adapters/          # Backend input adapter abstractions
│   │   ├── jobs/                    # Celery jobs and scheduled tasks
│   │   ├── output_adapters/         # Backend output adapter abstractions
│   │   ├── repositories/            # Data access layer
│   │   ├── schemas/                 # Shared schema definitions
│   │   ├── services/                # Business logic and assistant services
│   │   └── tools/                   # External service wrappers such as map/weather tools
│   ├── scripts/                     # Backend utility scripts
│   ├── tests/                       # Backend tests
│   ├── alembic.ini                  # Alembic configuration
│   ├── Dockerfile                   # Backend container image
│   ├── pytest.ini                   # Pytest configuration
│   └── requirements.txt             # Python dependencies
│
├── frontend/                        # Vue 3 frontend application
│   ├── android/                     # Capacitor Android project files
│   ├── ios/                         # Capacitor iOS project files
│   ├── public/                      # Static public assets
│   ├── src/
│   │   ├── api/                     # API client helpers
│   │   ├── components/              # Vue UI components
│   │   ├── i18n/                    # Localization resources
│   │   ├── inputAdapters/           # Frontend input adapter layer
│   │   ├── outputAdapters/          # Frontend output adapter layer
│   │   ├── platform/                # Platform-specific integration helpers
│   │   ├── plugins/                 # Frontend plugin setup
│   │   ├── stores/                  # Pinia stores
│   │   ├── types/                   # TypeScript type declarations
│   │   └── utils/                   # Shared frontend utilities
│   ├── src-tauri/                   # Tauri desktop shell
│   ├── tests/                       # Frontend tests
│   ├── package.json                 # Frontend scripts and dependencies
│   ├── pnpm-lock.yaml               # pnpm lockfile
│   └── vite.config.ts               # Vite configuration
│
├── docs/                            # Project documentation
│   ├── academic/                    # Graduation thesis and academic materials
│   ├── contributing/                # Contribution guide
│   ├── development/                 # Architecture, implementation and acceptance reports
│   ├── project-management/          # Task books, status reviews and checklists
│   ├── testing/                     # Test reports and testing notes
│   └── user-guide/                  # User-facing guides
│
├── reference/                       # Reference materials
├── scripts/                         # Repository-level automation and acceptance scripts
├── logs/                            # Local ignored logs and recycle area
│   └── recycle/                     # Archived local run artifacts
├── chroma_db/                       # Local vector database storage, ignored in normal use
├── docker-compose.yml               # Local multi-service deployment
├── .env.example                     # Environment variable template
└── README.md                        # Project entry document
```

## Architecture Overview

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

The assistant flow is designed around a proposal lifecycle:

1. The user sends a natural-language request.
2. The backend builds runtime context from calendar events, tasks, memory and active thread state.
3. The assistant interprets intent and produces either an answer, a clarification or one or more proposals.
4. Write operations remain pending until the user confirms a proposal.
5. The proposal manager executes confirmed actions idempotently and records execution status.

This design is intended to prevent accidental writes from ambiguous natural-language input.

## Testing Status

Recent validation includes:

- Backend assistant/proposal/memory tests: `89 passed`
- Frontend tests: `3 passed`
- Frontend production build: passed
- Browser full acceptance report: `99 total, 94 passed, 0 failed, 5 tracked`

The latest committed acceptance report is under:

```text
docs/development/browser_acceptance_runs/assistant_browser_full_acceptance_20260515053916.md
```

The tracked browser cases are scenarios that require deterministic provider or browser-network mocks beyond the current full browser harness.

## Documentation

See [docs/README.md](docs/README.md) for the full documentation index.

Useful entry points:

- [Architecture](docs/development/ARCHITECTURE.md)
- [Technical Spec](docs/development/TECHNICAL_SPEC.md)
- [Current Implementation Status](docs/development/CURRENT_IMPLEMENTATION_STATUS.md)
- [User Guide](docs/user-guide/USER_GUIDE.md)
- [Contributing](docs/contributing/CONTRIBUTING.md)

Some documents are graduation-project materials and may preserve historical planning state. For current behavior, prefer the code, tests and latest acceptance reports.

## Configuration Notes

- `.env` contains local secrets and must not be committed.
- `.env.example` documents expected variables.
- `client_secret.json` is ignored by Git and should be treated as a local Google OAuth credential file.
- Runtime databases, Chroma data, logs and generated build outputs are ignored.
- Local cleanup artifacts should go under `logs/recycle/`.

## Contributing

1. Keep changes focused and avoid committing generated local artifacts.
2. Run relevant backend and frontend tests before opening a PR.
3. For assistant behavior changes, add or update acceptance coverage where practical.
4. Keep documentation aligned with the actual implementation.

See [docs/contributing/CONTRIBUTING.md](docs/contributing/CONTRIBUTING.md) for more details.

## License

No open-source license file is currently included in this repository. Until a license is added by the project owner, all rights are reserved by default.
