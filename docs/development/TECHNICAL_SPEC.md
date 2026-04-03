# 个人事务助手系统详细技术方案 V2

## 1. 方案定位

本方案完全以“可落地”为优先目标，不沿用旧版多 Agent 概念设计，而是以现成开源项目的实现方式为主，尽量复用成熟代码、目录结构和交互模式，减少重复造轮子。

系统最终定位为：

**一个面向个人时间管理的智能事务助手系统，以日程、待办、提醒和行动建议为核心对象，支持自然语言交互、日程规划、日程建议、冲突处理和主动提醒。**

本系统最重要的产品特征不是聊天，而是：

1. 能理解用户的时间安排需求
2. 能给出合理的日程建议
3. 能识别并处理冲突
4. 能在合适的时机主动提醒和建议用户行动

## 2. 设计原则

### 2.1 优先复用，不重复造轮子

优先复用以下开源仓库中的成熟实现：

1. [reference/calendar-ai](/E:/GraduationProject/reference/calendar-ai)
2. [reference/calendar-mcp](/E:/GraduationProject/reference/calendar-mcp)
3. [reference/todo-work-agent](/E:/GraduationProject/reference/todo-work-agent)
4. [reference/spec-to-agents](/E:/GraduationProject/reference/spec-to-agents)

其他仓库作为补充参考：

1. [reference/langgraph-supervisor-py](/E:/GraduationProject/reference/langgraph-supervisor-py)
2. [reference/Langgraph-agents](/E:/GraduationProject/reference/Langgraph-agents)
3. [reference/Multi-Agent-AI-Assistant](/E:/GraduationProject/reference/Multi-Agent-AI-Assistant)
4. [reference/atom](/E:/GraduationProject/reference/atom)

### 2.2 规则优先，AI 辅助

本系统涉及时间、冲突、提醒、出发时机等强约束场景，因此核心调度逻辑不能完全依赖 LLM 自由发挥。

建议采用：

1. 规则引擎负责冲突检测、空档计算、提醒触发
2. LLM 负责意图识别、槽位抽取、自然语言解释、建议生成

当前默认模型服务选型为：

1. `Google Gemini`

### 2.3 先单工作流，后多 Agent 扩展

初版系统不强依赖复杂多 Agent 框架。

推荐先做：

1. 一个主 Assistant 工作流
2. 一组独立工具服务
3. 一个后台触发与提醒引擎

后续如果需要，可在不推翻架构的情况下演进到 Supervisor + 多角色协作。

### 2.4 主动提醒能力必须是系统内建能力

主动提醒不是“以后再加”的 UI 功能，而是系统核心能力之一。因此必须在数据模型、后台调度、通知渠道、前端提醒区中同步设计。

## 3. 开源仓库复用策略

## 3.1 前端复用策略

主要参考 [reference/calendar-ai](/E:/GraduationProject/reference/calendar-ai)。

建议直接复用或重写适配以下思路：

1. `FullCalendar` 驱动的日历可视化
2. `use-events.tsx` 这种“按日期范围拉取事件并缓存”的状态管理方式
3. `chat.tsx` 这种“助手与日历联动”的交互模式
4. `/api/calendar/events` 这种标准化的日历事件接口形式

前端不建议从零重新设计完整页面结构，而是应采用：

1. 日历工作区
2. 助手工作区
3. 提醒与建议工作区

### 适合直接借鉴的内容

1. 事件拉取缓存逻辑
2. FullCalendar 事件数据结构
3. 助手面板的会话流
4. 前端 API 调用方式

### 需要改造的内容

1. 将 Google Calendar 强依赖改为“本地事件表 + 可选外部日历同步”
2. 将原项目营销页和认证部分剔除
3. 在页面中新增冲突高亮、建议插入区和提醒面板

当前项目决策已升级为：

1. Google Calendar 同步纳入正式实现范围
2. 同步方式正式定为“本地 SQLite 为主，Google Calendar 为镜像”的单向主从方案

## 3.2 工具层复用策略

主要参考 [reference/calendar-mcp](/E:/GraduationProject/reference/calendar-mcp) 和 [reference/todo-work-agent](/E:/GraduationProject/reference/todo-work-agent)。

建议复用的核心思想是：

**把所有外部能力封装为稳定工具模块，而不是散落在对话逻辑里。**

