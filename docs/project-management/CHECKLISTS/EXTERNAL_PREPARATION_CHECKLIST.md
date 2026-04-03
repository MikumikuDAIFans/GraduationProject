# 外部依赖与人工准备清单

## 1. 文档目的

本清单用于在正式写代码前，一次性梳理这套系统所需的所有外部服务、API Key、第三方账号、OAuth 配置、打包环境和可选 MCP/插件位。

目标是让你先把需要人工准备的东西准备齐，后面实现时尽量不停下来反复补环境。

## 2. 总览

按优先级分为三类：

1. **必须准备**
2. **建议准备**
3. **可选准备**

## 3. 必须准备

这些是你做出可运行系统最核心的一批。

## 3.1 大模型访问能力

### 用途

1. 自然语言意图识别
2. 槽位抽取
3. 建议生成
4. 助手回复生成

### 你需要准备

1. 一个可稳定调用的 Gemini API Key
2. 一个 Google 账号

### 当前正式方案

当前模型服务默认采用：

1. `Google Gemini`

### 建议环境变量

1. `GEMINI_API_KEY`
2. `GEMINI_MODEL`

### 当前建议

当前最推荐直接使用：

1. `Gemini API`
2. 一个稳定的非预览模型，如 `models/gemini-2.5-flash`

## 3.2 数据库与缓存

### 用途

1. 存储事件
2. 存储任务
3. 存储提醒
4. 支撑 Celery 队列

### 你需要准备

1. `SQLite`
2. `Redis`

### 建议准备项

1. SQLite 数据库文件路径
2. Redis 连接地址

### 建议环境变量

1. `SQLITE_DB_PATH`
2. `REDIS_URL`

### 当前建议

建议直接采用本地数据库文件，例如：

1. `SQLITE_DB_PATH=./data/app.db`

## 3.3 地图服务

### 用途

1. 通勤时间估算
2. 出发提醒
3. 不同地点事件的冲突计算

### 推荐准备

二选一即可：

1. 高德地图开放平台
2. 腾讯地图开放平台

### 你需要准备

1. Web 服务 API Key
2. 调用白名单或安全配置

### 建议环境变量

1. `MAP_PROVIDER`
2. `MAP_API_KEY`

### 当前建议

优先建议高德地图，因为中文场景、国内路径规划和地理服务更贴近你的项目。

## 3.4 前端封装与构建环境

### 用途

1. 打包 Web 前端
2. 封装 Android App
3. 封装 Windows EXE

### 你需要准备

#### Web 前端

1. `Node.js`
2. `pnpm` 或 `npm`

#### Android 封装

1. `Android Studio`
2. Android SDK
3. JDK

#### Windows EXE 封装

1. `Rust` 工具链
2. `Tauri 2` 运行所需环境

### 建议版本基线

1. `Node.js 20+`
2. `pnpm` 最新稳定版
3. `Python 3.11`
4. `Rust stable`
5. `Android Studio` 最新稳定版

## 4. 建议准备

这些不是 MVP 必需，但你大概率会用到，提前准备会省很多时间。

## 4.1 天气服务

### 用途

1. 户外事件建议
2. 出发提醒文案增强
3. 风险提示

### 当前正式方案

当前天气服务默认采用：

1. `和风天气`

### 建议环境变量

1. `WEATHER_PROVIDER`
2. `QWEATHER_API_KEY`
3. `QWEATHER_API_HOST`

### 当前建议

建议统一写成：

1. `WEATHER_PROVIDER=qweather`
2. `QWEATHER_API_KEY=你的凭据`
3. `QWEATHER_API_HOST=你的专属 Host 或默认 Host`

## 4.2 Google Calendar 同步

### 用途

1. 将系统日程同步到外部日历
2. 作为演示亮点

### 是否必须

是。

### 当前决策

当前项目正式启用 Google Calendar 同步，不再作为可选增强项。

### 当前同步策略

当前正式采用：

1. `SQLite` 为主数据源
2. `Google Calendar` 为镜像
3. 不做双向强一致同步
4. 外部事件导入采用手动同步，不做后台定时自动导入

### 如果要做，你需要准备

1. Google Cloud 项目
2. Google Calendar API 启用
3. OAuth Client ID
4. OAuth Client Secret
5. 授权回调地址

### 建议环境变量

1. `GOOGLE_CLIENT_ID`
2. `GOOGLE_CLIENT_SECRET`
3. `GOOGLE_REDIRECT_URI`

### 说明

这里的 `GOOGLE_CLIENT_ID` 和 `GOOGLE_CLIENT_SECRET`：

