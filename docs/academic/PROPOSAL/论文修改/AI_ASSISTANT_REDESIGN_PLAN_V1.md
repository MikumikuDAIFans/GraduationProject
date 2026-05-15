# AI 助手重设计方案 V1 - 从被动 Chatbot 到多智能体个人助手

> 文档状态：drafting  
> 版本：V1  
> 最后更新：2026-04-29  
> 适用范围：后端助手编排、主动触发机制、会话与提案数据模型、前端助手交互层  
> 关联系统：`Vue 3 + Pinia + FastAPI + Celery + Redis + Gemini + LangGraph` 个人事务工作台  
> 当前目标：将现有“被动、弱理解、弱协商”的 AI 助手，重构为“多智能体、可协商、可主动跟进”的个人助手系统
> 实施任务书：`docs/development/AI_ASSISTANT_IMPLEMENTATION_TASK_BOOK_V1.md`

---

## 目录

- [一、问题定义](#一问题定义)
- [二、重设计目标](#二重设计目标)
- [三、目标产品定义](#三目标产品定义)
- [四、现有助手机制的结构性问题](#四现有助手机制的结构性问题)
- [五、新助手总体架构](#五新助手总体架构)
- [六、多智能体职责设计](#六多智能体职责设计)
- [七、核心状态机设计](#七核心状态机设计)
- [八、主动触发与心跳机制](#八主动触发与心跳机制)
- [九、提案与协商模型](#九提案与协商模型)
- [十、数据模型重构建议](#十数据模型重构建议)
- [十一、后端服务与 API 重构建议](#十一后端服务与-api-重构建议)
- [十二、前端交互重构建议](#十二前端交互重构建议)
- [十三、与现有系统模块的衔接方式](#十三与现有系统模块的衔接方式)
- [十四、一期到三期实施路线](#十四一期到三期实施路线)
- [十五、验收标准](#十五验收标准)
- [十六、风险与防失控策略](#十六风险与防失控策略)
- [十七、待参数化问题](#十七待参数化问题)
- [十八、推荐参数化顺序](#十八推荐参数化顺序)

---

## 一、问题定义

当前 AI 助手的主要问题不是“模型不够强”，而是**工作机制与产品定位错位**。

系统名称和原始目标是：

> `基于多智能体的个人助手`

但当前用户体感更接近：

> `一个会调用少量工具、依赖弱规则分类的被动 Chatbot`

这带来了四类核心问题：

1. **理解能力不足**
   - 过于依赖关键词匹配和粗粒度 intent 分类。
   - 大量简单日程表达无法稳定识别。
   - 对模糊请求、复合请求、协商型请求处理能力很弱。

2. **执行逻辑过早**
   - 当前链路容易从“理解一句话”直接跳到“创建一个事件/任务”。
   - 缺乏“先出方案、再确认、再执行”的协商层。

3. **缺乏主动性**
   - 助手几乎完全依赖用户主动发消息。
   - 系统虽然有 reminder scan，但没有形成“带上下文的主动商讨能力”。

4. **多智能体特征不成立**
   - 现有 workflow 更像串行节点，而不是职责清晰的 agent team。
   - 没有稳定的“理解-规划-协商-执行-跟进”分工闭环。

---

## 二、重设计目标

本次重设计不是小修小补，而是对 AI 助手机制进行目标导向的重构。

### 2.1 总目标

将 AI 助手重构为一个：

- 能理解自然语言事务需求
- 能提出多个可执行安排方案
- 能主动发现风险并发起协商
- 能在关键节点要求确认
- 能持续跟进任务推进与日程变化
- 能体现内部多智能体分工

的个人事务助手。

### 2.2 分目标

1. **理解目标**
   - 不再依赖关键词匹配作为主识别路径。
   - 优先通过结构化语义抽取识别用户目标、约束、模糊点。

2. **协商目标**
   - 对模糊请求、冲突请求、风险请求，不直接落库执行。
   - 先提出建议方案，再让用户确认或修改。

3. **主动目标**
   - 引入系统内部心跳机制。
   - 支持按时间间隔、事件累计、风险状态主动与用户互动。

4. **多智能体目标**
   - 将助手拆分为多个内部角色，而不是一个“大而全”单体聊天脑。
   - 每个 agent 只负责一个明确职责。

5. **可落地目标**
   - 在现有 `FastAPI + Celery + Redis + WebSocket + Gemini` 基线之上可渐进实施。
   - 一期必须能在现有代码架构中落地，而不是推倒重来。

---

## 三、目标产品定义

重设计后的 AI 助手，不应再是“命令执行器”，而应定义为：

> 一个围绕用户时间、任务、风险与偏好持续运作的多智能体事务协商系统。

其产品行为应体现为：

- 你提出一句模糊需求，它会先理解并给出方案。
- 你安排不合理，它会主动指出并建议调整。
- 你长时间没推进重要事项，它会主动跟进。
- 它能把“提醒”升级为“协商”，把“聊天”升级为“管理”。

---

## 四、现有助手机制的结构性问题

### 4.1 现有链路的问题

当前典型链路是：

```text
user_message
  -> parse_intent
  -> collect_context
  -> schedule_decision
  -> execute_tools
  -> render_response
```

这个链路的问题在于：

- 它适合工具工作流，不适合个人助手工作流。
- 它把“分类”置于中心，而不是“目标理解”。
- 它把“动作执行”置于协商之前。
- 它几乎没有显式的“等待确认”与“提案跟进”状态。

### 4.2 现有主动能力的问题

当前后台任务集中在：

- 事件提醒
- 出发提醒
- deadline risk
- conflict warnings

这些任务是必要的，但它们还只是：

> 被动提醒系统

而不是：

> 主动协商系统

### 4.3 现有多智能体的问题

当前的 “workflow / react / nodes” 更像：

- 处理节点
- 工具节点
- 条件分支

而不像：

- 理解 agent
- 规划 agent
- 协商 agent
- 执行 agent
- 跟进 agent

因此用户看不到多智能体优势，系统内部也没有形成真正的职责分工。

---

## 五、新助手总体架构

建议将助手系统升级为“两层结构”：

### 5.1 外层：对话与协商总控层

负责：

- 识别对话类型
- 调度内部 agent
- 管理协商状态
- 决定是否主动发起对话
- 汇总结果回复用户

### 5.2 内层：多智能体执行层

由多个专职模块组成，一期实现口径统一为：

- `Conductor`
- `Understanding Specialist`
- `Planning Specialist`
- `Negotiation Specialist`
- `Proposal Manager Specialist`
- `Action Executor`
- `Initiative Specialist`
- `Memory Specialist`

说明：

- 本文前部若仍出现 `Agent` 表述，应理解为职责角色描述。
- 真正进入实现时，以 `Conductor + Specialists + Action Executor` 为唯一规范命名体系。

### 5.3 核心思想

不再把助手视为：

> “一个模型 + 一组工具”

而是视为：

> “一个负责持续管理个人事务的内部团队”

---

## 六、多智能体职责设计

## 6.1 Conductor

角色：总控与编排

职责：

- 决定当前输入属于：
  - 执行请求
  - 查询请求
  - 协商请求
  - 主动触发
  - 跟进请求
- 决定调用哪些 specialist
- 决定最终进入：
  - 直接回复
  - 生成提案
  - 等待确认
  - 执行动作
  - 主动跟进

输入：

- 用户消息
- 当前 thread / proposal / recent context

输出：

- orchestration decision
- target agent set
- user-facing response envelope

---

## 6.2 Understanding Specialist

角色：自然语言目标理解

职责：

- 从自然语言中抽取真正目标，而不是只做粗粒度 intent 分类。
- 输出结构化理解结果：

```json
{
  "request_type": "schedule_request",
  "goal": "安排明天下午去学校上政治课",
  "constraints": {
    "date": "tomorrow",
    "time_range": "afternoon",
    "location": "school",
    "fixed": true
  },
  "missing_fields": [],
  "ambiguities": [
    "结束时间未知"
  ],
  "confidence": 0.84
}
```

关键原则：

- **LLM 结构化抽取为主**
- 规则系统只做 fallback 和安全保护

---

## 6.3 Planning Specialist

角色：事务规划与可行性评估

职责：

- 读取：
  - events
  - tasks
  - profile
  - reminders
  - suggestions
  - weather / travel
- 生成候选方案，而不是直接落库执行

说明：

- 正文中的 `Planning Specialist` 是概念层总称。
- 实现层可继续拆分为：
  - `Task Decomposer`
  - `Calendar Planning Specialist`
  - `Travel Planning Specialist`
  - `Deadline Risk Specialist`
- `Phase 1A` 可先实现一个简化版 `Planning Specialist`，后续再按职责拆分。

候选方案示例：

- 方案 A：按用户请求创建
- 方案 B：后移 30 分钟以避开冲突
- 方案 C：拆成“出发 + 上课 + 复盘”三个块

输出：

```json
{
  "candidates": [
    {
      "id": "plan_a",
      "summary": "...",
      "tradeoffs": ["最贴近原始请求", "有 10 分钟 buffer 风险"],
      "actions": [...]
    }
  ],
  "risk_level": "medium",
  "needs_confirmation": true
}
```

---

## 6.4 Negotiation Specialist

角色：协商与确认

职责：

- 判断当前应直接生成确认 proposal，还是先进入澄清
- 将规划候选方案翻译成用户可理解的表达
- 生成：
  - yes/no 确认
  - 多方案选择
  - 提示修改

边界：

- 所有写操作是否必须确认，由系统硬规则决定
- `Negotiation Specialist` 只负责“怎么确认”和“何时先澄清”
- 不负责决定写操作是否可以跳过确认

典型场景：

- 用户请求模糊
- 时间冲突存在
- 方案存在风险或多种合理安排
- 需要把候选方案组织成用户容易回复的表达

这是新助手区别于旧 Chatbot 的关键层。

---

## 6.5 Action Executor

角色：执行器

职责：

- 接受已确认方案
- 调用 event/task/google/suggestion 相关服务
- 处理落库、副作用、同步状态
- 记录执行回执

原则：

- Action Executor 不负责理解，不负责协商
- 它只做“已确认的动作落地”

---

## 6.6 Initiative Specialist

角色：主动性与心跳代理

职责：

- 周期性扫描用户近期事务状态
- 发现值得主动打扰的情况
- 发出主动协商信号

典型输出：

- 今日计划确认
- 明日任务安排建议
- 冲突修复建议
- deadline 风险协商
- 长任务延期重排建议

---

## 6.7 Memory Specialist

角色：短期与长期记忆管理

职责：

- 保存最近一段时间协商历史
- 管理 pending proposals
- 维护用户偏好记忆
- 提供“为什么系统这次主动找你”的上下文解释

它不是向量库展示层，而是助手连续性保障层。

---

## 七、核心状态机设计

新的助手主状态机不应是“节点流水线”，而应是“协商状态机”。

### 7.1 顶层状态

```text
idle
  -> understanding
  -> planning
  -> negotiating
  -> awaiting_confirmation
  -> executing
  -> followup_tracking
  -> completed
```

### 7.2 状态说明

#### `understanding`
- 理解用户当前目标
- 抽取约束、模糊点、置信度

#### `planning`
- 生成一个或多个候选方案
- 评估冲突与风险

#### `negotiating`
- 向用户解释方案
- 请求选择或补充

#### `awaiting_confirmation`
- 方案已提出，等待用户确认

#### `executing`
- 已确认，开始执行动作

#### `followup_tracking`
- 执行后持续观察
- 进入后续主动跟进

### 7.3 关键分支

1. 明确请求 + 风险低 -> 可直接生成确认 proposal  
2. 模糊请求 -> 进入 negotiation  
3. 冲突请求 -> 进入 negotiation  
4. 主动信号触发 -> 直接进入 planning / negotiating  
5. 长期未确认 proposal -> followup / expire

---

## 八、主动触发与心跳机制

这是系统从“被动助手”变成“主动助手”的关键。

## 8.1 触发源分类

### A. 时间间隔触发

例如：

- 起床后 30 分钟：今日安排确认
- 睡前 30 分钟：日终总结与未完成事项协商
- 每 4 小时：扫描事务风险

### B. 事件累计触发

例如：

- 最近 6 小时新增/修改事件 >= 3
- 某任务连续两次延期
- 高优先任务超过阈值未入日程
- 明日存在大块空白但 deadline 风险上升

### C. 风险触发

例如：

- 冲突出现
- 出发时间风险出现
- deadline 风险出现
- 计划执行率过低

### D. 提案跟进触发

例如：

- 某 pending proposal 超过 2 小时未确认
- 某协商线程被中断太久

---

## 8.2 主动消息等级

建议主动消息分为 4 级：

### 1. `info`
只通知，不要求用户回复

示例：
- 明天 9 点有课，建议 8:35 出发

### 2. `confirm`
需要 yes/no

示例：
- 你今晚还有 2 个高优先任务未安排，要我帮你加入空档吗？

### 3. `negotiate`
给出多个方案

示例：
- 明天下午政治课与复习时间冲突，我整理了 3 个调整方案

### 4. `urgent`
高优先级中断

示例：
- 30 分钟后需要出发，否则将赶不上活动

---

## 8.3 主动触发原则

主动性必须满足三条原则：

1. **有理由**
   - 每次主动发起必须绑定具体 signal

2. **有收益**
   - 主动消息必须帮助用户做出更好安排，而不是刷存在感

3. **有动作**
   - 主动消息必须配套确认、采纳、忽略、延期等操作

---

## 九、提案与协商模型

重设计后的核心对象不再只是 message，而是：

> `proposal`

## 9.1 Proposal 的定义

Proposal 是助手根据上下文生成的一个待决策计划单元。

示例：

- 一次日程安排提案
- 一次任务重排提案
- 一次“今日空档怎么用”的协商提案

### 9.2 Proposal 状态

```text
draft
pending
accepted
execution_pending
execution_failed
rejected
revised
expired
superseded
executed
archived
```

补充说明：

- `accepted` 只代表用户已经确认，不代表动作已经落库。
- 真正执行完成后，proposal 才进入 `executed`。

### 9.3 Proposal 内容

应包含：

- 背景上下文摘要
- 触发原因
- 候选方案列表
- 风险说明
- 建议默认方案
- 可执行动作集

---

## 十、数据模型重构建议

现有 `AssistantSession.context_json` 不适合继续承担全部协商状态。

建议新增以下实体。

说明：

- 本章只描述实体职责与最小语义。
- 正式字段、枚举与约束，以附录 E 为准。

## 10.1 `AssistantProposal`

职责摘要：

- 保存单个目标对应的 proposal
- 保存 proposal 生命周期
- 保存推荐方案、确认结果与执行结果的结构化载体

用途：

- 存储待确认方案
- 让主动协商有独立生命周期

## 10.2 `AssistantSignal`

职责摘要：

- 记录为什么系统主动触发一次交互
- 作为主动协商与 follow-up 的统一输入源

## 10.3 `AssistantThreadState`

职责摘要：

- 保存一次协商链路的上下文容器
- 保存当前 thread 与 proposal 的连续性信息

用途：

- 保存一次协商链路的当前状态

## 10.4 长期偏好记忆说明

V1 中不再单独引入 `AssistantPreferenceMemory` 数据表。

已锁定的一期策略是：

- 长期偏好记忆进入 `preferences.md`
- 长期地点记忆进入 `places.md`
- 长期习惯记忆进入 `habits.md`
- 长期术语映射进入 `glossary.md`

数据库中只保留：

- `AssistantMemoryUpdateCandidate`
- proposal / signal / thread state 等运行时结构

也就是说：

- 偏好记忆的长期存储由 `.md` 记忆层承担
- 数据库负责运行时状态与长期记忆候选更新

---

## 十一、后端服务与 API 重构建议

## 11.1 服务层拆分建议

一期实现建议以 `Conductor + Specialist Registry` 为主骨架组织。

推荐结构：

- `backend/app/assistant_agents/conductor.py`
- `backend/app/assistant_agents/registry.py`
- `backend/app/assistant_agents/contracts.py`
- `backend/app/assistant_agents/specialists/understanding.py`
- `backend/app/assistant_agents/specialists/planning.py`
- `backend/app/assistant_agents/specialists/negotiation.py`
- `backend/app/assistant_agents/specialists/proposal_manager.py`
- `backend/app/assistant_agents/specialists/initiative.py`
- `backend/app/assistant_agents/specialists/memory.py`
- `backend/app/assistant_agents/action_executor.py`

说明：

- 如果一期为了兼容现有工程需要保留 `assistant.py` facade，可在内部逐步映射到上述 registry 结构。
- 不建议长期把实现维持在 `assistant_orchestrator.py / assistant_understanding.py` 这种并列 service 文件模式中。

### 原则

- 不要再把所有能力继续堆在 `assistant.py`
- `assistant.py` 最终应只作为 facade / assembly point

## 11.2 API 建议

### 保留

- `/api/assistant/message`
- `/ws/assistant`
- `/api/assistant/current`
- `/api/assistant/sessions`

### 新增建议

- `/api/assistant/proposals`
- `/api/assistant/proposals/{id}/confirm`
- `/api/assistant/proposals/{id}/reject`
- `/api/assistant/proposals/{id}/revise`
- `/api/assistant/proposals/{id}/retry`
- `/api/assistant/signals`
- `/api/assistant/heartbeat/run`（debug only）

### 11.3 Proposal Confirm 幂等规则

`confirm API` 是 proposal 闭环中最容易产生重复执行风险的入口，因此一期必须明确幂等规则。

规则：

- 同一个 confirmed proposal 只能成功执行一次
- 重复 confirm 不得重复创建任务 / 日程 / 状态写入
- 若 proposal 已 `executed`，再次 confirm 只返回已执行回执
- 若 proposal 处于 `execution_pending`，再次 confirm 不重复执行，只返回当前执行状态
- 若 proposal 处于 `execution_failed`，应改走 `retry API`，而不是继续复用 confirm

### 11.4 Proposal Retry 规则

当 proposal 进入 `execution_failed` 时，一期建议显式提供 retry 入口，而不是让 `confirm` 同时承担“首次执行”和“失败重试”两种语义。

建议接口：

- `POST /api/assistant/proposals/{id}/retry`

规则：

- 只允许 `execution_failed -> execution_pending`
- 不允许 `pending / rejected / expired / superseded / executed` 进入 retry
- retry 时复用已有 `selected_option_id`
- `retry_count + 1`
- 仍需保留最近一次执行错误与本次执行开始时间

### WebSocket 事件建议扩展

- `proposal_created`
- `proposal_updated`
- `signal_created`
- `assistant_followup`

---

## 十二、前端交互重构建议

如果前端仍然只有消息流，用户感知不到“多智能体”和“主动协商”。

建议助手面板增加三个显式区域：

## 12.1 待确认区

显示：

- 当前 pending proposals
- 推荐方案
- 确认 / 修改 / 拒绝

## 12.2 主动建议区

显示：

- 来自 heartbeat 的主动建议
- 标记来源：冲突 / deadline / 明日规划 / 出发提醒

## 12.3 跟进区

显示：

- 正在跟进的任务
- 最近一次系统建议
- 下次计划检查时间

消息流仍保留，但不再承担全部状态承载。

---

## 十三、与现有系统模块的衔接方式

## 13.1 与 Calendar / Tasks 的衔接

新助手不替代现有 CRUD 模块，而是：

- 读取 calendar/tasks 作为上下文
- 通过 proposal 驱动最终执行
- 在确认后调用现有 service 层

## 13.2 与 SuggestionService 的衔接

SuggestionService 不再直接承担“助手方案生成”的全部责任。

建议：

- 保留其时间空档与任务槽位计算能力
- 将其作为 `Planning Specialist` 的子工具
- 不让 suggestion API 本身承担完整协商逻辑

## 13.3 与 Reminder Jobs 的衔接

现有 reminder jobs 可转化为 `Initiative Specialist` 的底层信号输入源。

例如：

- `scan_idle_slot_risks()` -> 产生 `deadline_risk_signal`
- `scan_conflict_warnings()` -> 产生 `conflict_signal`

即：

> reminder job 负责发现  
> `Initiative Specialist` 负责决定是否主动发起协商

---

## 十四、一期到三期实施路线

## Phase 1A：被动 proposal 闭环

目标：

- 助手不再默认直接写入
- 引入 proposal 概念
- 明确区分：
  - 直接出方案
  - 提出方案
  - 等待确认

范围：

- Conductor
- Understanding Specialist
- Task-or-Event Clarifier
- Planning Specialist
- Negotiation Specialist
- Proposal Manager Specialist
- Action Executor

不做：

- 复杂长期主动心跳
- 偏好长期学习闭环

### Phase 1A 内部开发顺序建议

为降低一期实现风险，建议 Phase 1A 在开发时进一步按以下最小顺序推进：

1. `1A-1：单 proposal + 单 option + 手动确认`
2. `1A-2：单 proposal + 多 option`
3. `1A-3：revise 生成新 proposal`
4. `1A-4：接入 Action Executor 真正落库`

说明：

- 这是一条开发顺序建议，不改变前述架构设计边界。
- 这样可以先收稳最小闭环，再逐步补 option、revise 与真实执行。

## Phase 1B：Proposal 工程稳定性

目标：

- proposal 生命周期完整化
- 执行幂等
- 多 proposal 文本指代稳定
- dedup_key 生效

范围：

- `execution_pending / execution_failed`
- confirm 幂等
- dedup_key
- 多 proposal 指代协议
- ThreadState 最小化
- 结构化日志

不做：

- 主动心跳全量上线
- 长期记忆写入自动化闭环

## Phase 2：引入主动触发与心跳

目标：

- 每日规划 ping
- 冲突与风险触发
- proposal follow-up

范围：

- AssistantSignal
- Initiative Specialist
- Celery beat 触发任务
- 前端主动建议区

## Phase 3：形成完整多智能体闭环

目标：

- 引入持续跟进
- 引入偏好记忆
- 引入长期计划协商能力

范围：

- Memory Specialist
- ThreadState
- 主动协商个性化

---

## 十五、验收标准

### 15.1 Phase 1A：被动 proposal 闭环

#### 用例 1：明确日程创建

输入：

- `明天下午三点去学校上政治课`

预期：

- 生成 `event_creation proposal`
- proposal `status = pending`
- 不直接创建 event
- `options` 至少包含 1 个方案
- 用户回复 `可以` 或 `按方案A安排` 后，proposal 进入 `execution_pending`
- 执行成功后，proposal 进入 `executed`

#### 用例 2：模糊任务请求

输入：

- `帮我安排一下复习`

预期：

- 系统判断为 `task_creation` 或 `task_schedule_plan`
- 若关键信息不足，可先澄清或生成低风险 proposal
- 不直接创建多个日程块
- 若用户补充后形成 proposal，仍需等待确认再执行

#### 用例 3：任务/日程类型澄清

输入：

- `这个是任务，不是单次日程`

预期：

- 更新 `Task-or-Event Clarifier` 判断结果
- 原 proposal 若已不再适用，进入 `revised` 或 `superseded`
- 生成新的 task-oriented proposal

### 15.2 Phase 1B：Proposal 工程稳定性

#### 用例 1：重复 confirm 幂等

输入：

- 对同一 proposal 连续两次发送确认

预期：

- 不重复创建 event / task
- 若 proposal 已 `execution_pending`，返回当前执行状态
- 若 proposal 已 `executed`，返回同一个执行结果回执

#### 用例 2：多 proposal 文本指代

输入：

- 当前同时存在 `P1`、`P2`
- 用户回复 `可以`

预期：

- 系统不得猜测指向
- 必须进入澄清，要求用户明确 `P1` 或 `P2`

#### 用例 3：自然语言 revise

输入：

- `改成4点开始`

预期：

- 映射为 `revise(proposal_id, patch=...)`
- 旧 proposal 进入 `revised` 或 `superseded`
- 生成新 proposal，而不是直接覆盖执行

### 15.3 Phase 2：主动触发与心跳

#### 用例 1：deadline 风险触发

输入：

- 某高优先任务未排程且接近 deadline

预期：

- 生成 `AssistantSignal`
- signal 经 `evaluated` 后可生成 `deadline_recovery proposal`
- 不直接改动任务或日程

#### 用例 2：出发前提醒

输入：

- 某外出事件接近 `departure_time`

预期：

- 系统基于保守通勤估算生成提醒
- 提醒文本包含来源、理由和明确回复方式
- 若用户声明 `我已经在学校了`，系统进入重新估算或免出发路径

### 15.4 多智能体链路可观测性

预期：

- 内部日志中可明确区分哪个 specialist / executor 负责理解、规划、协商、执行
- 对外表现出清晰的 `先理解 -> 再建议 -> 再确认 -> 再执行` 链路

---

## 十六、风险与防失控策略

## 16.1 风险：主动打扰过多

防护：

- 为 signal 增加冷却时间
- 同类主动消息短时只允许一次
- 支持用户关闭某类主动建议

## 16.2 风险：协商过度导致行动迟缓

防护：

- 风险低且目标明确时允许直接生成确认 proposal
- 设置明确的“直接出方案阈值”

## 16.3 风险：多智能体过度复杂

防护：

- 一期先做逻辑分层，不必一开始就做真正多模型并行
- “多智能体”先体现为职责拆分，而不是多 LLM 并发

## 16.4 风险：状态散落

防护：

- 把 proposal / signal / thread state 独立建模
- 减少把复杂状态继续堆进 `context_json`

---

## 十七、待参数化问题

当前方案的大方向已经锁定，剩余主要是实现前需要参数化的工程问题。

1. **直接出方案阈值如何配置**
   - 哪些请求允许助手不二次澄清就直接生成 proposal？

2. **pending proposal 默认多久过期**
   - 不同 proposal 类型是否需要不同过期时间？

3. **同类 signal cooldown 默认多久**
   - `deadline_risk / departure_check / night_review_followup` 是否分别配置？

4. **系统主动消息入口如何分级**
   - 助手面板是否为唯一主入口？
   - `urgent` 是否允许 toast / notifications 作为辅助入口？

5. **起床后 / 睡前时间如何从用户习惯中读取**
   - 默认读 `habits.md`
   - 若缺失，是否回退到 profile 或固定默认值？

6. **Phase 2 前的打扰决策规则**
   - 在 `signal + cooldown + dedup + severity` 基础上，
   - 是否补一个轻量 interrupt 决策规则来决定“只记录 / 进入主动建议区 / 生成 proposal”？

7. **Phase 1A 是否按单用户原型边界实现**
   - 若是，哪些记忆与节律策略可以先按单用户假设编码？

---

## 十八、推荐参数化顺序

为了让文档顺畅进入实施草案，建议按以下顺序完成参数化：

1. **Proposal 执行参数**
   - 直接出方案阈值
   - 默认过期时间
   - retry 允许条件

2. **主动系统参数**
   - signal cooldown
   - `urgent` 是否允许 toast
   - Phase 2 前是否补轻量 interrupt 决策规则

3. **作息与节律参数**
   - 起床后 / 睡前窗口的读取来源
   - 默认 safety buffer 与提醒窗口

4. **一期实现边界参数**
   - Phase 1A 是否按单用户原型边界实现
   - 哪些长期记忆写入先只做候选，不做自动落盘

5. **前端展示参数**
   - proposal 摘要长度
   - pending proposal 列表上限
   - 主动建议区与待确认区的默认优先级

---

## 结论

本方案的核心不是“让聊天更聪明”，而是：

> 把 AI 助手从被动问答器，重构成一个围绕时间、任务、风险与偏好持续工作的多智能体协商系统。

这将使系统真正贴近其原始定位：

> `基于多智能体的个人助手`

而不再只是一个被动、呆板、弱理解的 Chatbot。

---

## 附录 A - 2026-04-29 已锁定设计决策

以下决策已经由当前讨论明确锁定，后续实现默认以此为准。

### A.1 执行确认原则

- 系统可以直接生成候选方案。
- 系统不能直接写入任务、日程或状态。
- 所有落库操作都需要用户明确确认，包括：
  - 创建
  - 重排
  - 延期
  - 取消
  - 完成标记

### A.2 直接出方案白名单

- 不再使用“直接执行白名单”术语。
- 统一使用：
  - `直接出方案白名单`
  - `无需二次澄清即可生成候选方案`

### A.3 任务与日程关系

- 任务是父级目标单元。
- 日程是任务的执行切片。
- 独立日程允许存在，不必绑定任务。
- 任务不必立刻拆成日程，但必须处于以下状态之一：
  - `待排程`
  - `已部分排程`
  - `已形成执行切片`

### A.4 创建类请求的策略

- 方案先行，尽量少打扰用户。
- 规划层尽量自行利用上下文生成候选方案。
- 只有在系统无法生成可靠候选方案时，才进入澄清。
- 当系统无法明确事务类型是“任务”还是“一次性日程”时，应直接询问用户。

### A.5 信息齐全定义

- `信息齐全` 不再等于“字段齐全”。
- 统一定义为：
  - 系统已拥有足够上下文，可生成至少一个低风险、可解释、可确认的候选方案。

### A.6 主动触发一期重点

一期优先体现以下四类主动能力：

- 明日安排确认
- 冲突修复建议
- 出发前确认
- deadline 风险协商

### A.7 主动节律

主动触发正式划分为三类：

- 日常节律
  - 起床后 30 分钟：今日安排确认
  - 睡前 30 分钟：日终总结与未完成事项协商
- 事件节律
  - 非出行事件：事件开始前提醒
  - 出行事件：围绕 `departure_time` 提醒
- 风险节律
  - 冲突
  - deadline
  - 未排程高优先任务

### A.8 出发提醒规则

- 出行事件的临行提醒应围绕 `departure_time`，而不是 `event.start_time`。
- 建议公式为：

```text
departure_time = event_start_time - estimated_travel_duration - safety_buffer
```

- 当前已讨论默认安全冗余为 10 分钟，可在后续参数化。

### A.9 记忆体系边界

- `.md` 文件用于长期、低频、可读型记忆：
  - 偏好
  - 常用地点
  - 行为习惯
  - 术语映射
- 数据库用于运行时状态：
  - proposal
  - signal
  - thread state
  - 执行状态

### A.10 天气策略一期边界

- 每日 06:00 拉取今日天气快照并缓存。
- 默认仅使用缓存，不高频调用天气 API。
- 仅在以下情况补拉：
  - 用户明确询问天气
  - 距离上次同步超过 8-10 小时，且即将外出
  - 存在降雨、高温、低温等强相关风险场景

### A.11 出行智能体一期边界

- 一期仅做：
  - 保守估算
  - 出发建议
  - 出发前提醒
  - 高德跳转预留
- 一期不承诺：
  - 精确实时路况优化
  - 实时精确用户位置
  - 未来某时刻精确 ETA

### A.12 一期多智能体实现方式

- 一期采用逻辑分层式多智能体。
- 架构原则：
  - LangGraph Supervisor / 动态路由思维
  - OpenAI Agents SDK 的 tools + handoffs + state 理念
  - skill / specialist registry，可插拔扩展
- 二期再向真正运行时编排式多智能体演进。

### A.12.1 一期术语优先级

为避免主体叙述中的 `Agent` 概念与实施层的 `Specialist` 命名混用，正式锁定以下术语优先级：

- `Conductor`
  - 唯一中控编排者
- `Specialist`
  - 各职责推理模块
- `Action Executor`
  - 非推理型执行模块

说明：

- 主体章节中出现的 `Understanding Agent / Planning Agent / Negotiation Agent / Memory Agent` 等表述，仅作为概念分层说明。
- 一期真正进入实现时，以：
  - `Conductor + Specialists + Action Executor`
  - 为唯一规范命名体系。

### A.13 记忆体系更新机制

- 长期记忆采用 `.md` 文件分层维护。
- 运行时状态采用数据库实体维护。
- 只有 `Memory Specialist` 可以写长期记忆文件。
- 其他 specialist 只能提出“候选记忆更新”，不得直接写入 `.md`。
- 长期记忆建议写入时机：
  - 睡前总结后
  - 用户明确要求“记住这个偏好/地点”后

### A.14 地点记忆粒度

- 一期采用：
  - 主地点
  - 少量子地点
- 不在一期构建过细的地点图谱。

### A.15 出发安全冗余

- 一期默认固定安全冗余为 10 分钟。
- 二期再考虑根据地点、通勤模式、用户习惯动态调整。

### A.16 睡前总结批量确认

- 睡前总结支持批量自然语言确认。
- 用户可通过一段话同时表达：
  - 多个事项已完成
  - 某些事项未完成
  - 某些事项需要顺延

### A.17 Memory Specialist 对外可见性

- `Memory Specialist` 默认仅作为内部机制存在。
- 仅在用户显式要求“记住某个偏好/地点”时，对外说明发生了记忆写入。

### A.18 Proposal 粒度

- 一期采用：
  - `一个 proposal 只对应一个目标`
- 允许中控在一轮对话中同时提出多个 proposal。
- 不采用“一个 proposal 包含多个独立目标”的复杂结构。

### A.19 Partial Accept 策略

- 一期不真正支持复杂 `partial_accept` 执行。
- 若用户一句话中对多个目标分别给出不同处理意见：
  - 中控应拆成多个子 proposal
  - 每个子 proposal 独立进入标准生命周期

### A.20 重复性任务一期边界

- 一期不引入完整 recurrence engine。
- 对重复性任务：
  - 创建一个父任务
  - 一次性生成多个普通日程块
  - 后续主要管理这些日程块
- 父任务中仅保留“重复意图摘要”，不引入复杂 recurrence rule 计算器。

---

## 附录 B - Proposal 生命周期设计 V1

本附录定义助手系统中的 `Proposal` 如何生成、等待、确认、过期、跟进与收尾。

## B.1 Proposal 的核心定位

Proposal 不是一条普通消息，而是：

> 助手围绕某个目标、基于当前上下文提出的待决策计划单元。

它是“规划层”和“执行层”之间的唯一合法桥梁。

也就是说：

- 理解之后不直接执行
- 规划之后不直接落库
- 只有 Proposal 被用户确认，`Action Executor` 才能真正执行

## B.2 Proposal 分类

一期建议至少支持以下 6 类 proposal。

### 1. `event_creation`

用于：

- 创建一次性日程
- 明确是单事件，而不是长期任务

示例：

- 明天下午去学校和同学见面
- 周五晚上去看电影

### 2. `task_creation`

用于：

- 创建任务本体
- 尚未或正在拆分为执行切片

示例：

- 帮我安排一下复习
- 下周前准备答辩

### 3. `task_schedule_plan`

用于：

- 针对已有任务生成执行切片方案
- 将任务安排进未来空档

示例：

- 把这周的复习任务安排进空档
- 给驾校练车拆成每周三的训练块

### 4. `reschedule_plan`

用于：

- 已有日程或任务执行切片需要调整

示例：

- 今天的日程全部往后推
- 这两天复习计划要重排

### 5. `deadline_recovery`

用于：

- deadline 风险修复
- 高优先任务长期未入日程

示例：

- 论文复习还剩 5 小时，但明天就截止

### 6. `daily_review_followup`

用于：

- 睡前总结后，对未完成事项发起次日或后续安排方案

示例：

- 今天没完成的两项任务，是否改到明晚和周末？

## B.3 Proposal 生命周期状态

Proposal 的推荐状态机如下：

```text
draft
  -> pending
  -> accepted
  -> execution_pending
  -> execution_failed
  -> rejected
  -> revised
  -> superseded
  -> expired
  -> executed
  -> archived
```

### 状态定义

#### `draft`
- 内部刚生成，尚未正式推送给用户

#### `pending`
- 已展示给用户，等待用户明确回复

#### `accepted`
- 用户已明确同意方案
- 等待进入执行准备

#### `execution_pending`
- Proposal 已确认
- Action Executor 已接管
- 正在执行或等待执行结果落地

#### `rejected`
- 用户明确拒绝当前方案

#### `revised`
- 用户要求修改
- 当前 proposal 已不再原样执行，但其上下文仍可用于下一轮协商

#### `superseded`
- 被更新版本 proposal 替代

#### `expired`
- 因时间敏感性失效

#### `execution_failed`
- Proposal 已被确认并尝试执行
- 但动作落地失败
- 应保留失败原因，并允许重新协商

#### `executed`
- 已确认且已落库执行

#### `archived`
- 生命周期结束，仅作历史保留

## B.4 Proposal 标准生命周期

一期建议的标准流程如下：

```text
understanding
  -> planning
  -> proposal(draft)
  -> proposal(pending)
  -> user response
      -> accept -> execution_pending -> executed
      -> accept -> execution_pending -> execution_failed
      -> reject -> archived
      -> revise -> superseded + new proposal
      -> ignore -> follow-up / expire
```

## B.5 Proposal 的语义字段说明

本节只描述 Proposal 生命周期需要的语义字段。

正式数据库字段、枚举与约束，以附录 E 为准。

### `payload_json` 建议包含

- 原始目标
- 当前上下文摘要
- 候选方案列表
- 风险说明
- 推荐方案
- 执行动作集

## B.6 时间敏感 proposal 与非时间敏感 proposal

Proposal 必须区分时间敏感性，否则“忽略后怎么处理”会混乱。

### 时间敏感 proposal

示例：

- 明日安排确认
- 即将开始的外出计划
- 当日冲突修复
- 当日 deadline risk

规则：

- 超过有效时间即 `expired`
- 不应无限等待

### 非时间敏感 proposal

示例：

- 长期复习计划
- 长期训练计划
- 一周任务排程草案

规则：

- 可在睡前或次日再次跟进
- 不应立即过期

## B.7 Proposal 过期规则 V1

### 1. `event_creation`

- 若绑定明确自然时间窗口，默认在该时间窗口前过期
- 建议过期时点：
  - `proposal_target_start - 30min`
  - 若早于当前时间，则不再发起

### 2. `task_schedule_plan`

- 非即时型任务，不按分钟过期
- 可保留到：
  - 当日睡前复盘
  - 次日晨间安排确认

### 3. `reschedule_plan`

- 若用于当天调整，建议当天结束前过期
- 若用于未来数日调整，可延续到次日晨间汇总

### 4. `deadline_recovery`

- 若 deadline 在 24 小时内，proposal 高度时间敏感
- 若用户忽略，允许在睡前汇总再次跟进
- 若 deadline 已过，则转为 `expired` 或新的“补救 proposal”

### 5. `daily_review_followup`

- 默认延续到次日晨间计划确认时段
- 次日晨间后若仍未被确认，则：
  - 进入 `superseded`
  - 由新的日计划 proposal 替代

## B.8 用户忽略 proposal 时的行为

用户忽略不是拒绝，也不是接受。

一期建议定义为：

### 忽略的语义

- 当前用户尚未处理
- 不自动落地
- 系统可在合适时机再次跟进

### 忽略后的处理规则

#### 1. 时间敏感 proposal

- 不反复追问
- 等待：
  - 睡前汇总
  - 次日晨间汇总
  - 或直接过期

#### 2. 非时间敏感 proposal

- 允许在下一个总结时机再次带出
- 若被新版 proposal 替代，则旧 proposal 转 `superseded`

## B.9 Proposal 跟进节律 V1

Proposal 跟进不是任意时刻触发，而应挂靠前面已确认的三类节律。

### A. 日常节律

- 起床后 30 分钟
  - 跟进昨日遗留但仍有效的 proposal
  - 生成新的“今日安排 proposal”

- 睡前 30 分钟
  - 跟进白天未确认 proposal
  - 汇总未完成事项并重新协商

### B. 事件节律

- 出行事件以 `departure_time` 为中心
- 非出行事件以 `event_start_time` 为中心
- 若相关 proposal 仍为 pending，应在该时点前主动追问一次

### C. 风险节律

- deadline 风险
- 冲突变化
- 高优先任务长期未排程

若风险状态变化，允许系统生成一个新 proposal 替换旧 proposal。

## B.10 Proposal 与睡前总结的关系

你已经明确：

- 白天不一定有空及时同步状态
- 睡前总结需要承担批量确认与批量改期职责

因此建议定义：

### 睡前总结的职责

1. 汇总今日执行情况
2. 识别未完成事项
3. 对 pending proposal 再次跟进
4. 允许用户批量确认完成与顺延

### 睡前总结中 proposal 的处理

- 若 proposal 涉及今日事项，睡前必须汇总一次
- 若用户此时仍未处理：
  - 时间敏感 proposal -> `expired`
  - 长期 proposal -> 延续到次日晨间

## B.11 Proposal 与次日晨间确认的关系

次日晨间确认不只是“说一遍今天安排”，而是：

- 汇总仍然有效的 pending proposal
- 合并昨日遗留未完成事项
- 生成新的日计划 proposal

因此建议规则：

- 同一目标若已有旧 proposal，晨间新 proposal 生成后：
  - 旧 proposal -> `superseded`
  - 新 proposal -> `pending`

这样不会出现多个并存方案让用户混乱。

## B.12 Proposal 的确认语义

用户的自然语言回复应映射到以下几类动作：

### 1. `accept`

示例：

- 好
- 可以
- 就这样安排
- 按方案一执行

结果：

- `proposal.status = accepted`
- 进入执行

### 2. `reject`

示例：

- 不要
- 先不安排
- 取消这个方案

结果：

- `proposal.status = rejected`

### 3. `revise`

示例：

- 还是改成 4 点开始
- 结束时间延后半小时
- 今天不排，放到周末

结果：

- 当前 proposal -> `revised`
- 生成新 proposal

### 4. `partial_accept`

示例：

- 第一个可以，第二个改到明天

结果：

- 需要拆分 proposal
- 或将 proposal 内部候选方案局部接受，局部重生

一期可先不完全支持复杂的 partial execution，但需要预留数据结构。

## B.13 Proposal 与任务完成判定的关系

已确认的一条重要设计是：

- 任务是父级
- 日程是执行切片
- 可量化任务默认可自动完成

因此：

- 某些 proposal 的执行结果会改变任务状态
- 但任务完成本身仍视作“状态写入”
- 若用户对完成判定有异议，应允许在睡前总结中修正

## B.14 Proposal 生命周期中的统一原则

最终建议锁定以下统一原则：

1. **先生成 proposal，再谈执行**
2. **所有写操作必须基于用户确认**
3. **忽略不等于接受**
4. **时间敏感 proposal 会过期**
5. **长期 proposal 可在睡前/次日晨间再次跟进**
6. **新 proposal 可替代旧 proposal**
7. **proposal 是多智能体协商的核心中间态**

---

## 附录 C - 记忆体系设计 V1

本附录定义多智能体个人助手的一期记忆架构，包括：

- 长期 `.md` 记忆文件
- 数据库中的运行时状态
- Memory Specialist 的读写权限
- 记忆更新流程
- 候选记忆写入规则

## C.1 设计目标

记忆体系的目标不是“什么都记”，而是：

1. 让助手对用户形成连续理解
2. 让多智能体共享稳定背景信息
3. 让长期记忆与运行时状态严格分层
4. 保持记忆可读、可控、可维护

## C.2 记忆总体分层

一期采用两层记忆架构：

### 层 1：长期记忆层（Markdown）

特点：

- 人类可读
- 低频更新
- 长期稳定
- 可被多个 specialist 共享使用

适合存储：

- 偏好
- 常用地点
- 行为习惯
- 特定术语映射

### 层 2：运行时状态层（Database）

特点：

- 高频变化
- 有生命周期
- 结构化可查询
- 支撑协商与执行链路

适合存储：

- proposal
- signal
- thread state
- 当日执行状态
- remind / followup 消费状态

## C.3 一期 Markdown 记忆文件清单

建议在项目中建立：

```text
backend/app/memory/
  preferences.md
  places.md
  habits.md
  glossary.md
```

如果你后续更希望把记忆放在用户工作空间中而不是 `backend/app/` 内部，也可以改到：

```text
data/memory/
```

一期建议先以单用户模式为主，不做复杂多用户记忆隔离目录设计。

## C.4 `preferences.md`

用途：

- 记录用户风格偏好
- 决定系统如何提出方案、何时确认、何时主动协商

建议结构：

```md
# Preferences

## Planning Style
- planning_style: assistant_led
- confirmation_style: always_confirm_before_write
- proposal_style: multiple_options

## Interaction Style
- prefers_system_plan_first: true
- prefers_direct_clarification_when_goal_type_is_ambiguous: true

## Daily Rhythm
- morning_summary_enabled: true
- night_review_enabled: true
- departure_reminder_enabled: true

## Notes
- 用户希望系统先排好方案，用户主要负责确认和修正，而不是自己规划时间。
```

## C.5 `places.md`

用途：

- 保存常说地点与真实地点的映射
- 解决“学校 / 图书馆 / 驾校”类口语地点的语义对齐问题

建议结构：

```md
# Places

## Canonical Places

- 学校
  - canonical_name: 北京大学
  - address: ...
  - coords: ...
  - notes: 默认指主校区

- 图书馆
  - canonical_name: ...
  - address: ...
  - coords: ...
  - notes: 常用自习地点

- 驾校
  - canonical_name: ...
  - address: ...
  - coords: ...
  - notes: 每周三训练

## Aliases
- 学校 -> 北京大学
- 图书馆 -> 某常用图书馆
- 驾校 -> 某训练场
```

### 地点粒度规则

已锁定的一期策略是：

- 主地点
- 少量子地点

即：

- 可以有“学校”
- 可以有“学校图书馆”
- 但不在一期做完整地点图谱

## C.6 `habits.md`

用途：

- 保存用户行为节律与习惯
- 供 Planning / Daily Review / Initiative specialist 使用

建议结构：

```md
# Habits

## Daily Rhythm
- wake_window: 07:00-08:00
- sleep_window: 23:00-24:00

## Work Pattern
- often_no_time_to_mark_completion_during_day: true
- prefers_end_of_day_review: true
- prefers_assistant_led_planning: true

## Travel Pattern
- default_transport_mode: walking
- safety_buffer_minutes: 10

## Notes
- 用户白天可能无法及时同步状态，完成情况核对应尽量放在睡前总结中处理。
```

## C.7 `glossary.md`

用途：

- 记录用户常说词语的特定含义
- 帮助 Understanding Specialist 做语义解释，而不是单纯关键词匹配

建议结构：

```md
# Glossary

- 复习
  - default_type: long_task
  - notes: 默认理解为需拆分为多个执行块的任务，而不是单次日程

- 出去玩
  - default_type: one_off_event
  - notes: 可能触发当天已有安排的重排协商

- 学校
  - refer_to: 北京大学
```

## C.8 数据库运行时状态边界

以下内容明确不进入 `.md`，必须进入数据库：

- `AssistantProposal`
- `AssistantSignal`
- `AssistantThreadState`
- 当日任务/日程执行状态
- proposal 当前状态
- reminder 消费状态
- 今日汇总是否已处理

### 原因

这些信息具有：

- 高频变化
- 时效性
- 结构化查询需求
- 状态机生命周期

不适合通过 Markdown 文件维护。

## C.9 Memory Specialist 的角色与权限

已锁定设计：

> 只有 `Memory Specialist` 可以改 `.md` 长期记忆文件。  
> 其他 specialist 只能提出“候选记忆更新”。

### 这意味着：

#### Understanding Specialist
- 可读 `.md`
- 不可写 `.md`
- 可提交“候选术语映射”

#### Planning Specialist
- 可读 `.md`
- 不可写 `.md`
- 可提交“候选偏好更新”

#### Travel Planning Specialist
- 可读 `.md`
- 不可写 `.md`
- 可提交“候选地点映射更新”

#### Daily Review Specialist
- 可读 `.md`
- 不可写 `.md`
- 可提交“候选习惯总结”

#### Memory Specialist
- 负责审核并写入 `.md`
- 负责冲突处理与格式标准化

## C.10 候选记忆更新机制

一期建议引入“候选更新”概念，而不是实时改 `.md`。

### 候选更新来源

- 用户显式表达：
  - “以后默认把学校当成北大”
  - “记住我更喜欢你先给多个方案”

- 多次重复行为：
  - 多次将“复习”解释成长期任务
  - 多次将“图书馆”映射到同一地点

### 候选更新内容

建议在 DB 中单独保存：

- `memory_update_candidates`

字段建议：

- `id`
- `user_id`
- `memory_type`
- `source_specialist`
- `proposed_change_json`
- `confidence`
- `status`
- `created_at`

状态建议：

- `proposed`
- `confirmed`
- `rejected`
- `written`

## C.11 长期记忆真正写入的时机

已锁定建议如下：

### 允许写入的时机

1. 用户明确要求
   - “记住这个地方”
   - “以后默认按这个风格给我方案”

2. 睡前总结后
   - 系统把当天稳定出现的偏好/地点映射整理成候选
   - Memory Specialist 决定是否写入

### 不应立即写入的情况

- 单次偶然表达
- 低置信度推断
- 与已有记忆冲突但未确认的内容

## C.12 地点记忆更新规则

这是一期很关键的一类记忆。

### 自动候选

当满足以下条件时，可生成地点记忆候选：

- 用户多次使用同一个口语地点名
- 系统多次将其成功映射到同一 canonical place
- 用户未表现出纠正行为

### 直接写入

仅当：

- 用户明确说“记住以后学校就是这里”

### 冲突处理

若出现：

- “学校”曾指 A
- 后来用户又明确表示“学校”指 B

则：

- 不直接覆盖
- 生成冲突候选
- 由 Memory Specialist 或用户确认最终映射

## C.13 偏好记忆更新规则

### 直接写入

用户明确表达：

- “以后先给多个方案”
- “不要直接替我写进日程”
- “我更喜欢你自己先安排”

这类可直接进入 `preferences.md`

### 候选写入

通过多轮交互推断出的偏好，只进入候选层：

- 用户经常否定单一方案，倾向多个方案
- 用户频繁要求系统先排好再看

## C.14 行为习惯记忆更新规则

行为习惯不应由单次事件决定。

### 建议写入条件

- 同类模式连续出现 3 次以上
- 且跨越多个自然日

例如：

- 多次在睡前统一确认完成情况
- 多次在白天不及时更新状态
- 多次偏好 walking 作为出行方式

## C.15 术语映射记忆更新规则

术语映射应比习惯更容易写入，但仍需要保守。

### 可写入条件

- 用户明确口头定义
- 或系统多次映射一致且用户从未纠正

例如：

- “复习”默认是长期任务
- “学校”默认指北大

## C.16 记忆冲突处理

记忆冲突是必须预留的。

### 冲突类型

1. 地点冲突
2. 偏好冲突
3. 习惯冲突
4. 术语映射冲突

### 冲突处理原则

- 不静默覆盖
- 不让多个 specialist 直接改写
- 冲突进入候选层
- 必要时主动询问用户

## C.17 Memory Specialist 的输出形式

已锁定：

- 默认不对外显式“表演”
- 仅作为内部机制存在

但允许在以下场景对外说明：

- 用户明确要求“记住这个”
- 用户要求查看系统记住了什么

### 因此后续可考虑新增：

- `/api/assistant/memory`
- `/api/assistant/memory/refresh`

一期可先不暴露复杂编辑界面。

## C.18 一期记忆体系的统一原则

最终建议锁定以下原则：

1. **长期记忆与运行时状态严格分层**
2. **长期记忆优先可读、稳定、低频更新**
3. **只有 Memory Specialist 能写 `.md`**
4. **其他 specialist 只能提交候选更新**
5. **单次低置信度推断不得直接写长期记忆**
6. **地点、偏好、习惯、术语映射是一期核心记忆类型**
7. **proposal / signal / thread state 严禁存入 `.md`**

## C.19 `.md` 长期记忆的一期适用边界

需要明确：

- `.md` 长期记忆方案适合一期的：
  - 单用户
  - 本地工作台
  - 低频更新
  - 强可读性原型

它不是多用户产品化阶段的最终长期记忆方案。

若系统后续进入：

- 多用户
- 多端同步
- 高频长期记忆写入
- 审计与版本追踪要求增强

则应考虑迁移到：

- versioned memory table
- 或对象存储 + 元数据索引

一期阶段保留 `.md` 的原因是：

- 更容易人工检查
- 更适合研究型原型
- 更容易让 Memory Specialist 的行为可解释

---

## 附录 D - Specialist Registry 与 Conductor 调度设计 V1

本附录定义一期多智能体架构中：

- specialist registry 的组织方式
- Conductor 的按需调度逻辑
- specialist 的输入输出契约
- skill + tool 风格的可插拔扩展方式

目标不是做“固定流程机器”，而是做：

> 一个能够根据用户当前需求、上下文状态、proposal 状态与主动信号，动态选择合适 specialist 的中控式多智能体系统。

## D.1 一期总体调度哲学

已确认的一期方向是：

- 逻辑分层式多智能体
- 中控主智能体按需调用 specialist
- 不采用死板的固定流水线
- 后续可向更强的运行时编排式多智能体演进

因此一期的调度哲学建议正式定义为：

### 1. `Conductor owns orchestration`

Conductor 是唯一负责：

- 阅读输入
- 判断当前问题类型
- 选择 specialist
- 决定是澄清、提案、跟进还是执行

的中控实体。

### 2. `Specialists own specialized reasoning`

每个 specialist 只负责自己明确的职责领域：

- 理解
- 任务/日程判断
- 拆分
- 排程
- 协商
- 出行
- 睡前复盘
- 风险分析
- 记忆维护

### 3. `Proposal is the only execution gateway`

无论 specialist 怎么推理，最终都不能绕开 proposal：

- specialist 负责给出 reasoning / plan / signal
- Conductor 负责决定是否形成 proposal
- Action 执行必须以用户确认过的 proposal 为前提

## D.2 一期 Specialist 正式名单

建议将一期 specialist registry 正式锁定为以下 10 个：

### 1. `Understanding Specialist`

角色：

- 理解自然语言目标

负责：

- 抽取 request type
- 抽取 goal、constraints、ambiguities
- 给出理解置信度

---

### 2. `Task-or-Event Clarifier`

角色：

- 判断当前表达更像一次性日程还是长期任务

负责：

- 识别“这是事件还是任务”
- 无法明确时发起类型澄清

---

### 3. `Task Decomposer`

角色：

- 将长期任务拆成执行切片思路

负责：

- 判断任务是否需要拆分
- 给出执行节奏建议
- 输出建议性的 focus block 结构

---

### 4. `Calendar Planning Specialist`

角色：

- 将目标安排进日历空档

负责：

- 查找空档
- 检查冲突
- 生成候选排程方案

---

### 5. `Negotiation Specialist`

角色：

- 把内部方案翻译为可与用户协商的自然语言提案

负责：

- 组织多个候选方案
- 解释理由与取舍
- 生成用户确认所需的话术

---

### 6. `Travel Planning Specialist`

角色：

- 处理地点、通勤、出发建议、天气背景

负责：

- origin / destination 推断
- 通勤时间保守估算
- departure suggestion
- 高德跳转预留

---

### 7. `Daily Review Specialist`

角色：

- 睡前总结与日终协商

负责：

- 汇总已完成 / 未完成日程
- 识别未标记完成情况
- 生成顺延和次日安排建议

---

### 8. `Deadline Risk Specialist`

角色：

- deadline 风险与高优先事项未排程风险分析

负责：

- 判断任务是否接近不可行
- 生成补救 proposal 候选

---

### 9. `Proposal Manager Specialist`

角色：

- proposal 生命周期守门人

负责：

- proposal 创建
- proposal 替换
- proposal 过期
- 用户回复映射为 accept / reject / revise

说明：

这是一期建议新增的 specialist，因为 proposal 已是系统中枢对象，不宜让 Conductor 直接手写全部生命周期逻辑。

---

### 10. `Memory Specialist`

角色：

- 唯一长期记忆写入者

负责：

- 处理候选记忆更新
- 写入 `.md` 长期记忆
- 冲突解决

## D.3 Specialist Registry 的组织方式

一期建议按“skill + tool registry”风格组织，而不是硬编码在一个大文件中。

### 建议结构

```text
backend/app/assistant_agents/
  conductor.py
  registry.py
  contracts.py
  specialists/
    understanding.py
    task_or_event_clarifier.py
    task_decomposer.py
    calendar_planner.py
    negotiation.py
    travel_planner.py
    daily_review.py
    deadline_risk.py
    proposal_manager.py
    memory.py
```

### registry 的职责

- 注册 specialist
- 提供 specialist 元信息
- 提供可调用能力列表
- 支持后续热插拔扩展

## D.4 Specialist 元信息模型

每个 specialist 建议至少声明以下元信息：

```python
{
  "name": "travel_planning",
  "version": "v1",
  "responsibility": "travel estimation and departure planning",
  "triggers": ["event_creation", "event_context", "departure_followup"],
  "reads_memory": ["places.md", "habits.md"],
  "writes_memory": [],
  "uses_tools": ["amap.geocode", "amap.route", "weather.cached"],
  "output_type": "specialist_result"
}
```

这样可以非常自然地往你喜欢的“skill + tool 配置化、即插即用”方向演进。

## D.5 Conductor 的职责边界

Conductor 不是“全知全能模型”，它只负责编排。

### Conductor 负责

- 接受用户输入或系统主动 signal
- 构造当前 orchestration context
- 按需选择 specialist
- 决定当前流程进入：
  - clarify
  - propose
  - followup
  - execute
  - archive

### Conductor 不负责

- 自己做全部细节推理
- 自己写长期记忆
- 自己实现 proposal 生命周期细节
- 自己直接执行数据写入

## D.6 Conductor 的输入上下文

Conductor 在一期至少需要读取以下内容：

- 当前用户输入
- 当前活跃 session / thread
- 当前 pending proposals
- 最近 signals
- profile
- today / tomorrow events
- active tasks
- 长期记忆摘要

建议统一封装为：

```json
{
  "user_input": "...",
  "trigger_source": "user_message | heartbeat | reminder | followup",
  "active_thread": {...},
  "pending_proposals": [...],
  "recent_signals": [...],
  "profile_summary": {...},
  "memory_summary": {...}
}
```

## D.7 Conductor 的顶层输出

Conductor 顶层只应输出以下几类结果之一：

### 1. `clarification_request`

表示当前需要问用户问题，但还不足以进入 proposal。

### 2. `proposal_bundle`

表示当前已形成一个或多个独立 proposal，需要交给用户确认。

### 3. `followup_message`

表示当前是对已有 proposal / 风险 / 日终总结的跟进。

### 4. `execution_ready`

表示用户已经确认，允许交给 Action 层执行。

### 5. `memory_update_candidate`

表示这次交互提炼出了可更新的长期记忆候选。

## D.8 Specialist 输入输出契约 V1

一期建议每个 specialist 都使用统一的 contract 风格。

### 输入 Contract

```python
class SpecialistInput:
    user_id: str
    user_message: str | None
    trigger_source: str
    profile: dict
    memory_summary: dict
    events: list
    tasks: list
    proposals: list
    signals: list
    thread_state: dict | None
```

### 输出 Contract

```python
class SpecialistResult:
    specialist_name: str
    confidence: float
    result_type: str
    summary: str
    payload: dict
    suggested_next_step: str
```

### 这样做的好处

- 后续 specialist 可插拔
- Conductor 可以统一消费结果
- 不会变成每个 specialist 自说自话的混乱格式

## D.9 Conductor 的按需调用逻辑 V1

Conductor 不应固定调用全部 specialist，而应根据当前问题类型做动态路由。

### 典型用户输入分类与 specialist 选择

#### 场景 A：模糊创建请求

示例：

- “我要去约会”

建议调用：

1. `Understanding Specialist`
2. `Task-or-Event Clarifier`
3. 若目标和关键信息不足 -> 输出 `clarification_request`

说明：

此类场景不应直接进入 proposal。

#### 场景 B：较明确的一次性日程请求

示例：

- “明天下午 3 点我要去学校和同学见面”

建议调用：

1. `Understanding Specialist`
2. `Task-or-Event Clarifier`
3. `Calendar Planning Specialist`
4. `Travel Planning Specialist`
5. `Negotiation Specialist`
6. `Proposal Manager Specialist`

输出：

- 一个 `event_creation` proposal

#### 场景 C：长期任务请求

示例：

- “帮我安排一下复习”

建议调用：

1. `Understanding Specialist`
2. `Task-or-Event Clarifier`
3. `Task Decomposer`
4. `Calendar Planning Specialist`
5. `Negotiation Specialist`
6. `Proposal Manager Specialist`

输出：

- `task_creation`
- 以及后续 `task_schedule_plan` proposal 候选

#### 场景 D：日程冲突/大范围调整

示例：

- “推迟今天所有日程，我今天要出去玩”

建议调用：

1. `Understanding Specialist`
2. `Calendar Planning Specialist`
3. `Negotiation Specialist`
4. `Proposal Manager Specialist`

输出：

- 一个或多个 `reschedule_plan` proposal

#### 场景 E：睡前总结

触发源：

- heartbeat

建议调用：

1. `Daily Review Specialist`
2. `Deadline Risk Specialist`
3. `Proposal Manager Specialist`
4. `Memory Specialist`（候选记忆更新）

输出：

- 汇总消息
- 若有需要，生成新的 followup proposal

#### 场景 F：deadline 风险

触发源：

- risk signal

建议调用：

1. `Deadline Risk Specialist`
2. `Calendar Planning Specialist`
3. `Negotiation Specialist`
4. `Proposal Manager Specialist`

输出：

- `deadline_recovery` proposal

## D.10 Conductor 的决策顺序建议

一期建议 Conductor 使用以下顺序做决策：

### Step 1：识别触发源

- 用户消息
- 晨间 heartbeat
- 睡前 heartbeat
- 出发前提醒
- 冲突信号
- deadline 风险信号

### Step 2：识别目标类型

- event
- task
- review
- followup
- risk handling
- memory update

### Step 3：判断当前最优路径

四选一：

- `clarify`
- `propose`
- `followup`
- `execute`

### Step 4：组装对用户输出

- 一条 clarification
- 一个或多个 proposal
- 一条跟进汇总
- 或执行回执

## D.11 Conductor 的硬规则

为了防止系统行为漂移，一期建议明确以下硬规则：

1. 若尚未形成可靠候选方案，不允许进入执行
2. 若目标类型不明确，优先调用 `Task-or-Event Clarifier`
3. 若涉及外出或地点变化，优先调用 `Travel Planning Specialist`
4. 若涉及长期任务，优先调用 `Task Decomposer`
5. 所有 proposal 生命周期变更统一交给 `Proposal Manager Specialist`
6. 所有长期记忆写入统一交给 `Memory Specialist`

## D.12 Proposal Manager Specialist 的特殊地位

Proposal 已经被锁定为核心中间态，因此 `Proposal Manager Specialist` 需要被视为一期的关键基础 specialist。

其职责建议包括：

- 创建 proposal 记录
- 标记 proposal 状态
- 识别 superseded / expired
- 将用户确认回复映射为 lifecycle action
- 将批量自然语言回复拆成多个子 proposal 动作

它不是执行器，而是状态机管理员。

并且职责边界进一步锁定为：

- `Negotiation Specialist`
  - 负责“怎么说”
  - 把内部方案翻译成用户可读的话术

- `Proposal Manager Specialist`
  - 负责“状态怎么变”
  - 创建、替换、过期、确认映射、重试控制

## D.13 Skill + Tool 即插即用扩展方式

你特别强调希望向：

- `skill + tool`
- 灵活调整
- 即插即用

方向探索。

一期建议这样组织：

### skill

表示：

- specialist 的职责封装
- 包含触发条件、输入输出契约、可读记忆、可用工具说明

### tool

表示：

- 具体外部能力或内部 service 接口

例如：

- `tool: event_service.create_proposal_candidate`
- `tool: suggestion_service.compute_slots`
- `tool: amap.geocode`
- `tool: amap.route_estimate`
- `tool: weather.cached_snapshot`

### 注册方式

specialist 不直接写死工具调用，而是在元信息中声明其依赖工具。

这样未来新增一个 specialist，例如：

- `Study Rhythm Specialist`
- `Nutrition Break Specialist`

只需要：

1. 定义 skill 元信息
2. 注册它
3. 给 Conductor 新增 trigger condition

即可接入。

## D.14 与现有代码结构的映射建议

为了降低重构风险，一期可以采取“平滑包裹式”接入，而不是推倒旧 service。

### 现有代码可继续复用

- `EventService`
- `TaskService`
- `SuggestionService`
- `ContextService`
- `GoogleCalendarService`
- `jobs/reminders.py`

### 新层只负责编排

也就是说：

- specialist 负责 reasoning / proposal / routing
- 旧 service 继续负责 CRUD / API / tool 调用

这样能最大化利用已有系统沉淀。

## D.15 一期 Specialist Registry 的统一原则

最终建议锁定以下原则：

1. **Conductor 只负责编排，不负责所有专业推理**
2. **specialist 只负责单一职责领域**
3. **所有 specialist 使用统一输入输出契约**
4. **proposal 是 specialist 输出到执行层的唯一桥梁**
5. **registry 要支持新增 specialist 的即插即用**
6. **一期按需路由，不采用全量 specialist 固定流水线**
7. **Conductor + Proposal Manager + Memory Specialist 构成控制骨架**

---

## 附录 E - 数据模型与 API 设计 V1

本附录将前面已确认的机制翻译成可实现的数据结构与接口蓝图。

目标：

- 明确新增哪些数据库实体
- 明确各实体字段与状态枚举
- 明确哪些 API 需要新增
- 明确 WebSocket 事件如何扩展
- 明确新模型如何与现有 `events / tasks / assistant / reminders` 链路衔接

## E.1 设计原则

一期数据与接口设计遵从以下原则：

1. **不推翻现有 `Task / Event / AssistantSession / Reminder`**
2. **新增实体只承接新的协商、主动性、记忆候选与线程状态能力**
3. **proposal 是执行前唯一正式中间态**
4. **signal 是主动触发与风险触发的统一输入单元**
5. **thread state 用于维持一次协商链路的连续性**
6. **长期 `.md` 记忆不直接暴露复杂编辑接口**

## E.2 新增数据库实体总览

一期建议新增以下 4 类核心实体：

1. `AssistantProposal`
2. `AssistantSignal`
3. `AssistantThreadState`
4. `AssistantMemoryUpdateCandidate`

其中：

- `AssistantProposal` 是系统中枢实体
- `AssistantSignal` 是主动触发输入源
- `AssistantThreadState` 是协商状态持有者
- `AssistantMemoryUpdateCandidate` 是长期记忆更新候选池

## E.3 `AssistantProposal`

### 定位

保存：

- 某个具体目标对应的单个 proposal
- proposal 的生命周期状态
- proposal 与用户、session、任务、日程的关联

### 建议字段

- `id: int`
- `user_id: str`
- `session_id: int | None`
- `thread_state_id: int | None`
- `proposal_type: str`
- `trigger_type: str`
- `status: str`
- `dedup_key: str | None`
- `priority: int`
- `summary: str`
- `payload_json: dict`
- `recommended_option_id: str | None`
- `selected_option_id: str | None`
- `is_time_sensitive: bool`
- `related_task_id: int | None`
- `related_event_id: int | None`
- `source_signal_id: int | None`
- `supersedes_proposal_id: int | None`
- `expires_at: datetime | None`
- `followup_after: datetime | None`
- `confirmed_at: datetime | None`
- `execution_started_at: datetime | None`
- `execution_error: str | None`
- `executed_at: datetime | None`
- `archived_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

### `proposal_type` 建议枚举

- `event_creation`
- `task_creation`
- `task_schedule_plan`
- `reschedule_plan`
- `deadline_recovery`
- `daily_review_followup`

### `trigger_type` 建议枚举

- `user_message`
- `morning_heartbeat`
- `night_review`
- `departure_followup`
- `conflict_signal`
- `deadline_signal`
- `manual_followup`

### `status` 建议枚举

- `draft`
- `pending`
- `accepted`
- `execution_pending`
- `execution_failed`
- `rejected`
- `revised`
- `superseded`
- `expired`
- `executed`
- `archived`

### 关键约束

- 一期遵循：**一个 proposal 只对应一个目标**
- 允许一轮对话中生成多个 proposal
- 一个新 proposal 可通过 `supersedes_proposal_id` 指向被替代 proposal
- proposal 的结构化确认对象始终是 `option_id`，而不是模糊的“整条 proposal”

## E.4 `AssistantSignal`

### 定位

保存：

- 主动触发信号
- 风险信号
- proposal 跟进信号

### 建议字段

- `id: int`
- `user_id: str`
- `signal_type: str`
- `severity: str`
- `status: str`
- `dedup_key: str | None`
- `target_type: str | None`
- `target_id: int | None`
- `context_json: dict | None`
- `source_job: str | None`
- `cooldown_until: datetime | None`
- `evaluated_at: datetime | None`
- `proposal_created_at: datetime | None`
- `dismissed_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

### `signal_type` 建议枚举

- `morning_plan_ping`
- `night_review_ping`
- `departure_check`
- `event_conflict`
- `deadline_risk`
- `unscheduled_high_priority_task`
- `pending_proposal_followup`

### `severity` 建议枚举

- `info`
- `confirm`
- `negotiate`
- `urgent`

### `status` 建议枚举

- `new`
- `evaluated`
- `proposal_created`
- `cooling`
- `dismissed`
- `expired`

### `status` 语义说明

- `new`
  - signal 刚生成，尚未被 Conductor / Initiative 评估
- `evaluated`
  - 已被评估，但当前未转成 proposal
- `proposal_created`
  - 已基于该 signal 生成 proposal
- `cooling`
  - 当前处于冷却期，不再重复触发
- `dismissed`
  - 用户或系统明确忽略
- `expired`
  - 已失去时效性

### 作用

- `Initiative Specialist` 读 signal 决定是否发起主动交互
- Proposal Manager 可基于 signal 生成 proposal
- signal 生命周期不等于 proposal 生命周期，两者分别维护

## E.5 `AssistantThreadState`

### 定位

保存一次协商链路的连续状态。

例如：

- 正在讨论某个复习任务
- 正在围绕一次延期进行多轮协商
- 正在睡前批量核对完成情况

### 一期边界说明

`AssistantThreadState` 一期保持轻量，不作为第二套核心业务状态机。

它只负责：

- 保存当前协商链路的最近上下文
- 保存最近一次 specialist 结果
- 保存当前等待用户的最小状态

它不负责：

- 重复维护 proposal 全生命周期
- 取代 proposal 作为核心业务状态载体

硬规则：

- `ThreadState.status` 不得用于判断 proposal 是否可执行
- proposal 是否允许执行，只看 `AssistantProposal.status`

也就是说，一期的核心业务状态仍然是：

- `Proposal`

而 `ThreadState` 只是其协商连续性的辅助状态。

### 建议字段

- `id: int`
- `user_id: str`
- `session_id: int | None`
- `thread_type: str`
- `status: str`
- `related_task_id: int | None`
- `related_event_id: int | None`
- `active_proposal_id: int | None`
- `state_json: dict`
- `is_waiting_user: bool`
- `last_specialist: str | None`
- `last_user_message_at: datetime | None`
- `last_system_message_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

### `thread_type` 建议枚举

- `task_planning`
- `event_planning`
- `reschedule_negotiation`
- `daily_review`
- `deadline_recovery`
- `departure_followup`

### `status` 建议枚举

- `active`
- `waiting_user`
- `resolved`
- `superseded`
- `expired`

### 作用

- 让多轮协商保持上下文连续
- 避免所有状态都堆进 `AssistantSession.context_json`

## E.6 `AssistantMemoryUpdateCandidate`

### 定位

保存长期记忆候选写入项。

### 建议字段

- `id: int`
- `user_id: str`
- `memory_type: str`
- `source_specialist: str`
- `status: str`
- `confidence: float`
- `proposed_change_json: dict`
- `reason: str | None`
- `written_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

### `memory_type` 建议枚举

- `preferences`
- `places`
- `habits`
- `glossary`

### `status` 建议枚举

- `proposed`
- `confirmed`
- `rejected`
- `written`

## E.7 与现有表的衔接方式

### 与 `Task`

- `AssistantProposal.related_task_id`
- `AssistantThreadState.related_task_id`
- `AssistantSignal.target_type = task`

### 与 `Event`

- `AssistantProposal.related_event_id`
- `AssistantThreadState.related_event_id`
- `AssistantSignal.target_type = event`

### 与 `AssistantSession`

- `AssistantProposal.session_id`
- `AssistantThreadState.session_id`

### 与 `Reminder`

- Reminder 仍负责传统提醒
- AssistantSignal 负责主动协商触发
- 两者关系是：
  - `Reminder` 偏“通知”
  - `Signal` 偏“协商输入”

## E.8 是否需要扩展现有 `Task` 模型

建议一期只做轻量扩展，不重做任务模型。

### 可选新增字段

- `planning_status: str | None`
  - `pending_schedule`
  - `partially_scheduled`
  - `has_execution_blocks`
  - `done`

- `completion_mode: str | None`
  - `quantitative`
  - `manual_confirmation`

- `goal_summary: str | None`
  - 用于保存长期任务意图摘要

### 原因

你已经确认：

- 不是所有任务都要立刻拆
- 可量化任务可自动完成
- 结果型任务需要用户确认完成

这些信息值得落在任务模型上，而不仅靠推理。

## E.9 是否需要扩展现有 `Event` 模型

一期建议尽量少动 `Event`。

可选新增字段：

- `proposal_origin_id: int | None`
- `execution_role: str | None`
  - `standalone_event`
  - `task_execution_block`
  - `travel_block`
  - `review_block`

### 说明

如果不想修改现有 `Event` 表，也可以仅通过：

- `event_type`
- `linked_task_id`

来表达一期语义。

## E.10 后端 API 设计 V1

一期建议在现有 `/api/assistant` 下新增 proposal / signal / memory 相关接口。

### 1. Proposal API

#### `GET /api/assistant/proposals`

用途：

- 查看当前用户的 proposal 列表
- 支持筛选：
  - `status`
  - `proposal_type`
  - `time_sensitive`

#### `GET /api/assistant/proposals/{proposal_id}`

用途：

- 查看单个 proposal 详情

#### `POST /api/assistant/proposals/{proposal_id}/confirm`

用途：

- 用户明确确认 proposal 中的某个 option
- Action Executor 进入执行准备

建议请求体：

```json
{
  "option_id": "A"
}
```

#### `POST /api/assistant/proposals/{proposal_id}/reject`

用途：

- 用户明确拒绝 proposal

#### `POST /api/assistant/proposals/{proposal_id}/revise`

用途：

- 用户要求修改 proposal
- 由 Proposal Manager 生成新 proposal

#### `POST /api/assistant/proposals/{proposal_id}/expire`

用途：

- 管理员或系统内部调试接口
- 正常用户流程不一定暴露

### 2. Signal API

#### `GET /api/assistant/signals`

用途：

- 查看最近的 signal
- 支持 debug / 可视化使用

#### `POST /api/assistant/signals/{signal_id}/consume`

用途：

- 仅作为内部或调试接口
- 一期正式状态建议优先使用：
  - `evaluated`
  - `proposal_created`

#### `POST /api/assistant/heartbeat/run`

用途：

- debug only
- 手动触发 heartbeat 检查

### 3. Memory API

#### `GET /api/assistant/memory`

用途：

- 返回长期记忆摘要
- 不必一次把所有 `.md` 原文都抛给前端

#### `GET /api/assistant/memory/candidates`

用途：

- 查看候选记忆更新

#### `POST /api/assistant/memory/candidates/{id}/confirm`

用途：

- 确认候选记忆写入

#### `POST /api/assistant/memory/candidates/{id}/reject`

用途：

- 拒绝候选写入

## E.11 Assistant Message API 的新职责

现有：

- `/api/assistant/message`
- `/ws/assistant`

后续仍保留，但职责要升级：

### 不再只是“给回复”

而是：

- 接受用户自然语言
- 交给 Conductor
- 动态调度 specialist
- 返回以下类型之一：
  - clarification
  - proposal summary
  - followup message
  - execution result

### 也就是说：

- proposal 仍可通过纯文本消息链路触发和确认
- proposal API 更多承担结构化读取与调试用途

这和你想要的“尽量纯文本交互”是一致的。

## E.12 WebSocket 事件设计 V1

一期建议在现有通知体系中新增以下事件类型。

### 1. `proposal_created`

字段建议：

- `type`
- `proposal_id`
- `proposal_type`
- `summary`
- `priority`

### 2. `proposal_updated`

字段建议：

- `type`
- `proposal_id`
- `status`
- `updated_at`

### 3. `signal_created`

字段建议：

- `type`
- `signal_id`
- `signal_type`
- `severity`

### 4. `assistant_followup`

字段建议：

- `type`
- `thread_type`
- `summary`
- `proposal_ids`

### 5. `memory_candidate_created`

字段建议：

- `type`
- `candidate_id`
- `memory_type`
- `summary`

## E.13 与前端纯文本交互的接口策略

你已经明确希望尽量采用纯文本交互，不依赖内嵌按钮。

因此建议：

### 用户层主通道

- 仍是消息输入框
- proposal 的确认、拒绝、修改主要依赖自然语言

### 结构化接口层

- proposal API
- signal API
- memory candidate API

主要用于：

- 调试
- 状态同步
- 前端辅助展示

### 这样做的好处

- 不强迫用户点击卡片按钮
- 保留系统内部结构化状态
- 兼顾“像聊天”与“可工程化”

## E.14 自然语言确认与结构化状态的映射关系

一期建议由 `Proposal Manager Specialist` 负责将自然语言映射为结构化 proposal action。

例如：

- “好，就这样”
  -> `confirm(proposal_id)`

- “改成四点开始”
  -> `revise(proposal_id, patch=...)`

- “这个不要，另外一个可以”
  -> 拆解为多个子 proposal action

### 一期原则

- 前端不要求强制按钮
- 后端必须有明确的结构化状态变更逻辑

## E.14.1 Proposal Option 标准结构

为了避免“用户确认的是 proposal 还是方案”不清楚，一期建议固定 `payload_json.options` 结构。

建议格式：

```json
{
  "goal": {
    "raw_text": "",
    "normalized_goal": "",
    "goal_type": "event | task | reschedule | review"
  },
  "context": {
    "related_events": [],
    "related_tasks": [],
    "memory_used": [],
    "signals": []
  },
  "options": [
    {
      "option_id": "A",
      "title": "",
      "description": "",
      "risk_level": "low | medium | high",
      "tradeoffs": [],
      "actions": []
    }
  ],
  "recommended_option_id": "A",
  "confirmation": {
    "required": true,
    "allowed_replies": ["accept", "reject", "revise"]
  }
}
```

关键原则：

- 用户确认的是 `option_id`
- proposal 是该组候选方案的业务外壳

## E.14.2 Proposal 执行快照结构

一期不强制新增独立的 `AssistantActionExecution` 表，但建议在 `payload_json.execution` 中保留最小执行快照。

建议格式：

```json
{
  "execution": {
    "status": "pending | success | failed",
    "selected_option_id": "A",
    "attempts": [
      {
        "attempt_no": 1,
        "started_at": "",
        "finished_at": "",
        "result_summary": "",
        "error": null
      }
    ],
    "last_error": null
  }
}
```

作用：

- 支撑 confirm 幂等
- 支撑失败重试
- 在不新增新表的前提下保留最小执行审计信息

## E.15 与现有提醒扫描任务的关系

现有 `jobs/reminders.py` 不应被废弃，而应作为主动协商的底层发现器。

### 建议分工

- `jobs/reminders.py`
  - 负责发现风险与时间点
  - 产生 `AssistantSignal`

- `Initiative / Conductor`
  - 读取 signal
  - 决定是否生成 proposal / followup

这能最大化利用现有代码基础。

## E.16 一期落地时的最小表集建议

如果想控制一期复杂度，我建议最少先上：

1. `AssistantProposal`
2. `AssistantSignal`
3. `AssistantThreadState`

`AssistantMemoryUpdateCandidate` 可以和记忆体系一起进入一期后半段，或者一期末尾。

### 原因

proposal / signal / thread state 是协商系统的最小闭环。

## E.17 数据模型与 API 的统一原则

最终建议锁定以下原则：

1. **proposal 是执行前唯一正式中间态**
2. **signal 是主动性触发的统一输入源**
3. **thread state 保存多轮协商连续性**
4. **长期记忆候选与长期记忆写入必须分离**
5. **消息接口负责自然语言入口，proposal API 负责结构化状态承载**
6. **一期尽量增量接入，不推倒现有 events/tasks/services**

---

## 附录 F - 前端纯文本交互协议 V1

本附录定义在“尽量纯文本交互”的前提下：

- 助手如何向用户呈现 proposal
- 晨间汇报与睡前复盘的文本格式
- 用户如何通过自然语言完成确认、修改、拒绝、批量完成同步
- 前端如何在不依赖按钮的情况下仍保持交互清晰

## F.1 设计目标

你已经明确希望：

- 主要通过纯文本与智能体交互
- 不强依赖内嵌按钮
- 用户主要负责确认与修正，而不是自己手动规划

因此纯文本交互协议必须满足：

1. **读起来像自然对话**
2. **结构足够清晰，便于用户快速确认**
3. **便于后端把自然语言回复映射成 proposal action**
4. **支持批量确认与批量改期**

## F.2 前端助手面板的最小结构

即使主交互是文本，前端仍然需要最小限度的结构区分。

一期建议助手面板分为三个视觉区，但全部以文本承载：

### 1. `当前对话区`

用于：

- 用户与 Conductor 的来回文本交互
- proposal 的正文展示

### 2. `当前待确认事项区`

用于：

- 轻量列出当前 pending proposal 摘要
- 不必须是按钮，可以只是文本标题 + 状态

### 3. `主动跟进区`

用于：

- 晨间汇报
- 睡前复盘
- 风险跟进

### 说明

即便用户主要通过文本回复，前端仍要让他一眼看出：

- 现在系统是在提案
- 还是在总结
- 还是在要求确认

## F.3 Proposal 文本协议 V1

一期建议每个 proposal 的正文都遵循统一结构。

### 标准结构

```text
[结论]
我为你整理了一个关于「X」的安排方案。

[原因]
我这样安排，是因为……

[方案]
方案 A：……
方案 B：……
方案 C：……

[建议]
我更推荐方案 B，因为……

[你可以这样回复我]
- “按方案B安排”
- “把开始时间改到4点”
- “先不要安排”
```

### 作用

- 让用户知道现在是在讨论 proposal
- 给用户明确回复范式
- 降低纯文本交互歧义

## F.4 一次性日程 Proposal 模板

### 模板

```text
我为你整理了一个关于「明天下午去学校和同学见面」的安排方案。

考虑到你明天下午已有的日程、去学校的通勤时间，以及你通常的安排节奏，我整理了这几个可选项：

方案 A：15:00 - 16:00，在学校见面，建议提前 10 分钟出发。
方案 B：15:00 - 16:30，在学校见面，建议提前 10 分钟出发。

我更推荐方案 B，因为它给见面预留的时间更从容，而且和你现有安排冲突更少。

你可以直接回复我：
- “按方案B安排”
- “改成4点开始”
- “结束时间缩短到1小时”
- “先不要安排”
```

## F.5 长期任务 Proposal 模板

### 模板

```text
我把「复习」理解成一个需要持续推进的任务，而不是一次性日程。

为了让它更容易执行，我建议先把它拆成几个可安排的学习块。基于你这周的空档，我整理了一个初步方案：

方案 A：
- 周三晚上：复习 1 小时
- 周四下午：复习 1.5 小时
- 周六上午：复习 2 小时

方案 B：
- 周三晚上：复习 1.5 小时
- 周五晚上：复习 1.5 小时
- 周日上午：复习 2 小时

我更推荐方案 A，因为节奏更均匀，也更适合后续跟进调整。

你可以直接回复我：
- “按方案A安排”
- “改成周末集中复习”
- “先告诉你复习什么科目”
- “先不要排”
```

## F.6 重排 Proposal 模板

### 模板

```text
你刚才希望把今天的安排往后推，我已经检查了今天现有的日程。

如果执行这次调整，会影响：
- 15:00 的小组会
- 18:00 的复习块

我整理了两个重排方案：

方案 A：
- 小组会改到明天 15:00
- 复习块改到今晚 20:00

方案 B：
- 小组会改到后天 14:00
- 复习块改到明晚 19:30

我更推荐方案 A，因为对本周整体节奏影响更小。

你可以回复我：
- “按方案A调整”
- “小组会不要动，只改复习”
- “今天全部取消”
- “先别调整”
```

## F.7 晨间汇报文本协议 V1

晨间汇报的目的不是闲聊，而是：

- 用最少的文字帮用户重新建立今天的心智模型
- 识别是否需要调整
- 带出仍有效的 pending proposal

### 建议结构

```text
早上好，今天我先帮你快速过一下安排。

今天你已经确定的日程有：
- 09:00 政治课
- 15:00 和同学见面

今天还需要推进的任务有：
- 复习
- 驾校练车相关准备

我注意到有 1 个还没确认的安排：
- 今天晚上的复习块是否要排进日程

如果你想调整，我可以继续帮你改。
你可以直接回复我：
- “今天的安排不变”
- “下午的见面改到4点”
- “把复习安排进去”
- “重新帮我排一下今天”
```

## F.8 睡前复盘文本协议 V1

睡前复盘的职责是：

- 汇总完成情况
- 识别未完成事项
- 允许批量确认和批量顺延
- 触发次日 proposal

### 建议结构

```text
今天快结束了，我帮你做个简短复盘。

我记录到今天的日程有：
- 09:00 政治课
- 15:00 和同学见面
- 20:00 复习块

目前我不确定这些事项的完成情况：
- 政治课
- 复习块

另外，今天有 1 个任务还没有推进完：
- 复习任务还剩 2 个执行块

你可以直接告诉我：
- “今天这两个都完成了”
- “政治课完成了，复习没做”
- “复习做了但没标记”
- “复习改到明天晚上”
```

## F.9 出发前提醒文本协议 V1

你已经确认：

- 出行事件围绕 `departure_time`
- 一期做保守估算 + 天气缓存 + 高德跳转预留

### 建议结构

```text
你差不多该出发了。

按我现在的保守估算，从你当前默认出发地到学校大约需要 25 分钟，我已经额外预留了 10 分钟冗余。

今天的天气提示是：
- 可能有雨，建议带伞

如果你现在不在默认出发地，或者今天不去了，可以直接告诉我，我再帮你调整。
你可以回复我：
- “我现在就出发”
- “我已经在学校了”
- “今天不去了”
- “重新估算一下”
```

## F.10 自然语言确认协议

一期建议后端优先识别以下确认语义。

### 1. 接受

用户表达示例：

- 好
- 可以
- 就这样
- 按方案A安排
- 按你推荐的来

映射：

- `accept(proposal_id)`

### 2. 拒绝

用户表达示例：

- 不要
- 先不安排
- 取消这个方案
- 这个不行

映射：

- `reject(proposal_id)`

### 3. 修改

用户表达示例：

- 改成4点开始
- 结束时间缩短半小时
- 今天不要，挪到明天
- 驾校安排成周五

映射：

- `revise(proposal_id, patch=...)`

### 4. 类型澄清

用户表达示例：

- 这是一个任务，不是日程
- 就当成一次性安排
- 这个要拆成多个日程

映射：

- 更新 `Task-or-Event Clarifier` 的判断结果
- 生成新的 proposal

## F.11 批量确认协议

你已经明确希望支持睡前批量确认。

一期建议支持以下自然语言批量模式：

### 模式 A：批量完成

用户示例：

- 今天这三个都完成了
- 前两个完成了

### 模式 B：完成 + 未完成混合

用户示例：

- 政治课完成了，复习没做
- 见面完成了，复习做了但没标记

### 模式 C：批量顺延

用户示例：

- 复习和练车准备都改到明天
- 这个挪到周末，那个取消

### 一期内部处理原则

已确认：

- 不真正做复杂 partial accept 执行
- 而是把用户这类回复拆成多个子 proposal action 分别处理

## F.12 如何避免纯文本交互混乱

纯文本交互最大的风险，不是“不能做”，而是：

- 用户不知道系统当前在问什么
- 不知道自己回复会触发什么
- 多个 proposal 混在一起看不懂

一期建议采取以下防混乱策略：

### 1. 一次对话输出里显式标出“结论 / 原因 / 方案 / 回复方式”

### 2. 一个 proposal 只对应一个目标

### 3. 若同轮生成多个 proposal，必须分段列出

例如：

```text
关于今天的日程调整，我有 2 个待确认事项：

[事项 1] 小组会重排
...

[事项 2] 复习块顺延
...
```

### 4. 每次都提供可模仿的回复句式

例如：

- “按方案A安排”
- “改成4点开始”
- “先不要安排”

### 5. 睡前复盘和晨间汇报使用固定文本模板

用户使用几天后会形成稳定预期。

## F.13 前端最小必要辅助能力

虽然主交互是文本，但前端仍建议保留少量辅助信息：

- 当前是否有 pending proposal
- 当前是否为晨间汇报 / 睡前复盘 / 出发提醒
- 当前消息关联的 proposal 编号或摘要

### 说明

这不是按钮化，而是帮助用户理解上下文。

## F.14 一期前端不必做的事情

为了保持纯文本交互主线清晰，一期建议不强做：

- 复杂卡片式多按钮操作
- proposal 拖拽编辑
- 可视化流程图
- 复杂富文本协商 UI

这些可以后续作为增强层。

## F.15 纯文本交互协议的统一原则

最终建议锁定以下原则：

1. **文本是主交互通道**
2. **proposal 文本必须结构化**
3. **每次输出都要告诉用户“如何回复我”**
4. **晨间汇报、睡前复盘、出发提醒都使用固定模板**
5. **批量自然语言确认必须支持**
6. **复杂 mixed reply 在内部拆成多个子 proposal action**
7. **前端只提供最小必要辅助，不把主交互做成按钮系统**

---

## 附录 G - V1 定稿收口补充规则

本附录用于补齐 V1 方案中最后 4 个关键模糊点，确保设计在进入实施路线图前逻辑闭环。

## G.1 多个 pending proposal 并存时的文本指代协议

已确认一期采用：

- `一个 proposal 只对应一个目标`
- 允许中控在一轮对话中生成多个 proposal
- 前端主交互以纯文本为主

因此必须补充一套明确的文本指代规则，避免用户回复无法唯一映射。

### 规则 G.1.1 - Proposal 用户可读短标识

当同一时刻存在多个 `pending proposal` 时，系统必须为每个 proposal 分配一个用户可读短标识。

建议格式：

```text
P1 小组会调整
P2 复习顺延
P3 驾校训练安排
```

### 规则 G.1.2 - 文本确认格式

当存在多个 pending proposal 时，系统默认要求用户使用带标识的回复：

- `P1 按方案A`
- `P2 改到明天`
- `P3 先不要安排`

### 规则 G.1.3 - 单 proposal 容错

当当前仅存在一个活跃 pending proposal 时：

- 用户可以不写 `P1`
- Conductor 允许自动补全 proposal 指向

示例：

- `按方案A安排`
- `改成4点开始`
- `先不要安排`

### 规则 G.1.4 - 指代不清时必须澄清

当存在多个 pending proposal，且用户回复没有足够信息唯一指向时：

- 不允许猜测
- 必须进入 clarification

示例：

- 用户只回复：`可以`
- 当前存在 `P1`、`P2`
- 系统应回复：
  - `你是确认 P1 还是 P2？`

### 规则 G.1.5 - 前端最小辅助

前端无需做按钮化交互，但必须在文本附近或待确认区展示：

- proposal 短标识
- proposal 摘要
- 当前状态

这样用户才能在纯文本模式下稳定引用 proposal。

## G.2 Signal / Proposal 幂等与去重规则

V1 中已经有：

- cooldown 机制
- signal
- proposal

但若没有幂等键，会出现同义主动协商重复生成。

### 规则 G.2.1 - Signal 去重键

`AssistantSignal` 建议新增字段：

- `dedup_key: str | None`

建议格式：

```text
deadline_risk:task:23:2026-04-30
night_review:task:23:2026-04-30
departure_check:event:81:2026-04-30T08:25
```

### 规则 G.2.2 - Proposal 去重键

`AssistantProposal` 建议新增字段：

- `dedup_key: str | None`

建议格式：

```text
task_schedule_plan:task:23:2026-04-30-evening
reschedule_plan:event:81:2026-04-30
daily_review_followup:task:23:2026-04-30-night
```

### 规则 G.2.3 - Signal 创建约束

在 cooldown 有效期内：

- 同一 `user_id + dedup_key`
- 若已有 `new / evaluated / proposal_created / cooling` 的 signal

则不得重复创建新的同义 signal。

### 规则 G.2.4 - Proposal 创建约束

若存在：

- 同一 `user_id + dedup_key`
- 且已有 `pending / accepted but not executed / waiting followup` proposal

则不得重复生成新的等价 proposal，除非：

- 旧 proposal 已 `superseded`
- 或上下文发生实质变化

### 规则 G.2.5 - 上下文变化重开 proposal

当以下情况发生时，允许创建新的 proposal 取代旧 proposal：

- 时间窗变化
- 冲突集合变化
- task 剩余时长变化
- 用户提供了新约束

处理方式：

- 新 proposal 创建
- 旧 proposal -> `superseded`

### 规则 G.2.6 - 一期统一原则

一期应明确：

- cooldown 是产品层频率控制
- dedup_key 是数据层幂等控制

二者不能互相替代。

## G.2.7 Action Execution Idempotency

Proposal 幂等之外，还必须补 Action Executor 的执行幂等规则。

### 规则

- 同一个 confirmed proposal 只能被成功执行一次
- 重复 confirm 不得重复创建任务 / 日程 / 状态写入
- 若 proposal 已 `executed`，再次 confirm 只返回已执行回执
- 若 proposal 处于 `execution_pending`，再次 confirm 不重复执行，只返回当前执行状态
- 若 proposal 处于 `execution_failed`，允许 retry，但应记录重试次数与最近一次错误

### 建议执行前校验

Action Executor 执行前必须检查：

- `proposal.status` 是否允许执行
- `selected_option_id` 是否存在
- `option.actions` 是否非空
- proposal 是否未 `expired`
- proposal 是否未 `superseded`

### 一期实现建议

一期可先不单独新增 `AssistantActionExecution` 表，但至少要在：

- proposal 结构化字段
- 或运行日志

中保存：

- `selected_option_id`
- `execution_started_at`
- `execution_error`
- `retry_count`

## G.3 有限期重复任务的完成判定规则

你已经确认一期不做完整 recurrence engine，而是：

- 一个父任务
- 多个普通日程块

因此必须明确这类任务何时算完成。

### 规则 G.3.1 - 有限期重复任务的定义

满足以下条件之一的任务可视为“有限期重复任务”：

- 存在明确的开始/结束周期
- 一次性生成多个未来执行块
- 例如：
  - 一个月内每周三驾校练车
  - 一周内每天晚间复习

### 规则 G.3.2 - 父任务完成条件

一期默认规则：

父任务满足以下条件时可自动进入 `done`：

1. 当前日期已过任务计划终止日
2. 计划窗口内所有已生成执行块都进入终态：
   - `completed`
   - 或 `canceled_with_user_ack`

### 规则 G.3.3 - 取消执行块的默认语义

某个重复执行块被取消时：

- 默认不算该父任务“已完成”
- 系统应在后续协商中明确：
  - 是补排
  - 还是本次跳过

### 规则 G.3.4 - 本次跳过的显式终态

建议为执行块语义层增加一个可区分的状态概念：

- `canceled`
- `skipped_with_ack`

其中：

- `canceled` 表示取消但未解释如何处理
- `skipped_with_ack` 表示用户明确确认本次跳过，不补排

一期不一定要真的新增表状态字段，但逻辑层必须能区分这两类语义。

### 规则 G.3.5 - 结果型重复任务例外

若重复任务本身仍属于结果型任务，例如：

- 连续多周的材料提交跟进

则即使所有执行块结束，也不应自动 `done`，除非：

- 用户确认结果已完成

这仍受 `Task.completion_mode` 控制：

- `quantitative`
- `manual_confirmation`

## G.4 运行时 origin 解析顺序

`places.md` 负责地点名解释，但不能替代运行时“当前从哪里出发”的推断。

因此 Travel Planning Specialist 一期必须遵循统一 origin 解析顺序。

### 规则 G.4.1 - 运行时 origin 优先级

按以下顺序解析 `current_origin`：

1. 用户本轮消息中明确给出当前位置
2. 当前 thread 中最近一次已确认位置
3. 当日日程的前置地点
4. profile 中的 `home / work` 默认地点
5. 若仍不确定，则进入澄清

### 规则 G.4.2 - `places.md` 的职责边界

`places.md` 只负责：

- 别名解释
- 常用地点 canonical 映射

它不负责：

- 判断用户当前实时所在位置

### 规则 G.4.3 - `current_origin` 不进入长期记忆

运行时推断出的 `current_origin`：

- 只属于 thread / signal / proposal / runtime context
- 不应直接写入长期 `.md`

除非：

- 用户明确要求把某地点保存为长期常用地点

### 规则 G.4.4 - 无法确认时必须主动询问

若系统无法可靠推断 origin：

- 不能强猜
- 必须澄清

示例：

- `你明天下午去学校`
- 系统不知道你届时是在家、在公司，还是已经在学校
- 应先给出条件化方案，或主动问一句：
  - `如果你当时在家，我建议 X；如果你已经在学校，则建议 Y。你更接近哪种情况？`

## G.5 V1 定稿收口检查项

在进入实施路线图前，V1 方案应视为满足以下条件：

1. 任务 / 日程 / proposal / signal / thread / memory 六层语义已分离
2. proposal 生命周期完整闭环
3. 纯文本交互在多 proposal 并存时仍可唯一指代
4. 主动触发具备 cooldown 与 dedup 双层约束
5. 有限期重复任务具备可执行的完成判定规则
6. 运行时 origin 推断规则明确，且不污染长期记忆

满足以上条件后，V1 设计可视为进入“可实施蓝图”阶段。