适合直接借鉴：

1. `calendar_actions.py` 这种清晰的日历操作封装方式
2. Google Calendar OAuth 与 API 调用逻辑
3. `todo-work-agent/tools/google_calendar.py` 的事件创建与提醒写法
4. `tools/` 目录单独管理外部能力

### 推荐工具模块

1. `tools/calendar/`
2. `tools/tasks/`
3. `tools/map/`
4. `tools/weather/`
5. `tools/notification/`

## 3.3 后端工作流复用策略

主要参考 [reference/todo-work-agent](/E:/GraduationProject/reference/todo-work-agent) 和 [reference/spec-to-agents](/E:/GraduationProject/reference/spec-to-agents)。

推荐吸收的做法：

1. `agent/graph.py` 的状态图工作流结构
2. `agent/nodes.py` 的“节点 + 路由函数”写法
3. `database/models.py` 的 Repository 模式
4. `api/routes + api/services + database + tools` 的分层方式
5. `spec-to-agents` 中 `agents/ prompts/ tools/ workflow/ utils/` 的清晰目录

初版不建议直接照搬 `spec-to-agents` 的完整多 Agent 工作流，但非常适合照搬其项目结构思想。

## 3.4 许可证与复用注意事项

直接复用代码前必须逐个确认原仓库许可证。

当前已明确观察到：

1. `atom` README 标注 AGPL
2. `calendar-mcp` README 标注 AGPL + 商业许可
3. `calendar-ai` README 标注 MIT
4. `spec-to-agents` 仓库存在 `LICENSE` 文件

因此建议：

1. 前端优先参考和改写 `calendar-ai`
2. 思路可广泛借鉴所有项目
3. 直接复制代码时优先选择许可证清晰且对毕业设计友好的部分
4. 对许可证不清晰的仓库，优先借思路，不直接大段复制

## 4. 系统总体架构

## 4.1 总体分层

系统采用六层结构：

1. **前端交互层**
2. **接入与接口层**
3. **Assistant 工作流层**
4. **调度与建议引擎层**
5. **工具层**
6. **数据与基础设施层**

## 4.2 各层职责

### 前端交互层

负责：

1. 日历可视化
2. 助手对话
3. 提醒与建议展示
4. 事件编辑和确认

### 接入与接口层

负责：

1. REST API
2. WebSocket 推送
3. 用户鉴权
4. 外部插件入口预留

### Assistant 工作流层

负责：

1. 用户意图识别
2. 槽位抽取
3. 调用调度引擎与工具层
4. 组织最终回复

### 调度与建议引擎层

负责：

1. 冲突检测
2. 空闲时段搜索
3. 任务插空
4. 出发时间建议
5. 主动提醒触发

### 工具层

负责：

1. 日历事件 CRUD
2. 待办 CRUD
3. 地图通勤估算
4. 天气上下文
5. 通知分发

### 数据与基础设施层

负责：

1. SQLite 数据存储
2. Redis 缓存与队列
3. Celery 定时任务
4. 对话状态持久化
5. 系统审计日志

## 5. 前端详细设计

## 5.1 最终技术选型

前端正式定稿为：

1. `Vue 3`
2. `TypeScript`
3. `Vite`
4. `TailwindCSS`
5. `FullCalendar`
6. `Pinia`
7. `Axios`
8. `Capacitor`
9. `Tauri 2`

### 选型结论

本项目前端采用：

**`Vue 3 + TypeScript + Vite + TailwindCSS + FullCalendar + Pinia`**

封装路线采用：

1. **移动端封装：`Capacitor`**
2. **桌面端封装：`Tauri 2`**

### 为什么这样选

你的前端目标是：

1. 一套网页优先开发
2. 后续封装成手机 App
3. 后续封装成桌面 EXE
4. 兼顾电脑和手机端流畅响应

在这个目标下，不建议把前端主技术栈定为 `Next.js`，因为：

1. 你的核心需求不是服务端渲染
2. 你更需要轻量、快速构建和跨端封装
3. `Vite` 对前端单页应用和组件开发更直接
4. `Vue 3 + Vite` 更适合后续同时接入 `Capacitor` 和 `Tauri`

### 对开源参考仓库的复用方式

虽然 [reference/calendar-ai](/E:/GraduationProject/reference/calendar-ai) 使用的是 Next.js，但它仍然是前端设计的重要参考来源。