1. 不是 Gemini API Key
2. 它们是 Google OAuth 凭据
3. 只有在你要接入 Google Calendar 同步或 Google 账号授权登录时才需要

## 4.3 站内通知与桌面通知

### 用途

1. Web 页面内提醒
2. 桌面端通知

### 你需要准备

初版只做站内通知时：

1. 不需要额外第三方账号

如果要做桌面系统通知：

1. 需要确认 `Tauri` 侧通知权限和本地系统配置

### 当前建议

当前项目正式采用：

1. 站内提醒
2. WebSocket 实时推送
3. 桌面系统通知

## 4.4 Docker 运行基线

### 当前正式方案

当前项目约定：

1. 所有后端均运行在 Docker 容器中
2. `Redis` 与 `Celery` 统一 Docker 化运行
3. `SQLite` 使用挂载数据文件方式持久化

### 你需要准备

1. `Docker Desktop`
2. 可正常使用的 Docker Compose 环境

## 4.5 日志与观测

### 用途

1. 调试 Assistant 工作流
2. 调试提醒触发
3. 展示系统执行链路

### 可选方案

1. 本地日志 + 数据库日志表
2. LangSmith
3. Sentry

### 当前建议

初版不强依赖第三方观测平台，只做：

1. 应用日志
2. `schedule_change_logs`
3. Assistant 会话日志

## 5. 可选准备

这些不是现在必须，但未来你可能会接。

## 5.1 语音输入插件

### 用途

1. 用户语音输入

### 你未来可能需要准备

1. 语音识别服务 Key
2. 麦克风权限配置
3. 移动端录音权限

### 建议未来环境变量

1. `VOICE_INPUT_PROVIDER`
2. `VOICE_INPUT_API_KEY`

## 5.2 语音输出插件

### 用途

1. 模型语音播报

### 你未来可能需要准备

1. TTS 服务 Key
2. 音频输出适配

### 建议未来环境变量

1. `VOICE_OUTPUT_PROVIDER`
2. `VOICE_OUTPUT_API_KEY`

## 5.3 推送通知服务

### 用途

1. Android 推送
2. 更强的主动提醒

### 未来可能准备

1. Firebase 项目
2. FCM 配置

## 5.4 MCP 服务

### 结论

**当前系统运行时不强依赖 MCP。**

也就是说：

1. 生产系统不需要先搭 MCP 才能工作
2. 当前架构中 MCP 更适合作为开发期或研究期扩展

### 如果未来你想扩展

可选 MCP 服务包括：

1. Calendar MCP
2. Sequential Thinking MCP
3. Browser MCP

### 当前建议

MCP 先不列入必须准备项，只保留为未来可选扩展。

## 6. 推荐的环境变量总表

建议你后续统一整理到 `.env` 中。

### 必填

1. `GEMINI_API_KEY`
2. `GEMINI_MODEL`
3. `SQLITE_DB_PATH`
4. `REDIS_URL`
5. `MAP_PROVIDER`
6. `MAP_API_KEY`

### 建议填

1. `WEATHER_PROVIDER`
2. `QWEATHER_API_KEY`
3. `QWEATHER_API_HOST`
3. `GOOGLE_CLIENT_ID`
4. `GOOGLE_CLIENT_SECRET`
5. `GOOGLE_REDIRECT_URI`

### 未来插件预留

1. `VOICE_INPUT_PROVIDER`
2. `VOICE_INPUT_API_KEY`
3. `VOICE_OUTPUT_PROVIDER`
4. `VOICE_OUTPUT_API_KEY`

## 7. 建议你先人工准备的清单

如果按投入产出比排序，我建议你先准备这些：

1. 一个稳定可用的 `Gemini API Key`
2. `SQLite` 数据文件目录
3. `Redis`
4. 一个高德地图 API Key
5. `QWEATHER_API_KEY` 与 `QWEATHER_API_HOST`
6. Google Calendar OAuth 配置
7. Node.js、pnpm、Python 3.11
8. Android Studio
9. Rust stable

## 8. 当前最推荐的准备组合

如果你想先最小成本开工，我建议：

1. `Gemini API`
2. `SQLite + Redis`
3. `高德地图 API`
4. `和风天气 API`
5. `Google Calendar OAuth`
6. `Vue 3 + Vite`
7. `Capacitor + Tauri 2`
8. 暂时不接 MCP
9. 暂时不接语音服务

这套组合最符合你当前阶段：

1. 先把系统做出来
2. 先把主动提醒和时间安排跑通
3. 后续再逐项加外部增强
