# 项目技术规格书：基于多Agent协同的智能个人事务助理系统 (MA-IPAAS)

## 1. 项目概述

**项目名称**：MA-IPAAS (Multi-Agent Intelligent Personal Affairs Assistant System)

**核心理念**：构建一个不仅仅是记录日程，而是能够像真人助理一样具备思考、规划、预判能力的智能系统。系统通过多个专职 Agent 的协作，实现从自然语言指令到分钟级日程安排的自动化闭环。

**部署目标**：
- **后端**：容器化部署 (Docker)，兼容 Windows/Linux 服务器及云端环境。
- **前端**：一套代码 (Vue 3)，通过响应式设计适配 PC/平板/手机，支持通过容器壳 (Capacitor) 打包为 Android/Windows 原生应用。

------

## 2. 核心功能与 Agent 架构

系统采用 **Controller-Worker** 多智能体协作模式。

### 2.1 智能体 (Agents) 定义

1. **🤖 主控 Agent (Master Agent)**
   - **职责**：用户意图识别、任务分发、最终回复生成。
   - **输入**：自然语言（文本/语音转文字）。
   - **行为**：判断用户是想“查询日程”、“新增日程”还是“闲聊”，并将任务派发给下级 Agent。

2. **📅 调度 Agent (Scheduler Agent)**
   - **职责**：时间管理专家。
   - **能力**：
     - **冲突检测**：检测新事件是否与现有事件重叠。
     - **动态缓冲**：根据事件类型自动添加缓冲时间（如：会议前预留 5 分钟，外出前预留 30 分钟）。
     - **碎片填充**：识别日程空隙，建议插入待办事项池中的短任务。

3. **🚗 导航 Agent (Navigator Agent)**
   - **职责**：地理位置与通勤保障。
   - **能力**：
     - **路径规划**：调用地图 API 计算 A 点到 B 点的通勤时长。
     - **路况监控**：在日程开始前实时检查拥堵情况，动态调整“出发时间”。

4. **📝 秘书 Agent (Clerk Agent)**
   - **职责**：信息检索与记录。
   - **能力**：管理待办事项 (Backlog)，记录会议纪要，查询天气/资讯。

### 2.2 核心业务流程

1. **智能排程**：用户输入 -> Master 识别 -> Navigator 计算路程 -> Scheduler 寻找空档 -> 写入数据库 -> Master 反馈结果。
2. **弹性调整**：突发事件导致延误 -> Scheduler 自动推迟后续非固定任务 -> Navigator 重新计算后续行程交通时间 -> 推送变更通知。

------

## 3. 技术栈选型

### 3.1 后端 (Server & AI)

- **语言**：Python 3.11+
- **Web 框架**：Django 4.2+ (配合 Django REST Framework)
- **异步通讯**：Django Channels (WebSocket，用于实时 Agent 交互)
- **任务队列**：Celery + Redis (处理耗时的 AI 推理和定时任务)
- **AI 编排**：LangChain (Python 版)
- **数据库**：MySQL 8.0 (主数据), Redis (缓存与消息代理)
- **模型网关 (LLM Gateway)**：**One API**
  - **核心作用**：统一管理 DeepSeek, OpenAI, Claude, Gemini, 阿里通义, 讯飞星火等主流模型渠道。
  - **优势**：提供标准的 OpenAI 兼容接口，支持 Key 轮询、负载均衡、失败重试与额度管理。后端只需对接 One API 一个接口即可切换不同模型。
- **外部 API**：
  - Map：高德地图 API / 腾讯地图 API (Web 服务端)

### 3.2 前端 (Client)

- **框架**：Vue 3 (Composition API) + Vite
- **UI 组件库**：Naive UI (PC端适配好) 或 Vant UI (移动端优先)，推荐使用 **TailwindCSS / UnoCSS** 实现手写响应式布局。
- **状态管理**：Pinia
- **网络层**：Axios (HTTP), Native WebSocket API
- **跨端打包**：Capacitor.js (将 Web 打包为 Android APK / Windows EXE)

### 3.3 基础设施 (DevOps)

- **容器化**：Docker, Docker Compose
- **LLM 管理服务**：One API (Docker 部署, 默认端口 3000)
- **反向代理**：Nginx (可选，生产环境使用)

------

## 4. 数据库设计规范 (MySQL)

### 4.1 用户与配置表 (`tb_user_profile`)
- `id`: INT, PK
- `preferences`: JSON (存储用户偏好，如“不喜欢早起”、“通勤偏好地铁”)
- `home_location`: VARCHAR (家庭地址坐标)
- `work_location`: VARCHAR (公司地址坐标)

### 4.2 日程事件表 (`tb_schedule_events`)
- `id`: UUID, PK
- `title`: VARCHAR (事件标题)
- `start_time`: DATETIME (开始时间)
- `end_time`: DATETIME (结束时间)
- `location_name`: VARCHAR (地点名)
- `location_coords`: VARCHAR (经纬度 "lat,lng")
- `transport_mode`: ENUM ('taxi', 'public', 'drive', 'walk')
- `transport_duration`: INT (预计通勤分钟数)
- `buffer_pre`: INT (前置缓冲分钟)
- `is_fixed`: BOOLEAN (是否由于外部因素不可更改，如飞机起飞)
- `status`: ENUM ('planned', 'ongoing', 'completed', 'cancelled')