建议复用的是：

1. 页面布局思路
2. 日历与助手联动方式
3. 事件缓存和区间拉取逻辑
4. 聊天区的交互方式

建议不直接照搬的是：

1. Next.js 路由体系
2. NextAuth 鉴权体系
3. 营销页和认证页

### 这套选型的优点

1. Web 首发最轻量
2. 手机端封装路线清晰
3. 桌面端打包体积和资源占用相对更优
4. 后期可保留 PWA、App、桌面三种分发模式
5. 适合逐步接入语音插件

## 5.2 前端封装策略

### 5.2.1 Web 主体

主前端以浏览器 Web 应用为唯一事实来源。

也就是说：

1. 页面逻辑先做成标准 Web 应用
2. 移动端和桌面端都只是“壳”
3. 不在移动端和桌面端分别维护独立业务前端

### 5.2.2 移动端封装

推荐使用 `Capacitor`：

1. 适合把现有 Web 前端封装成 Android App
2. 后续如果需要，也能延伸到 iOS
3. 便于后续接入移动端原生能力
4. 适合未来接入语音输入、通知、设备权限

### 5.2.3 桌面端封装

推荐使用 `Tauri 2`：

1. 适合将同一套前端封装成 Windows EXE
2. 资源占用比 Electron 更轻
3. 更适合你的“流畅响应”目标
4. 后期也可扩展到 macOS/Linux

### 5.2.4 为什么不优先用 Electron

`Electron` 成熟，但对你当前项目并不是最优：

1. 打包体积偏大
2. 内存占用更高
3. 你当前场景并不需要它那套更重的桌面运行时能力

所以桌面端优先建议 `Tauri 2`，而不是 `Electron`。

## 5.3 页面结构

推荐做成一个主工作台页面，不要拆成大量功能页。

### 页面布局

1. 左侧：日历与日程时间轴
2. 右侧上半区：助手对话区
3. 右侧下半区：提醒与建议区

### 三个核心区块

#### A. 日历区

展示：

1. 日视图
2. 周视图
3. 事件详情弹层
4. 冲突高亮
5. 推荐插入时段

#### B. 助手区

支持：

1. 自然语言输入
2. 常见快捷指令
3. 对话式创建事件
4. 查询今日/明日日程
5. 确认或拒绝系统建议

#### C. 提醒区

展示：

1. 即将发生的事件
2. 出发提醒
3. 冲突预警
4. 空档建议
5. 今日时间安排建议

## 5.4 前端状态设计

建议拆成以下 store：

1. `useEventsStore`
2. `useAssistantStore`
3. `useReminderStore`
4. `useSuggestionStore`

### `useEventsStore`

参考 `calendar-ai/src/hooks/use-events.tsx` 的缓存设计，保存：

1. 当前事件列表
2. 当前视图时间范围
3. 已缓存范围
4. 重新拉取函数

### `useAssistantStore`

保存：

1. 消息列表
2. 当前会话 ID
3. 当前输入内容
4. 执行中状态

### `useReminderStore`

保存：

1. 待提醒项目
2. 已读/未读状态
3. 推送时间
4. 提醒类型

## 5.5 前端接口设计

推荐接口：

1. `GET /api/events`
2. `POST /api/events`
3. `PUT /api/events/{id}`
4. `DELETE /api/events/{id}`
5. `GET /api/tasks`
6. `POST /api/tasks`
7. `PATCH /api/tasks/{id}`
8. `POST /api/assistant/message`
9. `GET /api/reminders`
10. `GET /api/suggestions`

### WebSocket 通道

建议：

1. `/ws/assistant`
2. `/ws/notifications`

分别用于：

1. 助手回复流式输出
2. 实时提醒和主动建议推送

## 5.6 语音插件接口预留

当前不做实时语音实现，但必须预留接口边界。

建议前端预留：

1. `inputAdapters/textInput.ts`
2. `inputAdapters/voiceInput.ts`
3. `outputAdapters/textOutput.ts`
4. `outputAdapters/voiceOutput.ts`

当前默认启用文本输入输出，语音插件后续接入时不需要推翻 UI 主结构。

## 5.7 推荐前端目录

