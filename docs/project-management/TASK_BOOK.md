# 项目任务书

**更新日期**: 2026-04-28  
**当前基线**: 以当前工作区代码与测试结果为准  
**当前判断**: 项目已进入 **V8 收敛改造主路径已落地，兼容层清理进行中** 状态

## 当前目标

在 V7 主基线已经完成切换、V8 收敛主改造已经进入实装阶段的前提下，继续完成兼容层清理、性能复核与文档统一，确保后续开发与汇报都基于统一、稳定、可验证的版本口径。

## 当前完成情况

### 已稳定存在于主链路/主界面的部分

- 事件、任务、提醒、助手会话等基础业务链路已存在
- Assistant 已支持 WebSocket 流式回复
- workflow 已接管 `send_message` / `send_message_stream`
- 助手当前会话、Inbox、Summary 等接口已存在
- 地图、天气、Google Calendar、提醒、WebSocket 主工作台链路仍在使用
- 前端 Store 拆分已完成大部分结构迁移，`workspace.ts` 已退化为兼容层
- 移动端/桌面端壳目录已建好

### 已被当前基线吸纳的 V6 内容

- 向量库与 Gemini Embedding
- 习惯学习/偏好学习服务
- 多轮对话槽位补全
- 扫描线冲突检测器
- 智能任务拆分服务
- Habit / TaskSplit 数据模型及迁移草稿

### 已落地的 V7 主基线内容

- LangGraph 工作流目录与运行链路
- ReAct 子图
- 条件化上下文收集节点
- 工具注册型写法
- 部分超时与外部上下文优化
- backend 全量测试通过
- workflow debug 接口已落地
- Alembic 迁移已实跑验证到 `head`

### 已落地的 V8 主路径收敛内容

- 前端主界面已收敛为 **日历 / 任务 / 助手 / 设置** 四个一级入口
- `TasksPanel.vue` / `SettingsPanel.vue` 已落地，`SummaryPanel` / `InsightsPanel` 已退出主路径
- 首页 `hydrate()` 已精简为 events / tasks / assistant current / sessions 的首屏关键层
- `GoogleCalendarPanel` / `ProfilePanel` / `ContextPanel` 已迁移或降级到设置层/按需层
- `assistant/current` 已支持轻量模式，前端主路径默认 `include_inbox=false`
- `assistant/summary` 已从前端主路径移除
- `SuggestionService` 默认核心模式已跳过天气/地图/POI 外部调用
- `debug.html` 已区分窗口错误率与最近 5 分钟错误率，并支持清空请求日志
- WebSocket 工作台快照已收缩为仅广播 `events` / `tasks`

## 当前关键判断

### 当前版本归属

- 当前应归类为：**V7 已落地，V8 主收敛改造已基本落地**
- 当前主要工作从“版本切换”转为“兼容层清理、性能复核与文档收尾”

### 当前主问题

当前不再是“新能力没接通”，而是：

- 旧的 assistant inbox / summary / reminders / suggestions 兼容接口与前端 facade 还未完全退净
- 部分调试与兼容代码仍保留，需判断是否继续下线
- `AssistantService` / session runtime / suggestion runtime 仍有进一步瘦身空间
- 可选依赖与运行说明仍需继续收口

## 关键决策

### 已确认

1. 当前项目已经完成 V7 主入口接管。
2. V8 的产品结构收敛方向已经锁定并已在主路径大部分落地。
3. 前端主界面以 `日历 / 任务 / 助手 / 设置` 为唯一一级入口口径。
4. 首页主路径不再依赖 `assistant/summary`、`suggestions/*`、`context/*`、`reminders`。
5. 后续优先级应转向兼容层清理、性能复核、依赖说明与架构清债。

### 建议锁定

1. 近期优先目标应是**收口 V8**，而不是再并行开新版本分支。
2. 在兼容层与性能复核完成前，不建议继续横向扩展更多 agent 分支。

## 当前风险

1. 旧接口兼容仍在，存在“代码已不使用但接口仍存活”的长期漂移风险。
2. `AssistantService` 仍然过大，尚未彻底瘦身。
3. 向量能力仍依赖可选外部包，需补齐安装与运行说明。
4. 剩余弃用 warning 主要来自测试代码。

## 下一步任务

### P0

1. 收口兼容层
   - 清理前端已脱离主路径的 assistant inbox / summary facade 暴露
   - 评估 `assistant/inbox` / `assistant/summary` 的接口退场顺序
2. 收口性能复核
   - 用 `debug.html` 与真实主界面再次核对首页关键请求数量
   - 复核 `assistant/current` / `suggestions/*` 的真实耗时变化
3. 收口文档层
   - 统一 V8 落地口径
   - 同步 README / 状态文档 / 实施计划书

### P1

1. 继续瘦身编排层
   - 进一步拆薄 `AssistantService`
2. 深化习惯学习链路
   - 明确最小可用 API 面与展示面
3. 清理弃用警告
   - 统一时间处理实现

### P2

1. 审视剩余调试与监控面板是否继续保留
2. 视需要补充 workflow trace 的轻量展示集成

## 当前建议的唯一下一步动作

先以 **V8 最后一轮收口** 为目标完成一次兼容层与性能复核：

1. 清理已脱离主路径的旧 facade 与旧组件残留
2. 对首页与助手操作后的请求链路做一次最终人工复核
3. 同步项目管理与实现文档口径