### 4.3 待办事项池 (`tb_backlog`)
- `id`: UUID, PK
- `content`: TEXT (内容)
- `estimated_duration`: INT (预计耗时分钟)
- `priority`: INT (优先级)
- `deadline`: DATETIME (截止日期)

------

## 5. 详细实现路径 (Step-by-Step)

### 第一阶段：基础设施搭建 (Docker First)
**目标**：在任何机器上一键启动开发环境。

1. 创建项目根目录 `MA-IPAAS/`。
2. 编写 `docker-compose.yml`：
   - **Service `db`**: MySQL 8.0，映射端口 3306，挂载数据卷 `./data/mysql:/var/lib/mysql`。
   - **Service `redis`**: Redis 7，映射端口 6379。
   - **Service `one-api`**: LLM 统一网关。
     - 镜像: `justsong/one-api` (或 `ghcr.io/songquanpeng/one-api`)
     - 端口: 映射 3000:3000
     - 环境变量: `TZ=Asia/Shanghai`
     - 数据卷: `./data/one-api:/data`
     - (可选) 配置 `SQL_DSN` 连接到 `db` 服务以持久化数据到 MySQL。
   - **Service `backend`**: 基于 `Dockerfile` 构建。映射端口 8000。
   - **Service `celery_worker`**: 复用 backend 镜像，运行 celery worker 指令。
3. 编写后端 `Dockerfile`：
   - Base Image: `python:3.10-slim`
   - 安装依赖：`django`, `djangorestframework`, `mysqlclient`, `channels`, `daphne`, `langchain`, `openai` (调用 One API 用), `celery`, `redis`.
4. **验证**：运行 `docker-compose up -d`，确保所有服务状态为 Up，并能访问 `http://localhost:3000` 进入 One API 管理界面。

### 第二阶段：后端核心业务开发
**目标**：建立数据库模型与基础 API。

1. **Django 初始化**：
   - 创建 App: `core`, `scheduler`, `agent_engine`.
2. **Model 编写**：根据第 4 节设计数据库模型，并执行 Migrate。
3. **API 开发 (DRF)**：
   - `GET /api/events/`: 获取指定日期范围的日程。
   - `POST /api/events/`: 手动创建日程。
4. **WebSocket 配置 (Channels)**：
   - 配置 `asgi.py`。
   - 建立 Consumer `ChatConsumer`，处理路径 `ws/chat/`。
   - 实现基础的 Echo 功能（发送什么回复什么），验证连接。

### 第三阶段：Agent 引擎开发 (LangChain 集成)
**目标**：让系统“听懂”人话并操作数据库。

1. **One API 配置**：
   - 在 One API 后台添加所需的模型渠道 (如 DeepSeek, OpenAI)。
   - 创建一个新的令牌 (Token)，用于后端服务调用。
2. **工具集 (Tools) 开发**：
   - 封装 Python 函数为 LangChain Tool：
     - `tool_check_availability(start, end)`: 查询数据库空闲。
     - `tool_add_event(...)`: 写入数据库。
     - `tool_get_traffic(origin, dest)`: 调用高德 API 返回时长。
3. **Agent 编排**：
   - 使用 `langchain` 连接 One API。
     ```python
     ChatOpenAI(
         openai_api_base="http://one-api:3000/v1",
         openai_api_key="sk-..." # One API 生成的令牌
     )
     ```
   - Prompt Engineering：设定 System Message，告知 Agent 当前时间、用户偏好。
4. **异步连接**：
   - 在 Django View/Consumer 中接收用户消息 -> 丢给 Celery 任务 -> Celery 运行 Agent -> 结果通过 `channel_layer` 推送回 WebSocket。

### 第四阶段：前端开发 (响应式 & 跨端)
**目标**：可视化交互界面。

1. **项目初始化**：`npm create vite@latest` (Vue 3 + TS).
2. **布局实现**：
   - 使用 CSS Grid/Flex。
   - **Mobile View (<768px)**: 底部 TabBar (日程 | 助手 | 我的)。
   - **Desktop View (>=768px)**: 侧边 Sidebar，左侧日历面板，右侧悬浮聊天窗。
3. **日历组件**：集成 `FullCalendar` 或手写时间轴组件，从后端 API 拉取数据渲染。
4. **聊天组件**：类似微信/ChatGPT 的界面，连接 WebSocket，实时流式渲染 Agent 回复。

### 第五阶段：打包与发布
**目标**：生成 APK 和 Docker 镜像。

1. **Docker 生产配置**：
   - 配置 Nginx 容器作为反向代理，处理静态文件和 API 转发 (包括转发 `/v1` 到 One API)。
2. **Capacitor 集成**：
   - `npm install @capacitor/core @capacitor/cli @capacitor/android`
   - `npx cap add android`
   - 配置 `capacitor.config.json` 指向开发电脑 IP (调试) 或 生产服务器域名 (发布)。
   - 构建 APK。