```text
frontend/
  src/
    api/
    assets/
    components/
      calendar/
      assistant/
      reminders/
      common/
    layouts/
    pages/
      workspace/
      settings/
    router/
    stores/
    composables/
    inputAdapters/
    outputAdapters/
    utils/
    types/
  public/
  capacitor/
  src-tauri/
```

### 目录说明

1. `components/calendar/` 放日历和事件组件
2. `components/assistant/` 放助手对话区
3. `components/reminders/` 放提醒与建议区
4. `stores/` 放 `Pinia` 状态管理
5. `inputAdapters/` 与 `outputAdapters/` 为未来语音插件预留
6. `capacitor/` 放移动端壳相关配置
7. `src-tauri/` 放桌面端壳相关配置

## 6. 后端详细设计

## 6.1 技术选型

推荐：

1. `Python 3.11`
2. `FastAPI`
3. `Pydantic`
4. `SQLAlchemy 2`
5. `Alembic`
6. `Celery`
7. `Redis`
8. `SQLite`
9. `Uvicorn`

### 为什么正式改为 FastAPI

1. 项目本质上是 `API + WebSocket + 调度引擎 + 工具调用`，而不是传统后台站点
2. 参考仓库中 [reference/todo-work-agent](/E:/GraduationProject/reference/todo-work-agent) 与 [reference/calendar-mcp](/E:/GraduationProject/reference/calendar-mcp) 都更接近 FastAPI 风格
3. FastAPI 更适合类型驱动的接口设计、自动文档和轻量服务化拆分
4. WebSocket、异步接口和工具服务接入都更直接
5. Celery + Redis 仍然可以无缝保留
6. SQLite 对个人事务助手的本地单用户场景已经足够，能显著降低部署复杂度

## 6.2 推荐项目目录

建议采用融合 `todo-work-agent` 与 `spec-to-agents` 的目录：

```text
backend/
  api/
    main.py
    routes/
    schemas/
    dependencies/
  workflow/
    graph/
    nodes/
    prompts/
    schemas/
  tools/
    calendar/
    tasks/
    map/
    weather/
    notification/
  repositories/
  services/
  jobs/
  config/
  tests/
```

### 目录职责

1. `api/` 放 FastAPI 入口、路由、Schema 和依赖注入
2. `workflow/` 放 Assistant 工作流逻辑
3. `tools/` 放工具能力
4. `repositories/` 放数据访问
5. `services/` 放业务服务
6. `jobs/` 放 Celery 任务

## 6.3 核心模块

### A. Assistant Service

负责：

1. 处理用户消息
2. 识别意图
3. 抽取时间、地点、操作类型
4. 调用调度引擎和工具层
5. 输出自然语言答复

### B. Schedule Engine

负责：

1. 事件冲突检测
2. 空闲时段搜索
3. 柔性任务插入
4. 出发时间建议
5. 自动提醒计划生成

### C. Reminder Engine

负责：

1. 定时扫描未来事件
2. 生成提醒任务
3. 触发主动建议
4. 处理延误或上下文变化后的重新提醒

### D. Calendar Sync Service

负责：

1. 本地事件表管理
2. Google Calendar 同步
3. 外部日历事件映射

### Google Calendar 同步原则

当前正式同步策略为：

1. `SQLite` 是唯一主数据源
2. `Google Calendar` 是外部镜像
3. 系统内创建、修改、删除事件时，同步写入 Google Calendar
4. Google Calendar 外部改动不作为主写入口
5. 如需导入外部事件，采用“手动同步拉取导入 + 标记来源”的方式处理
6. 暂不实现后台定时自动导入

### E. Notification Service

负责：

1. WebSocket 推送
2. 站内提醒
3. 桌面系统通知
4. 后续插件式通知扩展

## 6.4 Assistant 工作流设计

参考 `todo-work-agent/agent/graph.py` 和 `agent/nodes.py`。

推荐将助手工作流建成 5 个节点：

1. `parse_intent_node`
2. `collect_context_node`
3. `schedule_decision_node`
4. `tool_execute_node`
5. `response_render_node`

### 节点说明

#### `parse_intent_node`

负责：

1. 判断是查询、创建、修改、取消、建议、提醒解释
2. 提取时间范围和地点

#### `collect_context_node`

负责：

1. 拉取已有事件
2. 拉取任务池
3. 拉取用户偏好
4. 拉取必要天气和通勤信息

