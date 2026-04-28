# 个人事务助手系统实现计划 V8 - 功能收敛、聚合去重与启动性能治理

> 本文档是 V7 当前基线落地后的下一阶段实现计划。  
> V8 的核心不是继续横向扩展新能力，而是围绕以下三条主线做系统性收敛：  
> 1. **产品结构收敛**：减少重复面板、重复概念、重复入口，建立更清晰的用户心智。  
> 2. **请求链路收敛**：删除首页不必要请求，拆掉聚合接口套聚合接口的链路。  
> 3. **性能与调试口径收敛**：解决真实慢接口，同时修正 `debug.html` 中“历史错误污染当前错误率”的统计误差。

---

## 目录

- [一、V8 立项背景与现状判断](#一v8-立项背景与现状判断)
- [二、V8 总目标与目标形态](#二v8-总目标与目标形态)
- [三、现状问题拆解](#三现状问题拆解)
  - [3.1 产品结构问题](#31-产品结构问题)
  - [3.2 启动链路问题](#32-启动链路问题)
  - [3.3 聚合接口性能问题](#33-聚合接口性能问题)
  - [3.4 调试统计口径问题](#34-调试统计口径问题)
- [四、V8 目标产品结构](#四v8-目标产品结构)
  - [4.1 一级心智收敛](#41-一级心智收敛)
  - [4.2 桌面端目标布局](#42-桌面端目标布局)
  - [4.3 移动端目标布局](#43-移动端目标布局)
  - [4.4 模块处置矩阵](#44-模块处置矩阵)
- [五、P0 — 产品结构收敛（核心）](#五p0--产品结构收敛核心)
  - [P0-1: 主界面收敛为四个一级能力](#p0-1-主界面收敛为四个一级能力)
  - [P0-2: 下线 SummaryPanel](#p0-2-下线-summarypanel)
  - [P0-3: 拆解 InsightsPanel，仅保留 TasksPanel](#p0-3-拆解-insightspanel仅保留-taskspanel)
  - [P0-4: Assistant Inbox 降级并最终退场](#p0-4-assistant-inbox-降级并最终退场)
  - [P0-5: Settings 层归并 Google Calendar 与 Profile](#p0-5-settings-层归并-google-calendar-与-profile)
  - [P0-6: ContextPanel 降级为场景内联信息](#p0-6-contextpanel-降级为场景内联信息)
- [六、P1 — 首页启动链路瘦身](#六p1--首页启动链路瘦身)
  - [P1-1: 重排 workspace.hydrate()](#p1-1-重排-workspacehydrate)
  - [P1-2: 首页关键请求白名单](#p1-2-首页关键请求白名单)
  - [P1-3: 按需加载策略](#p1-3-按需加载策略)
- [七、P2 — 助手聚合链路去重](#七p2--助手聚合链路去重)
  - [P2-1: assistant/current 去重](#p2-1-assistantcurrent-去重)
  - [P2-2: assistant/summary 去重或退场](#p2-2-assistantsummary-去重或退场)
  - [P2-3: Inbox 生成逻辑去耦合](#p2-3-inbox-生成逻辑去耦合)
- [八、P3 — SuggestionService 瘦身与能力分层](#八p3--suggestionservice-瘦身与能力分层)
  - [P3-1: 核心建议与增强建议分层](#p3-1-核心建议与增强建议分层)
  - [P3-2: 禁止默认路径触发昂贵外部调用](#p3-2-禁止默认路径触发昂贵外部调用)
  - [P3-3: 复用同请求数据快照](#p3-3-复用同请求数据快照)
- [九、P4 — 调试页与统计口径治理](#九p4--调试页与统计口径治理)
  - [P4-1: 实时错误与历史错误分离](#p4-1-实时错误与历史错误分离)
  - [P4-2: Debug 页面筛选与解释增强](#p4-2-debug-页面筛选与解释增强)
  - [P4-3: 历史错误污染治理](#p4-3-历史错误污染治理)
- [十、数据库、接口与兼容策略](#十数据库接口与兼容策略)
- [十一、详细实施顺序与工期建议](#十一-详细实施顺序与工期建议)
- [十二、验证指标与验收标准](#十二-验证指标与验收标准)
- [十三、风险与回滚策略](#十三-风险与回滚策略)
- [十四、已确认决策](#十四-已确认决策)
- [十五、结论与推荐路线](#十五-结论与推荐路线)

---

## 一、V8 立项背景与现状判断

### 1.1 当前版本判断

当前系统版本口径已经明确为：

> **V7 当前基线已落地**

这意味着 V8 不再是“新版本基础设施搭建”，而是：

- 在现有主链路上做结构收敛
- 在现有接口基础上做聚合与读取去重
- 在现有主界面上做信息架构减法
- 在现有调试能力上修正统计口径

### 1.2 V8 的真实任务

V8 的任务不是继续扩大系统边界，而是回答这三个问题：

1. **这个系统到底是什么产品？**
2. **为什么首页打开时这么慢？**
3. **为什么调试面板显示还在出错，但用户当前看到的大多数接口已经是 200？**

V8 需要把这三个问题同时解决，否则：

- 产品层继续混乱
- 性能层继续拖慢体验
- 调试层继续误导判断

### 1.3 V8 的统一目标表述

建议将 V8 对外统一表述为：

> **V8 聚焦于“系统收敛与性能治理”**：在保持 V7 主工作流稳定的前提下，将系统收敛为“日历 + 任务 + 助手 + 设置”的明确结构，并通过删除重复聚合、减少默认外部调用与收缩首页请求链路，显著降低页面加载与聚合接口的响应时间。

---

## 二、V8 总目标与目标形态

### 2.1 V8 四个总目标

1. **产品目标**
   - 用户可以清楚理解系统由哪些模块组成
   - 去除“收件箱像邮箱”“摘要像第二个首页”“洞察像杂糅中心”的混乱感

2. **性能目标**
   - 首页打开时不再自动触发多轮 suggestions/summary/context 聚合
   - `assistant/current`、`suggestions/*`、`assistant/summary` 的重复计算显著下降

3. **工程目标**
   - 把重复数据读取、重复聚合、默认昂贵上下文调用，从主路径里移走
   - 让前端加载策略和后端聚合逻辑具备可解释性

4. **演示目标**
   - 后续论文、答辩和展示时，系统边界可被一句话清晰解释
   - 调试页上的错误率与性能数据可以被正确说明，不再自相矛盾

### 2.2 V8 目标产品一句话定义

> **一个以日历为主画布、以任务为执行对象、以 AI 助手为操作入口、以设置页承载外围集成的个人事务工作台。**

---

## 三、现状问题拆解

### 3.1 产品结构问题

当前前端不是一个单层清晰结构，而是多层信息叠加：

- `SummaryPanel`
- `InsightsPanel`
- `Assistant Inbox`
- `AssistantPanel` 内 action card
- `CalendarPanel`
- `ContextPanel`
- `GoogleCalendarPanel`
- `ProfilePanel`

其中以下信息重复度很高：

| 信息类型 | 重复出现位置 |
|---|---|
| 接下来做什么 | `SummaryPanel` / `InsightsPanel` / `Assistant Inbox` |
| 任务状态 | `InsightsPanel` / `Assistant Inbox` / 助手对话 |
| 建议安排 | `InsightsPanel` / `Assistant Inbox` / 助手 action card |
| 跟进提示 | `Assistant Inbox` / 摘要卡 / 提醒层 |

这会带来两个直接后果：

1. 用户无法快速建立“系统主入口”心智  
2. 首页为了喂这些面板，不得不并行拉很多数据

### 3.2 启动链路问题

当前 [workspace.ts](E:/GraduationProject/frontend/src/stores/workspace.ts) 的 `hydrate()` 启动时会并行加载：

- `events`
- `tasks`
- `reminders`
- `suggestions`
- `googleCalendarStatus`
- `assistantSessions`
- `assistantCurrent`
- `assistantSummary`

随后又延迟加载：

- `weatherNow`
- `travelEstimate`
- `backendPerformance`
- `aiHealth`

即使用户只是打开首页，也会在后台自动做：

- 多个聚合接口请求
- 多个列表请求
- 多个非首屏关键请求
- 多个可能关联外部 API 的请求

### 3.3 聚合接口性能问题

根据 `debug.html` 观测，当前真实的慢接口是：

| 接口 | 最近观测 | 解释 |
|---|---:|---|
| `/api/assistant/summary` | 约 `9.1s`，历史峰值约 `21.8s` | 聚合过重 |
| `/api/assistant/current` | 约 `2.8s` | current 路径仍偏重 |
| `/api/suggestions/today` | 约 `3.1s` | 默认建议生成偏重 |
| `/api/suggestions/next` | 约 `2.1s` | 同上 |
| `/api/context/travel` | 约 `2.7s` | 本身依赖外部上下文调用 |

#### 3.3.1 `assistant/summary` 的问题

当前逻辑链路：

```text
get_summary()
  -> get_inbox()
      -> 查 tasks
      -> 查 reminders
      -> build_suggestions_for_dates(未来 3 天)
  -> 再查 tasks
  -> 再查 reminders
  -> get_today_suggestions()
  -> get_next_suggestions()
```

这意味着：

- 任务至少被读取两轮
- 提醒至少被读取两轮
- 建议至少被生成多轮

#### 3.3.2 `SuggestionService` 的问题

当前 [suggestions.py](E:/GraduationProject/backend/app/services/suggestions.py) 每次计算建议时都会：

- 重新读取全部事件
- 重新读取用户资料
- 重新读取全部任务
- 默认进入 `_build_context_suggestions()`
- 视情况继续进天气、地图、POI 搜索

也就是说，建议接口当前并不轻，它不是“纯规则计算空档”，而是“规则调度 + 上下文增强 + 外部调用候选”混在一起。

#### 3.3.3 `assistant/current` 的问题

当前 [assistant_runtime_session.py](E:/GraduationProject/backend/app/services/assistant_runtime_session.py) 中：

- `get_current_session()` 会先 `get_inbox()`
- `get_inbox()` 会查任务、查提醒、生成建议
- 然后还会做 `sync_inbox_to_session()`
- 再回读 `get_session()`

这条链路虽然比 `summary` 轻，但仍然包含多层聚合与会话同步。

### 3.4 调试统计口径问题

当前 `debug.html` 使用的是：

- `GET /api/debug/requests` 提供的窗口请求日志
- 所有 `status >= 400` 的请求都会被一起计入错误率

但问题在于：

- 窗口中混有历史 404
- 旧路径错误和当前错误没有区分
- 老版本请求残留与当前运行状态没有区分

因此当前“8% error rate”更接近：

> “窗口历史错误比例”

而不是：

> “系统此刻实时失败率”

---

## 四、V8 目标产品结构

### 4.1 一级心智收敛

V8 目标只保留四个一级能力：

- `日历`
- `任务`
- `助手`
- `设置`

其它能力全部降级为：

- 某个模块的附属视图
- 某个场景下的上下文信息
- 某个操作结果的反馈层

### 4.2 桌面端目标布局

建议桌面端最终布局：

```text
┌──────────────────────────────────────────────────────────────┐
│ 顶栏：标题 / 语言 / 少量状态 / 设置入口                       │
├───────────────────────────────┬──────────────────────────────┤
│ 左主区                         │ 右侧助手栏                   │
│                                │                              │
│ 上：CalendarPanel              │ AssistantPanel               │
│ 下：TasksPanel                 │ - 会话切换                   │
│                                │ - 聊天消息                   │
│                                │ - 动作结果                   │
│                                │ - 待确认操作                 │
└───────────────────────────────┴──────────────────────────────┘
```

不再出现：

- 独立 Summary 区
- 独立 Inbox 区
- 独立 Insights 三合一区
- 首页顶部常驻 Google Calendar 主卡
- 首页常驻天气/通勤双卡

### 4.3 移动端目标布局

建议移动端只保留四个 tab：

- `日历`
- `任务`
- `助手`
- `设置`

如需“今日概览”，只允许做极轻量 header，不再保留完整 `SummaryPanel`。

### 4.4 模块处置矩阵

| 模块 | 当前状态 | V8 处置 | 原因 |
|---|---|---|---|
| `CalendarPanel` | 主模块 | 保留 | 最清晰的主工作台画布 |
| `AssistantPanel` 聊天主区 | 主模块 | 保留 | 系统差异化核心入口 |
| `Assistant Inbox` | 助手内嵌层 | 下线或显著降级 | 概念误导，和任务/摘要重叠 |
| `SummaryPanel` | 首页概览层 | 删除 | 与任务/助手/提醒重复 |
| `InsightsPanel` | 三合一面板 | 拆解 | 职责混杂 |
| `任务列表` | Insights 内部 | 保留并独立 | 核心对象层 |
| `提醒` 列表 | Insights 内部 | 降级 | 只需轻提示，不需主面板 |
| `建议` 列表 | Insights 内部 | 降级 | 建议应附着任务或助手，而不是独立一级面板 |
| `ContextPanel` | 主界面组件 | 降级 | 只在需要时出现 |
| `GoogleCalendarPanel` | 首页顶部 | 迁移到设置 | 属于外围集成 |
| `ProfilePanel` | 顶部抽屉 | 保留并迁移到设置 | 属于设置层 |
| `PerformancePanel` | 非主挂载 | 保留内部能力 | 面向调试，不进主工作台 |

---

## 五、P0 — 产品结构收敛（核心）

### P0-1: 主界面收敛为四个一级能力

**目标**：让用户第一眼就知道系统是什么，不再被多个半重叠模块分散注意力。

**涉及文件**：

- `E:\GraduationProject\frontend\src\App.vue`
- `E:\GraduationProject\frontend\src\stores\workspace.ts`

**实施要点**：

1. 桌面端主区收敛为：
   - `CalendarPanel`
   - `TasksPanel`
   - `AssistantPanel`
2. 移动端 tab 固定为：
   - `calendar`
   - `tasks`
   - `assistant`
   - `settings`
3. 顶栏只保留：
   - 标题
   - 语言切换
   - 少量状态
   - 设置入口

**不再保留的旧结构**：

- 首页中部概览卡片层
- 首页中部多区域 stacked dashboard
- “跟进待处理”和“摘要卡片”同时存在

**验收标准**：

- 用户打开首页时，不需要理解 3 个以上的核心区域
- 顶层导航词汇不再出现“洞察”“收件箱”“摘要”这种中间层概念

### P0-2: 下线 SummaryPanel

**目标**：删除“第二个首页”的信息层，避免卡片与主区重复。

**涉及文件**：

- `E:\GraduationProject\frontend\src\components\SummaryPanel.vue`
- `E:\GraduationProject\frontend\src\App.vue`
- `E:\GraduationProject\frontend\src\stores\assistant.ts`
- `E:\GraduationProject\backend\app\services\assistant_runtime_session.py`
- `E:\GraduationProject\backend\app\api\routes\assistant.py`

**实施策略**：

1. 前端先移除对 `assistantSummary` 的主路径依赖
2. 首页不再默认请求 `/api/assistant/summary`
3. 后端保留接口一段兼容期
4. 若兼容期后无前端依赖，再评估退场

**为什么不能先只优化 summary 再保留它**：

因为 `SummaryPanel` 的产品职责本身已经和其他模块重叠。  
单纯优化性能，不能解决它在结构上重复存在的问题。

### P0-3: 拆解 InsightsPanel，仅保留 TasksPanel

**目标**：把“任务”从“任务 + 提醒 + 建议”的混合容器中解放出来。

**涉及文件**：

- `E:\GraduationProject\frontend\src\components\InsightsPanel.vue`
- 新增 `E:\GraduationProject\frontend\src\components\TasksPanel.vue`（建议）

**拆解后职责**：

- `TasksPanel`
  - 展示任务列表
  - 显示状态 / 已安排时长 / 已完成时长 / 剩余时长
  - 支持继续规划
  - 支持删除任务

- `Reminders`
  - 不再做独立大面板
  - 只作为 toast 或轻量状态条

- `Suggestions`
  - 不再独立展示为主区列表
  - 只在任务详情或助手对话中出现

**验收标准**：

- “任务”页面只讲任务
- 用户进入任务页时，不会再看到 unrelated reminder/suggestion 噪声

### P0-4: Assistant Inbox 降级并最终退场

**目标**：移除最容易造成认知误解的产品层概念。

**涉及文件**：

- `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`
- `E:\GraduationProject\frontend\src\stores\assistant.ts`
- `E:\GraduationProject\backend\app\services\assistant_runtime_session.py`
- `E:\GraduationProject\backend\app\api\routes\assistant.py`

**当前问题**：

- 用户不认为自己设计过“邮箱/收件箱”
- 但系统里确实存在一个 `Assistant Inbox`
- 它同时承担：
  - 任务跟进
  - 建议入口
  - 会话内主动消息

这说明它不是自然形成的产品概念，而是技术实现遗留概念。

**已锁定处理方式**：

采用分阶段退场策略：

1. **过渡阶段（B）**
   - 保留后端数据结构兼容
   - 前端不再突出显示“收件箱”入口
   - 如仍需短暂展示，仅以“待处理跟进”或“待确认动作”的轻量块呈现

2. **目标阶段（A）**
   - 前端彻底移除独立 Inbox UI
   - 只保留助手内待确认动作
   - 后端逐步弱化 `get_inbox()` 对会话 surfacing 的耦合

**最终目标**：

- 不再保留独立 `Inbox` 产品心智
- 所有“待处理”回归：
  - 任务
  - 助手确认动作
  - 轻提醒

### P0-5: Settings 层归并 Google Calendar 与 Profile

**目标**：把“设置型模块”移出首页主工作台。

**涉及文件**：

- `E:\GraduationProject\frontend\src\components\GoogleCalendarPanel.vue`
- `E:\GraduationProject\frontend\src\components\ProfilePanel.vue`
- `E:\GraduationProject\frontend\src\App.vue`
- 可能新增 `SettingsPanel.vue`

**实施方案（已锁定）**：

1. 将 `ProfilePanel` 固化为设置区内容
2. 将 `GoogleCalendarPanel` 从首页顶部迁出
3. 首页只保留一个极轻量的 Google Calendar 状态徽标
4. 完整连接/同步面板仅在设置层展示

**收益**：

- 首页视觉重心不再被外围集成功能抢占
- Google Calendar 从“首页主要内容”降回“系统设置/集成”

### P0-6: ContextPanel 降级为场景内联信息

**目标**：不再让天气/通勤成为首页常驻重量组件。

**涉及文件**：

- `E:\GraduationProject\frontend\src\components\ContextPanel.vue`
- `E:\GraduationProject\frontend\src\components\CalendarPanel.vue`
- `E:\GraduationProject\frontend\src\components\AssistantPanel.vue`

**改造方向**：

- 创建带地点事件时，在助手回复或事件确认卡中展示天气/通勤信息
- 查看某个事件详情时，按需拉取 travel/weather
- 首页默认不展示独立天气/通勤双卡

**注意**：

这一步和性能治理强相关，因为它能直接减少默认的 `context/travel` / `context/weather` 触发冲动。

---

## 六、P1 — 首页启动链路瘦身

### P1-1: 重排 workspace.hydrate()

**目标**：让启动链路只请求“首屏必需数据”。

**涉及文件**：

- `E:\GraduationProject\frontend\src\stores\workspace.ts`

**当前问题**：

`hydrate()` 同时拉：

- events
- tasks
- reminders
- suggestions
- google calendar status
- assistant sessions
- assistant current
- assistant summary

这等价于把多个模块的数据依赖全部堆到首屏。

**V8 改造目标**：

将 `hydrate()` 分成三层：

```text
Layer A: 首屏关键层
  - events
  - tasks
  - assistant current
  - assistant sessions（可选）

Layer B: 次级按需层
  - settings data
  - google calendar status

Layer C: 用户触发层
  - reminders
  - suggestions
  - weather/travel
  - performance/health
```

### P1-2: 首页关键请求白名单

V8 建议首页关键白名单只保留：

- `GET /api/events`
- `GET /api/tasks`
- `GET /api/assistant/current`
- 可选：`GET /api/assistant/sessions`

从首页关键链路移除：

- `/api/assistant/summary`
- `/api/suggestions/today`
- `/api/suggestions/next`
- `/api/reminders`
- `/api/context/travel`
- `/api/context/weather/now`
- `/api/google-calendar/status`
- `/api/health/ai`
- `/api/health/performance`

### P1-3: 按需加载策略

| 数据 | 触发方式 |
|---|---|
| Google Calendar 状态 | 进入设置页时加载 |
| reminders | 打开任务页或通知中心时加载 |
| suggestions | 进入任务页、选中任务、请求继续安排时加载 |
| weather/travel | 事件确认或显式点击详情时加载 |
| performance/health | 仅 debug 页面加载 |

**验收标准**：

- 打开首页时网络请求数量显著低于当前实现
- 调试页和首屏构建时不再互相影响

---

## 七、P2 — 助手聚合链路去重

### P2-1: assistant/current 去重

**目标**：让 `/api/assistant/current` 只承担“当前会话读取”，而不是顺带做太多后台汇总工作。

**当前链路**：

```text
get_current_session()
  -> get_inbox()
  -> sync_inbox_to_session()
  -> get_session()
```

**问题**：

- current 请求其实在做 inbox 计算
- inbox 又会查任务、查提醒、生成 suggestions
- current 请求负担被抬高

**V8 改造建议**：

引入一个更轻的 current 读取模型：

```text
get_current_session_light()
  -> latest session
  -> visible messages
  -> minimal pending actions
```

如果前端不再需要独立 inbox，就不应在 current 里隐式生成 inbox。

### P2-2: assistant/summary 去重或退场

**目标**：避免 `summary -> inbox -> suggestions` 的套娃式聚合。

**建议优先级**：

1. 前端先移除首页依赖
2. 后端再判断：
   - 保留为非关键接口
   - 还是继续兼容
   - 或逐步退场

**如果保留 summary 接口**，则必须满足：

- 只读取一轮任务
- 只读取一轮提醒
- 只生成一轮建议
- 不再先调 `get_inbox()`

### P2-3: Inbox 生成逻辑去耦合

**目标**：把“任务跟进生成逻辑”和“会话消息写入逻辑”分离。

**当前问题**：

- `sync_inbox_to_session()` 会把 inbox 项反写成 assistant 消息
- 会话与 inbox 之间形成强耦合
- 这让 current/inbox/message 三者边界变模糊

**V8 建议**：

- 会话消息是会话消息
- 待处理动作是待处理动作
- 不再默认把每个 follow-up 都转写为消息

这一步能同时简化：

- 当前 session 读取
- 会话 UI
- inbox 状态同步

---

## 八、P3 — SuggestionService 瘦身与能力分层

### P3-1: 核心建议与增强建议分层

**目标**：把 `SuggestionService` 从“大而全建议引擎”拆成两层。

建议拆成：

1. **核心建议层**
   - 根据任务、空档、偏好生成任务时段建议
   - 不触发天气、地图、POI

2. **增强建议层**
   - 天气提示
   - 通勤提示
   - 附近休息点
   - 事件相关上下文提醒

### P3-2: 禁止默认路径触发昂贵外部调用

以下类型在默认 suggestions 路径中不再启用：

- `location_based_break`
- `weather_watch`
- `weather_alert`

除非满足显式触发条件：

- 用户进入事件上下文场景
- 用户明确请求天气 / 路线 / 出发建议
- 用户点击“查看更多上下文建议”

### P3-3: 复用同请求数据快照

**目标**：同一请求内避免重复读取。

建议引入轻量数据 bundle：

```python
SuggestionInputBundle(
    events=...,
    tasks=...,
    profile=...,
    now=...,
)
```

这样可以避免：

- 同一请求内多次读 events
- 同一请求内多次读 tasks
- 同一请求内多次读 profile

**收益**：

- suggestions 变轻
- assistant summary/current 更容易复用 bundle

---

## 九、P4 — 调试页与统计口径治理

### P4-1: 实时错误与历史错误分离

当前 `debug.html` 的错误率是基于窗口内历史请求计算的。  
V8 应拆成两个指标：

1. `窗口错误率`
   - 最近 N 条请求中的失败比例
2. `实时错误率`
   - 最近 T 秒或最近一轮刷新中的失败比例

### P4-2: Debug 页面筛选与解释增强

`debug.html` 应增强：

- 仅看失败请求
- 仅看慢请求
- 按路径筛选
- 按时间范围筛选
- 标记“旧路径/历史兼容错误”

同时页面上应显式说明：

> “错误率基于最近窗口请求统计，可能包含历史失败请求。”

### P4-3: 历史错误污染治理

可选策略：

- 增加“清空当前窗口日志”按钮
- 增加“仅显示最近 5 分钟请求”开关
- 对已知旧路径错误单独打标签

例如：

- `/api/system/ai-health`
- `/api/system/performance`
- 旧版 `/assistant/inbox/*` 兼容路径

这些可以归类为：

> `legacy-path failures`

而不是与当前业务失败混在一起。

---

## 十、数据库、接口与兼容策略

### 10.1 不涉及大规模数据库重构

V8 主要是：

- 读取模型重排
- 聚合逻辑重写
- 前端依赖削减

原则上不要求引入新的核心业务表。

### 10.2 接口演化策略

| 接口 | V8 策略 |
|---|---|
| `/api/assistant/current` | 保留，做瘦身 |
| `/api/assistant/summary` | 前端先移除依赖，再决定兼容保留或退场 |
| `/api/assistant/inbox` | 前端降级依赖，后端兼容期保留 |
| `/api/suggestions/today` | 保留，但默认仅返回轻量核心建议 |
| `/api/suggestions/next` | 同上 |
| `/api/context/travel` | 保留，但从首页默认链路移除 |
| `/api/context/weather/now` | 保留，但从首页默认链路移除 |

### 10.3 兼容期原则

建议采用：

1. **前端先停止主路径使用**
2. **后端继续兼容一段时间**
3. **确认无依赖后再退场**

这样可以降低一次性变更的风险。

---

## 十一、详细实施顺序与工期建议

### 11.1 推荐顺序

#### 第一阶段：结构收敛与请求减法

1. 调整首页结构
2. 下线 `SummaryPanel`
3. 拆解 `InsightsPanel`
4. `hydrate()` 白名单化

#### 第二阶段：后端聚合去重

5. current 链路瘦身
6. summary 链路去重或降级
7. inbox 与 session 解耦

#### 第三阶段：suggestions 与 debug 治理

8. SuggestionService 分层
9. 禁止默认昂贵外部调用
10. debug 页面统计校准

#### 第四阶段：文档与验收

11. 文档同步
12. 全量回归
13. 性能对比报告

### 11.2 工期建议

| 阶段 | 内容 | 预计工时 |
|---|---|---:|
| 阶段 1 | 前端结构收敛 + 首页请求减法 | 3-4 天 |
| 阶段 2 | 助手聚合去重 | 2-3 天 |
| 阶段 3 | SuggestionService 瘦身 | 2-3 天 |
| 阶段 4 | Debug 治理 + 文档同步 + 回归 | 1-2 天 |

**总计建议**：`8-12 个工作日`

---

## 十二、验证指标与验收标准

### 12.1 结构验收

- 主界面只保留 `日历 / 任务 / 助手 / 设置`
- 用户不再看到“收件箱”作为独立一级概念
- 首页不再同时出现 summary + insights + inbox 三层重复结构

### 12.2 请求验收

打开首页时：

- 不再请求 `/api/assistant/summary`
- 不再请求 `/api/suggestions/today`
- 不再请求 `/api/suggestions/next`
- 不再请求 `/api/context/travel`
- 不再请求 `/api/context/weather/now`
- 不再请求 `/api/reminders`

### 12.3 性能验收

| 接口 | 当前观测 | V8 目标 |
|---|---:|---:|
| `/api/assistant/current` | ~2.8s | `< 600ms` |
| `/api/assistant/summary` | ~9.1s | 首页退场；若保留兼容则 `< 800ms` |
| `/api/suggestions/today` | ~3.1s | `< 500ms` |
| `/api/suggestions/next` | ~2.1s | `< 500ms` |
| `/api/context/travel` | ~2.7s | 不进首页默认链路；显式触发场景 `< 1500ms` |

### 12.4 调试验收

- `debug.html` 可区分历史错误与当前错误
- 错误率字段具备解释性
- 可以筛选慢请求 / 失败请求 / 路径请求

### 12.5 工程验收

- 后端全量测试通过
- 前端构建通过
- 主链路手工 smoke 通过

---

## 十三、风险与回滚策略

### 13.1 主要风险

1. **前端改动面较广**
   - 页面结构、导航、store 读取点都会受影响

2. **后端聚合关系较深**
   - current / inbox / summary 当前彼此耦合

3. **建议服务被多个路径复用**
   - 改 suggestions 时，任务安排与助手跟进都可能受影响

### 13.2 风险缓解策略

- 先做前端主路径减法，再做后端退场
- 保留兼容接口一段时间
- 每一阶段单独验证
- 避免前端结构收敛与后端大改在同一提交里完全混合

### 13.3 回滚策略

若某阶段失败，回滚优先级：

1. 保留新 UI，但恢复旧接口依赖
2. 保留新接口实现，但恢复旧 UI 展示
3. 恢复 `hydrate()` 原始链路作为临时兜底

---

## 十四、已确认决策

以下决策已经由用户确认，后续 V8 实施与文档同步应以此为准。

### D1. `SummaryPanel`

- **最终决策**：A（彻底删除）✅
- **执行口径**：不保留独立摘要层；首页不再存在 summary card 区。

### D2. `Assistant Inbox`

- **最终决策**：采用 `B -> A` 的收敛路线 ✅
- **执行口径**：
  - 过渡阶段：不再突出 `Inbox` 词汇，必要时仅以“待处理跟进”轻量呈现
  - 目标阶段：彻底移除独立 Inbox UI，只保留助手内待确认动作

### D3. `任务页 reminders`

- **最终决策**：A（不保留独立 reminders 区）✅
- **执行口径**：reminders 只通过 toast、轻提示或助手上下文呈现，不保留任务页专门分区。

### D4. `Google Calendar` 首页展示

- **最终决策**：B（首页仅保留轻量状态徽标）✅
- **执行口径**：
  - 首页不再保留完整 `GoogleCalendarPanel`
  - 首页仅保留一个小状态徽标
  - 完整连接/同步能力进入设置页

### D5. `assistant/summary`

- **最终决策**：A（前端先完全移除依赖，后端兼容期后退场）✅
- **执行口径**：
  - 首页主链路不再依赖 `assistant/summary`
  - 后端暂时兼容保留
  - 待前端与调试路径脱离后再评估接口退场

### D6. `debug.html`

- **最终决策**：A（继续作为开发调试页，但修正统计口径）✅
- **执行口径**：
  - 不扩展成完整内部监控系统
  - 重点完成“实时错误 vs 历史错误”分离
  - 重点提升可解释性，而不是继续堆功能

---

## 十五、当前落地进展

### 15.1 已完成的主路径落地项

- 前端主界面已收敛为 `日历 / 任务 / 助手 / 设置`
- `TasksPanel.vue` / `SettingsPanel.vue` 已落地
- `SummaryPanel.vue` / `InsightsPanel.vue` 已退出主路径，并已从前端代码中删除
- 首页 `hydrate()` 已收敛为首屏关键请求层
- 设置页已改为进入时按需加载，不再双重触发
- `AssistantPanel` 主 UI 已移除独立 Inbox 展示
- `/api/assistant/current` 已支持 `include_inbox=false` 轻量模式，前端主路径默认启用
- `get_summary()` 已去掉多轮 suggestion 快照生成
- `SuggestionService` 核心模式已跳过天气/地图/POI 外部调用
- `workspace_snapshot` 已收缩为仅广播 `events / tasks`
- `debug.html` 已支持窗口错误率 / 最近 5 分钟错误率双指标，并修复清空请求日志后的统计残留问题

### 15.2 剩余兼容项

- 后端 `assistant/inbox` / `assistant/summary` 接口仍保留兼容期
- 前端 `assistant.ts` 仍保留少量兼容类型定义，便于兼容返回结构
- `workspace.ts` 仍作为 facade 存在，但其主路径依赖已显著收缩

### 15.3 当前验证结果

- 后端全量测试通过：`284 passed`
- 前端构建通过
- 关键 API 烟测已通过

---

## 十六、结论与推荐路线

V8 最推荐的执行路线是：

1. **先做结构减法**
   - 删 `SummaryPanel`
   - 拆 `InsightsPanel`
   - 降级或移除 `Assistant Inbox`
   - 把 Google Calendar / Profile 迁到设置层

2. **再做首页请求减法**
   - `hydrate()` 只保留首页关键白名单请求
   - 把 suggestions / reminders / context / summary 从首屏主链路移走

3. **然后做后端聚合去重**
   - current 去重
   - summary 退场或非关键化
   - inbox 与 session 解耦

4. **最后做建议服务与 debug 治理**
   - suggestions 分层
   - 默认路径不再触发昂贵外部调用
   - debug 错误率区分历史与实时

---

---

## 十七、精确实施手册（文件级）

> 本节是在代码审计后补充的精确执行参考，直接对应每个改动点的文件路径与操作。

### 16.1 前端文件变更矩阵

| 文件 | 操作 | 说明 |
|---|---|---|
| `frontend/src/App.vue` | **重写** | 移除 SummaryPanel/ContextPanel/GoogleCalendarPanel 从主区；移动端改为 calendar/tasks/assistant/settings 四 Tab；桌面端仅保留 CalendarPanel+TasksPanel+AssistantPanel |
| `frontend/src/components/SummaryPanel.vue` | **已删除** | V8 中彻底退出主路径与代码库 |
| `frontend/src/components/InsightsPanel.vue` | **已删除** | 被 TasksPanel 替代并退出代码库 |
| `frontend/src/components/TasksPanel.vue` | **新建** | 从 InsightsPanel 中抽取任务 Tab 部分 |
| `frontend/src/components/SettingsPanel.vue` | **新建** | 包含 GoogleCalendarPanel + ProfilePanel + ContextPanel（天气/通勤） |
| `frontend/src/components/ContextPanel.vue` | **保留文件** | 不在主区挂载；移入 SettingsPanel 内 |
| `frontend/src/components/GoogleCalendarPanel.vue` | **保留文件** | 移入 SettingsPanel 内 |
| `frontend/src/components/ProfilePanel.vue` | **保留文件** | 移入 SettingsPanel 内 |
| `frontend/src/stores/workspace.ts` | **修改** `hydrate()` | 删除 fetchReminders/fetchSuggestions/fetchAssistantSummary/fetchGoogleCalendarStatus/fetchWeatherNow/fetchTravelEstimate 从关键路径；保留 events/tasks/assistantCurrent/assistantSessions |
| `frontend/src/stores/workspace.ts` | **新增** `hydrateSettings()` | 按需加载 GC 状态、profile context |
| `frontend/src/stores/workspace.ts` | **新增** `hydrateTasks()` | 按需加载 reminders/suggestions |
| `frontend/src/i18n/index.ts` | **修改** | 把 `common.overview` 改为 `common.settings`；新增 `settings.*` key |

### 16.2 后端文件变更矩阵

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/services/suggestions.py` | **修改** `_build_suggestions_for_dates` | 新增 `core_only: bool = False` 参数；为 True 时跳过 `_build_context_suggestions`（天气/地图） |
| `backend/app/services/suggestions.py` | **修改** `get_today_suggestions` / `get_next_suggestions` | 接收可选 `core_only` 参数并透传 |
| `backend/app/api/routes/suggestions.py` | **修改** | 路由新增 `core_only: bool = Query(default=True)` 参数 |
| `backend/app/services/assistant_runtime_session.py` | **修改** `get_summary` | 用一次读取替代重复读取：复用 `get_inbox` 返回的 tasks/reminders；不再二次调用 `task_service.list_tasks` |
| `backend/app/services/assistant_runtime_session.py` | **修改** `get_current_session` | 轻量路径：先尝试读 session 和已有 inbox state，只有有未推送条目时才调用 `sync_inbox_to_session` |
| `frontend/public/debug.html` | **修改** `updateQuickStats` | 新增"最近 5 分钟"过滤开关；分两列显示"窗口错误率"vs"近 5 分钟错误率"；添加说明文字 |

### 16.3 关键执行顺序

```
1. 新建 TasksPanel.vue, SettingsPanel.vue
2. 修改 i18n（增加 settings key）
3. 重写 App.vue（引用新面板，移除旧面板）
4. 修改 workspace.ts hydrate()
5. 后端 suggestions.py core_only
6. 后端 assistant_runtime_session.py get_summary 去重
7. 后端 assistant_runtime_session.py get_current_session 轻量化
8. 修改 debug.html
9. Docker 构建 + 测试
```

---

## 计划元数据

- Plan ID: `GPA-V8-CONVERGENCE-PERF`
- Version: `v5`
- Last updated: `2026-04-28 Asia/Shanghai`
- Canonical progress file: `E:\GraduationProject\docs\project-management\TASK_BOOK.md`
- Related handoff file: `none`
- Current branch: `codex/v4-completion`
- Baseline commit: `9177fca`
- Current active phase: `Phase 6: 文档、验证与对外口径同步`
- Execution readiness: `executing`
