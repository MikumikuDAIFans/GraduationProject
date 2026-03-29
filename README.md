# 智能个人事务助手系统

**MA-IPAAS — Multi-Agent Intelligent Personal Affairs Assistant System**

一个面向个人时间管理的 AI 事务助手，以日程、待办、出发提醒和行动建议为核心，支持自然语言交互、日程规划、冲突检测和主动推送。

---

## 目录

- [用户功能介绍](#用户功能介绍)
- [技术栈与实现](#技术栈与实现)
- [快速启动](#快速启动)

---

## 用户功能介绍

### 1. 日历与日程管理

#### 1.1 全视图日历

- 支持**月视图、周视图、日视图**三种切换模式，适应不同规划粒度
- 桌面端默认显示周视图，手机端默认显示日视图
- 实时时间指示线：日历上标注当前时刻，一眼看出今日剩余时间
- 本地事件与 Google Calendar 导入事件分色区分：
  - 本地创建事件显示为**蓝紫色**
  - Google 导入事件显示为**天蓝色**，标注 ☁ 图标
  - 专注时间块（Focus Block）显示为**紫色**

#### 1.2 事件列表

- 日历下方列出近期事件卡片，按时间排序
- 每张卡片显示：事件名称、开始时间、同步状态（本地 / 已同步 / 导入 / 错误）
- 如事件关联了待办任务，展示任务名称及已完成 / 计划时长进度
- 焦点高亮：当 AI 助手推荐某任务时，对应事件卡片自动滚动到视野中并高亮显示

#### 1.3 出发指引（Departure Guides）

- 对含有地点信息且配置了出发时间的事件，日历页下方显示**出发指引卡片**
- 展示：目标地点、建议出发时间、预计通勤时长、出行方式（驾车 / 步行）
- 数据来源于高德地图路线估算，结合用户设置的家庭/工作地点

#### 1.4 专注时间块管理

- 事件可标记为"专注时间块"（focus_block），用于 AI 自动在空闲时段插入任务
- 专注块完成后可点击**Done** 标记已完成，或点击 **Cancel** 取消
- 可点击 **Ask AI** 向 AI 助手询问当前任务进展建议

#### 1.5 Google Calendar 同步

- 支持 OAuth 2.0 授权连接 Google Calendar
- 导入外部日历事件并在本地日历中展示，标注来源
- 可手动触发同步，拉取最新 Google 日历数据
- 同步状态实时展示：已同步、同步错误、仅本地

---

### 2. 待办任务管理

#### 2.1 任务列表

- Insights 面板展示所有待办任务，按优先级和截止时间排列
- 每条任务显示：任务内容、优先级（1-5）、预计时长、截止日期、完成进度
- 任务状态：待处理（pending）/ 进行中（in_progress）/ 已完成（done）

#### 2.2 任务操作

- 通过 AI 对话创建任务：告诉 AI "帮我添加一个任务：准备答辩 PPT，截止周五"，系统自动解析并创建
- 在 Insights 面板直接勾选完成，或标记为进行中
- 删除不再需要的任务

#### 2.3 任务与日程联动

- 任务可关联日历事件（任务对应的专注时间块）
- 系统追踪每个任务已完成的专注块数量和时长
- AI 在推荐空档时，优先插入未完成或已取消过的任务

#### 2.4 任务拆分

- 支持将一个大任务（`can_split=true`）拆分成多个小专注段插入不同空档
- 拆分时段不短于 30 分钟，段与段之间保留 5 分钟缓冲
- AI 建议卡片中展示"Segment 1/3"等进度信息

---

### 3. AI 助手（Daily Copilot）

#### 3.1 自然语言对话

- 支持中文自然语言输入，AI 由 Google Gemini 驱动
- 可识别时间表达：今天、明天、后天、下周一、晚上八点、明早九点半等
- 支持 Ctrl+Enter 快捷发送

#### 3.2 对话式日程创建

- 描述事件，AI 自动解析标题、时间、地点并创建到日历
- 示例：`"帮我把明天下午三点到五点的组会加到日历"`
- 创建成功后在对话下方显示**已创建事件**的动作卡片

#### 3.3 对话式任务创建

- 通过对话添加任务，AI 自动提取内容、预计时长、截止时间
- 示例：`"我需要在周四前完成一份报告，大概要两小时"`
- 任务创建成功后显示**已创建任务**动作卡片

#### 3.4 智能日程安排建议

- 告诉 AI 一批任务，AI 在现有日历空档中智能推荐安排时段
- 示例：`"帮我把复习和买东西安排到今天"`
- AI 返回**日程建议**卡片，包含建议时间段列表
- 用户可点击 **Confirm** 确认创建，或 **Cancel** 放弃

#### 3.5 冲突检测与警告

- AI 创建事件时自动检测与现有日程的时间重叠
- 若发现冲突，在对话中显示**冲突警告**卡片，标注冲突事件名称和时间

#### 3.6 事件提案（Propose Event）

- AI 可主动提案新事件，展示标题、建议时间
- 用户确认后一键创建到日历

#### 3.7 上下文感知回复

- AI 在回答时可获取：当天/未来的日历事件、当前天气、待处理任务列表、用户偏好
- 会话历史持久化：同一个聊天会话中，AI 记得之前的对话内容
- 多会话管理：每次进入新会话或刷新时可获取历史会话

#### 3.8 Inbox 通知中心

- AI 主动生成的事项通知（如任务跟进、冲突提醒等）汇集在 Inbox
- Inbox 默认折叠，有新消息时在 Header 右侧显示数量徽标
- 每条 Inbox 消息支持：执行快捷操作（Action Button）、标记已读、✕ 归档
- 归档操作即时生效（乐观 UI），同步至后端

#### 3.9 AI 每日摘要卡片

- Summary 面板展示 AI 生成的当日摘要卡片
- 摘要涵盖：今日事件概览、待处理任务风险、未读跟进提醒数量等
- 每张摘要卡片有情绪色调（积极 / 警告 / 中性）和可选操作按钮

---

### 4. 主动提醒与建议（Insights）

#### 4.1 空档建议

- 系统每次更新时计算用户工作窗口（起床时间到睡眠时间）内的空闲时段
- 将优先级高、截止临近或曾被取消的任务插入空档，生成建议
- 建议卡片显示：建议时段、任务名称、说明（优先级、预计时长）

#### 4.2 任务拆分建议

- 对可拆分的长任务，系统在多个空档中生成分段建议
- 每个分段标注"Segment N/总段数"，帮助用户合理分配时间

#### 4.3 出发计划建议

- 对含有出发时间的事件，Insights 中展示出发计划建议卡片
- 标明建议出发时刻、目的地、预计通勤时长

#### 4.4 天气提示

- 若用户设置了家庭地址，Insights 展示当前天气状况卡片
- 包含：天气描述、气温、湿度，供出门前参考

#### 4.5 自动提醒生成

- 后台 Celery 任务每隔数分钟扫描未来 24 小时内的事件
- 自动在事件开始前 30 分钟生成**事件开始提醒**
- 对含有出发时间的事件，自动在出发时刻生成**出发提醒**
- 提醒通过 WebSocket 实时推送到前端，在 Reminders 标签中展示

---

### 5. 上下文面板（Context）

- 实时展示当前天气：温度、天气描述、风向风级、湿度、降水量、能见度
- 实时通勤估算：从家到工作地点的预计通勤时长和距离（高德地图）
- 天气和通勤数据均展示最后更新时间

---

### 6. 用户设置（Profile）

- 设置用户名和显示名
- 设置时区（默认 Asia/Shanghai）
- 设置**家庭地址**和**工作地点**（用于天气和通勤估算）
- 设置偏好出行方式（驾车 / 步行 / 公交）
- 设置起床时间和睡眠时间（用于空档计算的工作窗口）
- 设置专注块时长（preferences_json.focus_block_minutes，默认 60 分钟）
- Google Calendar 连接状态展示和授权入口

---

### 7. 移动端适配

- 手机端采用底部标签导航：概览（Summary）/ 日历（Calendar）/ 建议（Insights）/ 助手（Assistant）
- 日历在手机端默认日视图，支持切换到周视图和月视图，工具栏自动换行不溢出
- 布局使用 `h-dvh` 动态视口高度，正确适配 iOS Safari 工具栏
- 助手聊天区域在手机端全屏展示，输入框始终固定在底部

---

## 技术栈与实现

### 前端

| 技术 | 用途 |
|---|---|
| Vue 3 + TypeScript | 组件框架与类型安全 |
| Vite | 构建工具与开发服务器 |
| TailwindCSS | 原子化 CSS，自定义设计令牌 |
| Pinia | 全局状态管理（workspace store） |
| FullCalendar | 日历可视化（dayGrid + timeGrid 插件） |
| Axios | HTTP 请求封装 |
| marked | Markdown 渲染（AI 回复） |

**前端架构要点：**

- **单 Store 架构**：全部业务状态集中在 `workspace.ts` 的 Pinia store，通过 WebSocket 定期接收后端 `workspace_snapshot` 更新，避免频繁轮询
- **WebSocket 驱动**：连接 `/ws/notifications`，每 8 秒接收一次快照，包含提醒、今日建议、未来建议、Inbox、摘要等所有动态数据
- **扁平白色设计系统**：在 `tailwind.config.ts` 中定义语义色彩令牌（`ink` / `surface` / `border` / `accent` / `positive` / `warn` / `danger`），全组件统一使用
- **移动端底部 Tab**：`App.vue` 通过 `mobileTab` ref 控制当前激活面板，`h-dvh` 布局规避 iOS 浏览器地址栏高度问题
- **AssistantPanel**：Inbox 默认折叠减少视觉密度，AI 回复使用 `.assistant-md-light` light-mode prose CSS 渲染 markdown，Archive 采用乐观 UI（本地立即隐藏，后台异步更新）

### 后端

| 技术 | 用途 |
|---|---|
| Python 3.11 | 主语言 |
| FastAPI | Web 框架，REST API + WebSocket |
| SQLAlchemy 2 | ORM（async，mapped_column 风格） |
| Alembic | 数据库迁移 |
| Pydantic v2 | 请求/响应 Schema 验证 |
| Celery + Redis | 异步任务队列与定时调度 |
| SQLite | 业务数据持久化 |
| Uvicorn | ASGI 服务器 |

**后端架构要点：**

- **分层架构**：`api/routes → services → repositories → models`，清晰分离接入层、业务层、数据访问层
- **Assistant 工作流**：`AssistantService` 接收用户消息，调用 `GeminiClient` 进行意图理解和自然语言处理，解析返回的 action（`create_event` / `create_task` / `suggest_schedule` 等），调用对应 Service 执行操作，最终返回自然语言回复 + actions 列表
- **调度引擎**（`SuggestionService`）：
  - 基于用户的起床/睡眠时间计算每日工作窗口
  - 遍历日历事件，计算相邻事件之间的空闲时段
  - 将待处理任务按优先级、截止时间、已取消块数量排序
  - 为可拆分任务生成分段建议（每段 ≥30 分钟，段间 5 分钟缓冲）
  - 对含出发时间的事件生成出发计划建议
  - 调用天气 API 生成天气提示卡片
- **提醒引擎**（`jobs/reminders.py`）：Celery Beat 定时任务，扫描未来 24 小时事件，自动生成 `event_start`（开始前 30 分钟）和 `departure`（出发时刻）两类提醒记录，幂等写入（已存在则跳过）
- **Google Calendar**：OAuth 2.0 授权流程，令牌持久化在 `user_profile` 表，支持手动触发同步拉取外部事件并写入本地 `events` 表，标记 `source=google_imported`
- **地图工具**（`tools/amap.py`）：高德地图地理编码 + 路线规划 API 封装，支持驾车/步行，返回时长（秒/分钟）和距离（米/千米）
- **天气工具**（`tools/qweather.py`）：和风天气实况 API 封装，返回温度、体感、天气描述、风向风级、湿度、降水量、能见度

### 数据库

共 7 张核心表：

| 表名 | 说明 |
|---|---|
| `user_profile` | 用户信息、地址偏好、Google Calendar OAuth 令牌 |
| `events` | 日历事件，含通勤字段、外部同步字段、关联任务 ID |
| `tasks` | 待办任务，含优先级、截止时间、拆分标志、关联事件 ID |
| `reminders` | 提醒记录，含提醒类型、触发时刻、投递渠道、状态 |
| `assistant_sessions` | 助手会话，含上下文 JSON |
| `assistant_messages` | 对话消息，含角色、内容、tool_calls JSON |
| `schedule_change_logs` | 日程变更日志，用于审计和答辩可解释性 |

### 部署

- 全部后端组件（FastAPI API、Celery Worker、Celery Beat、Redis）运行在 **Docker 容器**中
- SQLite 数据文件通过 Docker volume 挂载持久化
- 前端以 Vite 开发服务器本地运行，或构建为静态文件由 Nginx 托管
- `docker-compose.yml` 一键启动所有后端服务

---

## 快速启动

### 前置条件

- Docker Desktop（运行后端）
- Node.js 18+ + pnpm（运行前端）
- 复制 `.env.example` 为 `.env`，填入 API 密钥

### 环境变量

```env
GEMINI_API_KEY=          # Google Gemini API Key
QWEATHER_API_KEY=        # 和风天气 API Key
MAP_API_KEY=             # 高德地图 Web Service API Key
MAP_PROVIDER=amap
GOOGLE_CLIENT_ID=        # Google OAuth Client ID
GOOGLE_CLIENT_SECRET=    # Google OAuth Client Secret
GOOGLE_REDIRECT_URI=     # OAuth 回调地址
```

### 启动后端

```bash
cd GraduationProject
docker compose up -d
```

### 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

访问 `http://localhost:8888`

---

## 与设计书对比及后续计划

详见下方 [功能对比](#功能对比与后续计划) 章节。

---

## 功能对比与后续计划

### 已实现（与设计书 V2 完全一致）

| 设计书要求 | 实现状态 |
|---|---|
| Vue 3 + TypeScript + Vite + TailwindCSS + FullCalendar + Pinia | ✅ 完整实现 |
| FastAPI + SQLAlchemy 2 + Alembic + Celery + Redis + SQLite | ✅ 完整实现 |
| 7 张核心数据库表（含 schedule_change_logs） | ✅ 完整实现 |
| 事件 CRUD API | ✅ 完整实现 |
| 任务 CRUD API | ✅ 完整实现 |
| 助手消息接口 `POST /api/assistant/message` | ✅ 完整实现 |
| 助手会话持久化 | ✅ 完整实现 |
| 日历区：日/周/月视图、事件展示、冲突高亮 | ✅ 完整实现 |
| 助手区：自然语言输入、对话创建事件/任务、确认建议 | ✅ 完整实现 |
| 提醒区：待提醒项目、出发提醒、空档建议 | ✅ 完整实现 |
| Celery Beat 定时扫描提醒（event_start + departure） | ✅ 完整实现 |
| WebSocket `/ws/notifications` 实时推送 | ✅ 完整实现 |
| 规则引擎：空闲时段计算、任务插空、拆分建议 | ✅ 完整实现 |
| 高德地图 API：地理编码 + 路线估算 | ✅ 完整实现 |
| 和风天气 API：实况天气 | ✅ 完整实现 |
| Google Calendar OAuth 同步（手动触发拉取） | ✅ 完整实现 |
| Docker 容器化部署（API + Worker + Beat + Redis） | ✅ 完整实现 |
| 移动端响应式适配 | ✅ 完整实现 |
| `schedule_change_logs` 审计日志 | ✅ 完整实现 |

### 部分实现或与设计书存在差异

| 设计书要求 | 当前状态 | 说明 |
|---|---|---|
| 冲突检测带缓冲时间（buffer_before / buffer_after） | ⚠️ 部分实现 | 字段已建模，但 AI 冲突检测逻辑主要依赖 Gemini 判断，规则层未完整实现 buffer 计算 |
| Reminder 提醒 WebSocket 实时推送到前端展示 | ⚠️ 部分实现 | 提醒已写入数据库，WebSocket 快照中包含提醒列表，但前端 Reminders 标签仅展示列表，无浏览器桌面通知弹窗 |
| Google Calendar 双向同步（本地→Google 写回） | ⚠️ 部分实现 | 当前仅实现 Google→本地单向导入；本地创建事件写回 Google Calendar 的逻辑已有 `google_calendar.py` 工具但未在 Event 创建流程中激活 |
| 助手 Inbox 主动生成（冲突/任务跟进提醒） | ⚠️ 部分实现 | Inbox 框架完整，但 AI 主动生成 Inbox 条目的触发逻辑依赖 Gemini 在对话时写入，无独立后台主动生成任务跟进 |

### 未实现（设计书规划但当前版本缺失）

| 设计书要求 | 状态 | 后续计划 |
|---|---|---|
| Capacitor 移动端封装（Android App） | ❌ 未实现 | 当前移动端为响应式网页，后续可接入 Capacitor 封装 APK |
| Tauri 2 桌面端封装（Windows EXE） | ❌ 未实现 | 前端框架已为 Tauri 兼容，后续添加 `src-tauri/` 配置即可 |
| 桌面系统通知（Tauri Notification 插件） | ❌ 未实现 | 依赖 Tauri 封装完成后实现 |
| 语音输入/输出插件接口预留 | ❌ 未实现 | `inputAdapters/` / `outputAdapters/` 目录结构未建立 |
| 每 1 分钟扫描近 30 分钟事件的高频提醒任务 | ❌ 未实现 | 当前提醒扫描频率由 Celery Beat 控制，频率配置较低，需调整 beat_schedule |
| 建议式重排（冲突时推荐 1-3 个替代时间） | ❌ 未实现 | 当前 AI 会提示冲突但不自动给出替代时段选项 |
| WebSocket `/ws/assistant` 流式输出 | ❌ 未实现 | 当前助手回复为 REST 请求同步等待，无流式输出体验 |

### 后续开发优先级建议

1. **P0 — 答辩前必须完成**
   - 调整 Celery Beat 频率（每 1 分钟扫描提醒）
   - 完善冲突检测的 buffer 规则计算
   - 前端添加提醒弹窗（浏览器 Notification API 或页面 Toast）

2. **P1 — 功能完善**
   - 本地事件写回 Google Calendar（双向同步）
   - 后台主动任务跟进 Inbox 生成（独立 Celery 任务）
   - 冲突时推荐替代时段

3. **P2 — 跨平台封装**
   - Capacitor 打包 Android APK
   - Tauri 2 打包 Windows EXE + 桌面通知

4. **P3 — 体验增强**
   - WebSocket 流式输出 AI 回复
   - 语音输入适配器接口