#### `schedule_decision_node`

负责：

1. 判断是否存在冲突
2. 判断是否需要推荐其他时间
3. 判断是否需要创建提醒
4. 判断是否需要插入待办

#### `tool_execute_node`

负责：

1. 创建/修改事件
2. 写入待办
3. 注册提醒
4. 写入建议日志

#### `response_render_node`

负责：

1. 输出简洁结果
2. 输出冲突说明
3. 输出下一步建议

## 6.5 为什么初版不急着上多 Agent

因为你的核心竞争力不在“有几个 Agent”，而在于：

1. 日程理解
2. 时间建议
3. 冲突处理
4. 主动提醒

这四件事先用单工作流做稳，再决定是否拆成多个 Agent，更符合毕业设计节奏。

## 7. 数据库详细设计

## 7.1 设计原则

数据库部分尽量避免自己从零发明复杂结构，建议直接采用：

1. `todo-work-agent` 的 Repository 风格
2. 传统业务表 + 日志表 + 定时提醒表 的常规设计

不建议一上来设计过多抽象表。

当前数据库正式定稿为 `SQLite`，原因如下：

1. 当前系统以个人事务管理为主，数据规模较小
2. SQLite 足以支撑单用户或轻量原型
3. 可明显降低本地开发与部署复杂度
4. 更适合毕业设计阶段快速落地和演示

需要额外说明：

1. `SQLite` 只承担业务数据存储
2. `Redis` 只承担队列、缓存和实时通信支撑
3. 二者职责不重叠
4. `SQLite` 数据文件通过挂载目录或数据卷持久化

## 7.2 核心表

建议保留 7 张核心表：

1. `user_profile`
2. `events`
3. `tasks`
4. `reminders`
5. `assistant_sessions`
6. `assistant_messages`
7. `schedule_change_logs`

## 7.3 `user_profile`

字段建议：

1. `id`
2. `username`
3. `display_name`
4. `timezone`
5. `home_location_name`
6. `home_location_coords`
7. `work_location_name`
8. `work_location_coords`
9. `transport_preference`
10. `wake_up_time`
11. `sleep_time`
12. `preferences_json`
13. `created_at`
14. `updated_at`

## 7.4 `events`

字段建议：

1. `id`
2. `user_id`
3. `title`
4. `description`
5. `start_time`
6. `end_time`
7. `location_name`
8. `location_coords`
9. `event_type`
10. `source`
11. `is_fixed`
12. `buffer_before`
13. `buffer_after`
14. `travel_mode`
15. `travel_duration_minutes`
16. `departure_time`
17. `status`
18. `external_event_id`
19. `created_at`
20. `updated_at`

### 说明

这张表必须能支撑：

1. 冲突检测
2. 出发提醒
3. 日历展示
4. 外部同步

## 7.5 `tasks`

字段建议：

1. `id`
2. `user_id`
3. `content`
4. `description`
5. `estimated_duration_minutes`
6. `priority`
7. `deadline`
8. `status`
9. `can_split`
10. `preferred_period`
11. `linked_event_id`
12. `created_at`
13. `updated_at`

### 说明

这张表服务于：

1. 待办池
2. 空档推荐
3. 今日建议安排

## 7.6 `reminders`

字段建议：

1. `id`
2. `user_id`
3. `target_type`
4. `target_id`
5. `remind_type`
6. `remind_at`
7. `delivery_channel`
8. `message`
9. `status`
10. `sent_at`
11. `created_at`

### `remind_type` 建议枚举

1. `event_start`
2. `departure`
3. `task_deadline`
4. `idle_slot_suggestion`
5. `conflict_warning`

## 7.7 `assistant_sessions`

字段建议：

1. `id`
2. `user_id`
3. `session_type`
4. `context_json`
5. `created_at`
6. `updated_at`

## 7.8 `assistant_messages`

字段建议：

1. `id`
2. `session_id`
3. `role`
4. `content`
5. `tool_calls_json`
6. `created_at`

## 7.9 `schedule_change_logs`

字段建议：

1. `id`
2. `user_id`
3. `event_id`
4. `change_type`
5. `reason`
6. `old_value_json`
7. `new_value_json`
8. `trigger_source`
9. `created_at`

### 作用

支撑：

1. 事件被如何自动调整的可追溯性
2. 答辩时的系统可解释性

