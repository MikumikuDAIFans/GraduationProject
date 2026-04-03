# 开源项目参考表

## 1. 本次收集的本地参考仓库

已克隆到 [reference](/E:/GraduationProject/reference) 目录。

| 项目 | 本地路径 | 类型 | 最值得参考的点 | 不建议直接照搬的点 |
|---|---|---|---|---|
| `atom` | [reference/atom](/E:/GraduationProject/reference/atom) | 大型自托管 Agent 平台 | 多 Agent 平台分层、治理、记忆、部署组织方式 | 体量过大，超出毕业设计实现范围 |
| `calendar-ai` | [reference/calendar-ai](/E:/GraduationProject/reference/calendar-ai) | AI 日历助手 | 自然语言到日历操作的最小闭环 | 对多 Agent 支撑较弱，更像单 Assistant 产品 |
| `calendar-mcp` | [reference/calendar-mcp](/E:/GraduationProject/reference/calendar-mcp) | Calendar 工具服务 | 把日历能力抽成独立工具层 | 它是工具服务，不是完整产品架构 |
| `langgraph-supervisor-py` | [reference/langgraph-supervisor-py](/E:/GraduationProject/reference/langgraph-supervisor-py) | 多 Agent Supervisor 框架 | 监督式多 Agent 编排模式、handoff、消息历史控制 | 更偏框架示例，业务层需要自己补 |
| `Langgraph-agents` | [reference/Langgraph-agents](/E:/GraduationProject/reference/Langgraph-agents) | 多 Agent 模式示例 | Supervisor 与 Swarm 的对比，预约场景示例 | 示例性质较强，工程完备度有限 |
| `spec-to-agents` | [reference/spec-to-agents](/E:/GraduationProject/reference/spec-to-agents) | 生产化多 Agent 示例 | coordinator-centric 架构、工具目录、prompt 分层、workflow 分层 | 偏 Azure 生态，基础设施较重 |
| `todo-work-agent` | [reference/todo-work-agent](/E:/GraduationProject/reference/todo-work-agent) | 任务管理 Agent | MVP 范围控制、Plan-Execute、生产部署与测试 | 偏单 Agent，不适合直接映射成你的总架构 |
| `Multi-Agent-AI-Assistant` | [reference/Multi-Agent-AI-Assistant](/E:/GraduationProject/reference/Multi-Agent-AI-Assistant) | n8n 多 Agent 助理 | Supervisor + Calendar/Email/Contact 的个人助理拆分方式 | 更偏工作流编排，代码级抽象不够强 |

## 2. 逐项分析

### 2.1 atom

- GitHub: [rush86999/atom](https://github.com/rush86999/atom)
- 适合借鉴：
  - 平台分层
  - 目录规模化组织
  - 记忆、治理、技能扩展、部署治理
- 对你的启发：
  - 毕业设计不一定要做“平台级能力”，但可以借鉴它的分层思想，把 Agent、工具、状态、前端、部署拆开写

### 2.2 calendar-ai

- GitHub: [typper-io/calendar-ai](https://github.com/typper-io/calendar-ai)
- 适合借鉴：
  - 日历助手产品最小闭环
  - 自然语言创建日程
  - 前端围绕“calendar + assistant”组织交互
- 对你的启发：
  - 你的系统前端可以采用“日历工作区 + 助手工作区”的双视图，而不是普通聊天页

### 2.3 calendar-mcp

- GitHub: [deciduus/calendar-mcp](https://github.com/deciduus/calendar-mcp)
- 适合借鉴：
  - 把日历能力独立为工具服务
  - `free_busy`、`mutual schedule` 这类能力接口化
- 对你的启发：
  - 你的系统最好将 Calendar 访问独立为 `Calendar Tool`，而不是由某个 Agent 直接拼接数据库逻辑

### 2.4 langgraph-supervisor-py

- GitHub: [langchain-ai/langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py)
- 适合借鉴：
  - Supervisor 管多个专长 Agent
  - handoff 工具
  - message history 管理
  - memory/checkpoint 扩展
- 对你的启发：
  - 你的 `Master Agent` 更适合升级为 `Supervisor Agent`

### 2.5 Langgraph-agents

- GitHub: [pareshraut/Langgraph-agents](https://github.com/pareshraut/Langgraph-agents)
- 适合借鉴：
  - 同时展示 Supervisor 和 Swarm 两类协作方式
  - `doc-agent` 中的预约调度场景
- 对你的启发：
  - 你的毕业设计应优先采用 Supervisor，而不是 Swarm
  - 日程系统通常更需要中心化约束控制

### 2.6 spec-to-agents

- GitHub: [microsoft/spec-to-agents](https://github.com/microsoft/spec-to-agents)
- 适合借鉴：
  - coordinator-centric star topology
  - prompts、tools、workflow、agents 分目录管理
  - structured output routing
  - human-in-the-loop
- 对你的启发：
  - 论文中的总体架构图和时序图可以借鉴这种“协调器 + 专家 Agent + 工具层”的表达方式

### 2.7 todo-work-agent

- GitHub: [boemer00/todo-work-agent](https://github.com/boemer00/todo-work-agent)
- 适合借鉴：
  - Plan-Execute 模式
  - 生产部署、测试、可观测性
  - 任务系统如何做 MVP
- 对你的启发：
  - 你的毕业设计需要一个可展示的最小闭环，不要一开始就追求全功能多 Agent 平台

### 2.8 Multi-Agent-AI-Assistant

- GitHub: [sushant1827/Multi-Agent-AI-Assistant](https://github.com/sushant1827/Multi-Agent-AI-Assistant)
- 适合借鉴：
  - `Supervisor + Calendar + Contact + Email` 的个人助理拆分
  - 个人事务助理如何做职能 Agent 切分
- 对你的启发：
  - 你的 Agent 命名和职责边界可以更面向业务域，而不是纯概念域

## 3. 最推荐你重点参考的 4 个项目

如果只挑 4 个深看，建议顺序如下：

1. [reference/spec-to-agents](/E:/GraduationProject/reference/spec-to-agents)
   - 最适合学习严谨的多 Agent 工程化结构
2. [reference/langgraph-supervisor-py](/E:/GraduationProject/reference/langgraph-supervisor-py)
   - 最适合学习 Supervisor 模式
3. [reference/calendar-mcp](/E:/GraduationProject/reference/calendar-mcp)
   - 最适合学习工具层设计
4. [reference/calendar-ai](/E:/GraduationProject/reference/calendar-ai)
   - 最适合学习贴近你课题的产品交互闭环

## 4. 对你毕业设计最直接的结论

结合这些开源项目，MA-IPAAS 更适合采用以下设计原则：

1. 用 `Supervisor Agent` 统一路由，而不是多个 Agent 平行自由协作
2. 用 `Specialized Agents` 表达业务域职责，而不是泛化角色描述
3. 用 `Tool Layer` 承载外部能力，而不是让 Agent 直接耦合 API 与数据库
4. 用 `State / Memory / Audit` 支撑会话状态、可追溯性与重排历史
5. 用 `MVP 分阶段实现` 控制毕业设计风险