## 8. 调度与提醒引擎设计

## 8.1 调度引擎职责

调度引擎是整个系统的核心，不属于普通 CRUD。

它需要提供以下能力：

1. 检测时间重叠
2. 检测出发时间是否不足
3. 识别两个事件之间是否存在可用空档
4. 将小任务插入空档
5. 在事件变动后刷新提醒

## 8.2 核心算法策略

建议先做规则版：

1. 按开始时间排序事件
2. 计算相邻事件间隔
3. 扣除前后缓冲时间
4. 判断剩余时段是否可插入待办
5. 若地点不同，插入通勤时长

### 冲突判断规则

事件 A 与事件 B 冲突，当且仅当：

1. `A.end_time + A.buffer_after > B.start_time - B.buffer_before`

若地点不同，还应额外考虑：

1. `A.end_time + A.buffer_after + travel_time(A.location, B.location) > B.start_time - B.buffer_before`

## 8.3 主动提醒逻辑

提醒引擎建议使用 `Celery Beat + Celery Worker`。

建议至少配置以下任务：

1. 每 1 分钟扫描近 30 分钟事件
2. 每 5 分钟扫描近 2 小时的出发事件
3. 每 15 分钟扫描今日空档与待办风险
4. 每 30 分钟检查是否存在冲突或延误风险

## 8.4 主动建议逻辑

系统应支持主动生成两类建议：

### A. 空档建议

示例：

1. 现在到下一项日程前有 45 分钟，建议处理“提交周报”
2. 今天下午有两个 30 分钟空档，建议拆分完成“复习答辩 PPT”

### B. 出发建议

示例：

1. 18:00 在校外有会议，按当前路况建议 17:15 出发
2. 当前路况比平时更堵，建议提前 10 分钟准备

## 8.5 延误与重排

初版不做复杂自动重排，只做“建议式重排”。

系统发现冲突时：

1. 不直接大规模自动改表
2. 先给用户推荐 1-3 个替代时间
3. 用户确认后再执行

这样更稳，也更适合毕业设计演示。

## 9. 工具层设计

## 9.1 Calendar Tool

参考 `calendar-mcp/src/calendar_actions.py`。

建议提供：

1. `list_events(user_id, start, end)`
2. `create_event(payload)`
3. `update_event(event_id, payload)`
4. `delete_event(event_id)`
5. `query_free_busy(user_id, start, end)`

## 9.2 Task Tool

参考 `todo-work-agent/database/models.py` 的 Repository 风格。

建议提供：

1. `create_task(payload)`
2. `list_tasks(user_id, filters)`
3. `update_task(task_id, payload)`
4. `mark_task_done(task_id)`
5. `get_due_tasks(user_id, range)`

## 9.3 Map Tool

建议封装：

1. `estimate_travel_time(origin, destination, mode, departure_time)`
2. `estimate_departure_time(event)`

初版可先写适配接口，先返回模拟值或简单估算，再接高德地图 API。

当前由于高德 API 已完成基础可用性测试，地图能力不再是概念性占位，而应直接进入正式接入阶段。

## 9.4 Weather Tool

建议封装：

1. `get_weather(location, start_time, end_time)`

主要用于：

1. 出发提醒文案增强
2. 户外事件的风险提示

当前默认天气服务选型为：

1. `和风天气`

## 9.5 Notification Tool

建议封装：

1. `push_in_app_notification(user_id, payload)`
2. `broadcast_ws_notification(user_id, payload)`
3. `create_reminder_record(payload)`

后续可扩展：

1. 邮件
2. 微信
3. 手机推送
4. 语音输出插件

当前通知能力正式要求为：

1. 站内提醒
2. WebSocket 推送
3. 桌面系统通知

其中桌面通知建议通过 `Tauri 2` 官方通知插件实现。

## 10. API 设计

## 10.1 事件接口

1. `GET /api/events?start=...&end=...`
2. `POST /api/events`
3. `GET /api/events/{id}`
4. `PUT /api/events/{id}`
5. `DELETE /api/events/{id}`

## 10.2 任务接口

1. `GET /api/tasks`
2. `POST /api/tasks`
3. `PATCH /api/tasks/{id}`
4. `DELETE /api/tasks/{id}`

## 10.3 助手接口

1. `POST /api/assistant/message`
2. `GET /api/assistant/sessions/{id}`

### 请求示例

```json
{
  "session_id": "optional-session-id",
  "message": "帮我安排一下明天下午，把复习和买东西插进去"
}
```

### 返回示例

```json
{
  "session_id": "sess_xxx",
  "reply": "明天下午 14:00-15:00 适合复习，17:30-18:00 适合买东西。",
  "actions": [
    {
      "type": "suggest_schedule",
      "items": []
    }
  ]
}
```

## 10.4 提醒接口

1. `GET /api/reminders`
2. `POST /api/reminders/{id}/read`

## 10.5 建议接口

1. `GET /api/suggestions/today`
2. `GET /api/suggestions/next`

## 11. 插件扩展设计

## 11.1 当前必须预留的插件点

虽然你说现在不用细做语音，但要提前预留扩展边界。

建议后端提供：

1. `InputAdapter`
2. `OutputAdapter`
3. `ContextProvider`
4. `NotificationProvider`

### 输入插件接口

```python
class InputAdapter:
    def parse(self, payload) -> dict:
        ...
```

### 输出插件接口

```python
class OutputAdapter:
    def render(self, message, metadata=None) -> dict:
        ...
```

当前默认：

1. 文本输入适配器
2. 文本输出适配器

未来新增：

1. 语音输入适配器
2. 语音输出适配器

## 11.2 插件式接入语音的原则

未来增加语音能力时：

1. 不修改核心调度逻辑
2. 不修改事件表结构
3. 不修改提醒引擎
4. 只扩展输入输出适配层

## 12. 部署方案

## 12.1 开发环境

建议：

1. `docker-compose`
2. `redis`
3. `sqlite 数据文件`
4. `backend`
5. `frontend`
6. `celery_worker`
7. `celery_beat`

## 12.2 最小生产环境

建议：

1. `Nginx`
2. `Frontend`
3. `FastAPI API`
4. `Uvicorn / WebSocket`
5. `Celery Worker`
6. `Celery Beat`
7. `Redis`
8. `SQLite 数据文件持久化`

## 12.3 部署原则

尽量先做单机容器化部署，避免把精力消耗在云基础设施上。

需要补充一条关键实施约束：

1. `Celery` 官方不支持 Microsoft Windows 作为正式受支持平台
2. 因此本地开发环境中的 `Redis` 与 `Celery` 正式采用 `Docker` 方式运行
3. 不建议把 `Celery worker/beat` 作为原生 Windows 进程运行方案来设计
4. 当前项目默认约定：所有后端组件均运行在 Docker 容器中

## 12.4 容器化运行边界

当前正式约定如下：

1. `fastapi api` 运行在 Docker 容器中
2. `uvicorn/asgi` 运行在 Docker 容器中
3. `celery worker` 运行在 Docker 容器中
4. `celery beat` 运行在 Docker 容器中
5. `redis` 运行在 Docker 容器中
6. `sqlite` 数据文件通过 Docker volume 或挂载目录持久化

## 13. 推荐落地路线

## 13.1 第一阶段

先完成：

1. 基础数据库表
2. 事件 CRUD
3. 任务 CRUD
4. 助手消息接口
5. 日历页基础展示

## 13.2 第二阶段

再完成：

1. 冲突检测
2. 空档建议
3. 出发提醒
4. 今日建议安排

## 13.3 第三阶段

最后完成：

1. WebSocket 实时提醒
2. 外部地图接入
3. 外部日历同步
4. UI 展示优化
5. 演示数据与答辩材料

## 14. 最终推荐结论

这套系统最合适的可落地实现不是“先做复杂多 Agent”，而是：

1. 用 `calendar-ai` 的前端交互模式做日历 + 助手主界面
2. 用 `calendar-mcp` 的工具化思路做 Calendar Tool
3. 用 `todo-work-agent` 的工作流、Repository、工具目录和测试思路做后端主骨架
4. 用 `spec-to-agents` 的目录分层和模块组织方式做工程结构
5. 用 `Celery Beat + Reminder Engine` 把主动提醒真正做成系统能力
6. 用 `SQLite + Redis` 保持数据层轻量可部署

如果后续真的要演进多 Agent，也应该建立在这套单工作流 + 工具层 + 提醒引擎已经跑通的基础上，而不是反过来。
