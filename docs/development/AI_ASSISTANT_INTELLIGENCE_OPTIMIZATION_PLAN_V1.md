# AI 助手智能化优化方案与浏览器级验收计划 V1

> 文档状态：drafting
> 版本：V1
> 最后更新：2026-05-15
> 适用范围：AI 助手理解层、多轮上下文、Proposal 协议、前端交互、浏览器级验收
> 关联文档：`docs/development/AI_ASSISTANT_REDESIGN_PLAN_V1.md`、`docs/development/AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`
> 核心目标：在保留 proposal-first 安全边界的前提下，把当前偏规则化的助手升级为更智能、更自然、更可解释的事务协商助手。

---

## 一、背景与问题判断

当前 AI 助手已经具备以下基础能力：

1. 能通过助手对话创建、修改、确认、拒绝日程 proposal。
2. 能保证未确认前不写入 event / task。
3. 能通过文本协议处理 `确认 P1 方案A`、`P1 先不要安排`、`把 P1 改到下午4点` 等操作。
4. 能在浏览器级真实对话中完成 50+ 日程创建与修改压力验收。

但用户体感仍然偏“程序化”，主要原因不是没有 LLM，而是当前系统的 LLM 使用方式仍偏保守：

1. LLM 更多承担语义辅助抽取，而不是稳定的结构化理解主路径。
2. 时间解析、目标匹配、多轮上下文补槽仍大量依赖正则和手写规则。
3. `understanding.py` 混合了 intent 分类、时间解析、上下文继承、目标匹配、proposal revise 判断等多种职责，继续堆补丁会导致维护困难。
4. 前端一度存在 proposal 卡片 direct API 操作入口，容易绕过“用户提示词 -> 助手协议 -> 状态机”的统一链路。
5. 多轮会话状态缺少一个可持久化、可解释、可被 LLM 使用的结构化摘要。

因此，下一阶段不应继续单纯增加正则，而应升级为：

```text
LLM 负责语义和上下文理解
确定性模块负责安全校验、时间归一化、目标解析和执行
前端所有用户可见操作统一走助手消息通道
```

---

## 二、设计原则

### 2.1 保留安全边界

LLM 不允许直接写入数据库，不允许直接确认、拒绝或修改业务实体。

所有会改变业务数据的操作必须经过：

```text
结构化理解 -> 安全校验 -> pending proposal -> 用户确认 -> proposal executor -> 落库
```

### 2.2 统一用户操作入口

所有用户可见操作都必须表现为用户消息。

允许按钮作为快捷入口，但按钮只负责生成固定提示词并发送给助手，例如：

- 确认按钮 -> `确认 P1 方案A`
- 拒绝按钮 -> `P1 先不要安排`
- 重试按钮 -> `重试 P1`
- 记忆确认 -> `记住 M1`

禁止前端待确认方案卡片直接调用 proposal confirm / reject / revise API。

### 2.3 主输入框是唯一自然语言输入口

待确认方案卡片不得再提供额外输入框。修改 proposal 必须通过主输入框，例如：

```text
把 P1 改到下午2点
把 P2 地点改成图书馆
把 P1 标题改成政治课
```

### 2.4 LLM 输出必须结构化

LLM 不应返回自由文本作为后端业务决策依据，而应返回受 schema 约束的 JSON。

不合格 JSON、低置信度结果、与确定性校验冲突的结果，必须 fallback 到澄清或规则路径。

### 2.5 可解释、可回放、可验收

每一次智能判断都应能回答：

- 用户原话是什么？
- LLM 理解结果是什么？
- 系统继承了哪些上下文？
- 目标匹配到了哪个 proposal / event / task？
- 为什么可以 proposal，或为什么需要澄清？
- 未确认前是否没有写库？

---

## 三、目标架构

### 3.1 总体链路

```text
用户输入
  ↓
前端 AssistantPanel
  ↓
AssistantMessage
  ↓
AssistantService
  ↓
加载上下文：history / events / tasks / profile / memory / pending proposals / conversation_state
  ↓
ProposalIntentRouter
  ↓
MessageUnderstandingLLM
  ↓
ContextResolver
  ↓
TimeNormalizer
  ↓
SafetyValidator
  ↓
Planning / Proposal Builder
  ↓
Negotiation Reply
  ↓
pending proposal 或 clarification
  ↓
用户确认
  ↓
Proposal Executor
```

### 3.2 模块职责

#### MessageUnderstandingLLM

职责：

- 让 LLM 读取当前用户消息、最近历史、conversation_state、pending proposals 摘要。
- 输出结构化理解结果。
- 标注 intent、conversation_act、slots、context_links、missing_fields、risk_flags。

不负责：

- 不直接写库。
- 不直接执行 proposal。
- 不直接覆盖确定性时间归一化结果。

#### ProposalIntentRouter

职责：

- 在调用 LLM 之前优先识别高确定性的 proposal 操作。
- 处理 `确认 P1 方案A`、`P1 先不要安排`、`把 P1 改到下午4点`。
- 多 pending 且用户只说 `可以` 时必须澄清。

原因：

确认、拒绝、修改 proposal 是安全协议，不应交给 LLM 猜。

#### ContextResolver

职责：

- 解析用户话里的目标引用。
- 支持 `P1`、`这个方案`、`刚才那个`、`约会`、`真实逐条日程10`、`明天那个复习块`。
- 生成候选评分和解释。

输出示例：

```json
{
  "target_kind": "event",
  "resolution": "resolved",
  "target_id": 10,
  "candidate_scores": [
    {
      "event_id": 10,
      "title": "处理真实逐条日程10",
      "score": 0.94,
      "reasons": ["编号精确匹配", "标题别名匹配"]
    }
  ]
}
```

#### TimeNormalizer

职责：

- 将 LLM 或规则提取到的自然时间统一转换为 timezone-aware datetime。
- 处理今天、明天、下个月一号、下午/晚上、裸小时、跨天、过去时间滚动。
- 保留解释，例如 `8点` 为什么被解析为 `20:00`。

#### SafetyValidator

职责：

- 判断是否缺字段。
- 判断是否目标唯一。
- 判断是否冲突。
- 判断是否需要多方案。
- 判断是否会大批量失控。
- 判断是否允许 proposal。

#### ConversationStateManager

职责：

- 为每个 assistant session 维护结构化会话状态。
- 保存当前 active_goal、known_slots、missing_fields、last_referenced、recent_entities。
- 每次用户消息和助手回复后更新。

---

## 四、LLM 结构化理解 Schema

### 4.1 输入上下文

LLM 的输入不应只有当前用户消息，应包含：

```json
{
  "now": "2026-05-15T19:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "current_user_message": "下午1点开始，晚上10点结束",
  "recent_messages": [
    {
      "role": "user",
      "content": "下个月的一号去学校"
    },
    {
      "role": "assistant",
      "content": "这个日程还缺少开始时间。"
    }
  ],
  "conversation_state": {
    "active_goal": {
      "type": "create_event",
      "status": "collecting_slots",
      "known_slots": {
        "date": "2026-06-01",
        "title": "去学校",
        "location_name": "学校"
      },
      "missing_fields": ["start_time"]
    }
  },
  "pending_proposals": [],
  "events_summary": [],
  "tasks_summary": []
}
```

### 4.2 输出 Schema

```json
{
  "intent": "create_event",
  "goal_type": "event",
  "conversation_act": "slot_fill",
  "confidence": 0.92,
  "language": "zh",
  "slots": {
    "title": "去学校",
    "date": "2026-06-01",
    "start_time": "13:00",
    "end_time": "22:00",
    "location_name": "学校",
    "duration_minutes": null
  },
  "slots_patch": {
    "start_time": "13:00",
    "end_time": "22:00"
  },
  "context_links": {
    "uses_previous_request": true,
    "target_proposal_label": null,
    "target_event_reference": null,
    "target_task_reference": null
  },
  "missing_fields": [],
  "ambiguities": [],
  "risk_flags": [],
  "explanation": "用户在补充上一轮去学校日程的开始和结束时间。"
}
```

### 4.3 conversation_act 枚举

- `new_request`
- `slot_fill`
- `confirm_existing`
- `reject_existing`
- `revise_existing`
- `ask_question`
- `answer_question`
- `cancel_existing`
- `mark_done`
- `unknown`

### 4.4 intent 枚举

- `create_event`
- `reschedule_event`
- `cancel_event`
- `mark_event_completed`
- `create_task`
- `plan_task_schedule`
- `mark_task_completed`
- `schedule_guidance`
- `memory_update`
- `unknown`

---

## 五、Conversation State 设计

### 5.1 数据结构

建议为每个会话维护 `conversation_state_json`：

```json
{
  "active_goal": {
    "type": "create_event",
    "status": "collecting_slots",
    "known_slots": {
      "title": "去学校",
      "date": "2026-06-01",
      "location_name": "学校"
    },
    "missing_fields": ["start_time"]
  },
  "last_referenced": {
    "proposal_id": null,
    "event_id": null,
    "task_id": null
  },
  "recent_entities": [
    {
      "kind": "event",
      "label": "约会",
      "event_id": 12,
      "last_mentioned_at": "2026-05-15T19:10:00+08:00"
    }
  ],
  "updated_by_message_id": 123
}
```

### 5.2 更新规则

每次用户消息后：

1. 若是新请求，创建或替换 active_goal。
2. 若是补槽，合并 slots_patch。
3. 若生成 proposal，记录 active proposal。
4. 若确认 / 拒绝 / 修改 proposal，更新 last_referenced。
5. 若执行成功，记录最新 event/task。
6. 若用户开启新话题，关闭旧 active_goal。

### 5.3 清理规则

- proposal executed / rejected 后，active proposal 不再作为默认确认目标。
- 多 pending proposal 时，不允许用 active target 自动确认。
- active_goal 超过合理轮数未继续，应降级为普通历史，不再强行合并。

---

## 六、前端交互规范

### 6.1 待确认方案卡片

允许显示：

- protocol label，例如 `P1`
- proposal 状态
- summary
- 方案 A / B
- 推荐标识
- 确认按钮
- 拒绝按钮
- 修改提示文本

禁止显示：

- 卡片内修改输入框
- 卡片内自由文本提交入口
- 会直接调用 proposal confirm / reject / revise API 的按钮

### 6.2 快捷按钮行为

按钮只能生成用户消息：

| UI 操作 | 发送给助手的消息 |
|---|---|
| 确认方案 A | `确认 P1 方案A` |
| 拒绝方案 | `P1 先不要安排` |
| 重试失败方案 | `重试 P1` |

### 6.3 修改方案方式

用户必须在主输入框输入：

```text
把 P1 改到下午2点
把 P1 地点改成图书馆
把 P1 标题改成政治课
```

待确认方案卡片只展示提示：

```text
修改请在主输入框回复：把 P1 改到下午2点
```

---

## 七、后端改造路线

### Phase 1：统一用户操作入口

目标：

- 所有前端 proposal 操作都走 AssistantMessage。
- 保留后端 proposal API 作为内部或 debug 能力，但不作为用户主流程。

改动点：

- `AssistantPanel.vue`
- `App.vue`
- `assistant.ts`
- `workspace.ts`
- `AssistantService._maybe_handle_proposal_text_protocol`

验收重点：

- 点击确认按钮时，网络中不出现 `/assistant/proposals/{id}/confirm`。
- 消息表中出现用户消息 `确认 P1 方案A`。
- proposal 正常 executed。

### Phase 2：ConversationStateManager

目标：

- 建立结构化会话状态。
- 替代部分依赖 recent history 文本扫描的补槽逻辑。

改动点：

- 新增 `assistant_conversation_state` 表或扩展现有 thread state。
- 新增 `ConversationStateManager`。
- `AssistantService` 在调用 conductor 前注入 state。
- conductor 输出后更新 state。

验收重点：

- `下个月的一号去学校` 后，state 记录 date/title/location/missing start_time。
- `下午1点开始` 后，继承 state 并生成完整 proposal。

### Phase 3：LLM 结构化理解主路径

目标：

- 让 LLM 结构化输出成为理解层主路径。
- 规则作为 validator / fallback，而不是无限堆补丁。

改动点：

- `GeminiClient.extract_message_understanding`
- 新增 Pydantic schema。
- `UnderstandingSpecialist` 优先消费 schema。
- 低置信度或 schema 不合法时 fallback。

验收重点：

- 同一批自然语言测试在不同话术下保持稳定 intent / slots。
- LLM 错误输出不会导致直接写库。

### Phase 4：ContextResolver 与 TargetResolver

目标：

- 统一处理 proposal/event/task 引用。
- 输出可解释候选评分。

改动点：

- 新增 `assistant_context_resolver.py`
- 替换 `understanding.py` 中分散的目标匹配逻辑。
- 引入目标解析诊断 metadata。

验收重点：

- `把真实逐条日程10改到6月20号` 不误匹配 `真实逐条日程52`。
- `把约会时间改为8点` 能定位最近已创建约会。
- 多个约会候选时必须澄清。

### Phase 5：LLM Proposal Verifier

目标：

- 在 proposal 展示前，让 LLM 检查 proposal 是否忠实于用户原话。
- 只做验证，不做执行。

输出示例：

```json
{
  "verdict": "ok",
  "issues": [],
  "confidence": 0.91
}
```

若 verdict 为 `problem`，系统应改为澄清或重新生成 proposal。

验收重点：

- 用户说“出发去学校”时，proposal 标题和时间语义不应变成无关任务。
- 用户说“提醒我”时，系统应说明是提醒型日程或询问提醒策略。

---

## 八、浏览器级真实测试总要求

本优化计划的验收必须是浏览器级真实测试。

禁止以下替代方式：

1. 只跑单元测试。
2. 直接调用后端 proposal confirm / reject / revise API。
3. 直接写 SQLite 数据库。
4. 一次性输入大段清单代替逐条真实对话。
5. 只用 mock 页面，不经过真实前端组件。

允许辅助方式：

- 用 Playwright 自动操作真实浏览器页面。
- 用 SQLite 查询作为结果证据。
- 用网络面板记录请求。
- 用后端日志和控制台日志确认无错误。

每条浏览器用例至少记录：

- 用户每轮输入。
- 助手每轮回复。
- 待确认方案区展示。
- proposal 状态变化。
- events/tasks 是否落库。
- 网络请求是否有 4xx/5xx。
- console 是否有 error。

---

## 九、浏览器级验收环境

### 9.1 环境准备

- 使用独立 SQLite 测试库。
- 后端启动在独立端口，例如 `18720`。
- 前端启动在独立端口，例如 `8895`。
- 前端 `VITE_API_BASE_URL` 指向该后端。
- 浏览器使用 Chromium。
- 验收前清理目标测试数据。

### 9.2 基础数据

建议准备：

- 地点记忆：
  - 学校 = 测试学校地址
  - 家 = 测试家庭地址
  - 图书馆 = 测试图书馆
- 任务：
  - 整理毕设论文
  - 英语复习
- 日程：
  - 明天 15:00-16:00 图书馆自习
  - 明天 18:00-19:00 约会
  - 6月20日 10:00-11:00 真实逐条日程52

---

## 十、浏览器级 P0 验收用例

### INT-P0-001 前端确认按钮必须走助手消息

- 前置条件：存在 1 个 pending proposal `P1`。
- 浏览器操作：点击待确认方案卡片的 `确认` 按钮。
- 预期结果：
  - 对话区新增用户消息 `确认 P1 方案A`。
  - 网络请求不得出现 `/api/assistant/proposals/{id}/confirm`。
  - 可以出现 `/ws/assistant` 或 `/api/assistant/message`。
  - proposal 最终进入 `executed`。
  - 业务数据只写入一次。

### INT-P0-002 前端拒绝按钮必须走助手消息

- 前置条件：存在 1 个 pending proposal `P1`。
- 浏览器操作：点击待确认方案卡片的 `拒绝` 按钮。
- 预期结果：
  - 对话区新增用户消息 `P1 先不要安排`。
  - 网络请求不得出现 `/api/assistant/proposals/{id}/reject`。
  - proposal 进入 `rejected`。
  - events/tasks 无新增、无修改。

### INT-P0-003 待确认方案卡片不得出现额外输入框

- 前置条件：存在 1 个 pending proposal。
- 浏览器检查：
  - 待确认方案卡片中 `input` 和 `textarea` 数量为 0。
  - 页面只存在主输入框作为自然语言入口。
  - 页面不出现 `输入修改要求` 文案。
- 预期结果：
  - 卡片只显示确认、拒绝和修改提示。
  - 修改提示指向主输入框，例如 `修改请在主输入框回复：把 P1 改到下午2点`。

### INT-P0-004 主输入框修改 proposal

- 前置条件：存在 pending proposal `P1`，时间为 09:00-10:00。
- 浏览器输入：`把 P1 改到下午2点`
- 预期结果：
  - 对话区新增该用户消息。
  - 旧 proposal 进入 `superseded` 或 `revised`。
  - 新 proposal pending，时间为 14:00-15:00。
  - 未确认前 events/tasks 不变。

### INT-P0-005 多轮补槽必须继承 conversation_state

- 浏览器输入序列：
  1. `下个月的一号去学校`
  2. `下午1点开始`
- 预期结果：
  - 第 1 轮不落库，进入缺时间澄清或 collecting state。
  - conversation state 记录 `date=下个月一号`、`title=去学校`、`location=学校`。
  - 第 2 轮继承上一轮上下文，生成 `06-01 13:00-14:00 去学校` proposal。
  - 不得追问已知地点和日期。

### INT-P0-006 独立新日程不得错误合并到上一轮

- 前置条件：刚完成 `下个月的一号去学校 -> 下午1点开始`，存在或已确认该 proposal。
- 浏览器输入：`明天晚上6点去约会`
- 预期结果：
  - 系统识别为新的 event_creation。
  - 不得继承“学校”作为约会地点。
  - 标题为 `约会` 或等价表达。
  - 时间为明天 18:00。

### INT-P0-007 改期目标必须可解释匹配

- 前置条件：存在事件 `处理真实逐条日程10`、`真实逐条日程52`。
- 浏览器输入：`把真实逐条日程10改到6月20号16:00到17:00，地点改到最终测试地点A`
- 预期结果：
  - 系统生成 event_reschedule proposal。
  - target event 为 `处理真实逐条日程10`。
  - 不得因为目标日期是 6月20号而误选当天的 `真实逐条日程52`。
  - proposal 或诊断 metadata 中可看到目标匹配依据。

### INT-P0-008 多 pending 下“可以”必须澄清

- 前置条件：同时存在 `P1`、`P2` 两个 pending proposal。
- 浏览器输入：`可以`
- 预期结果：
  - 不确认任何 proposal。
  - 助手要求明确 `P1` 还是 `P2`。
  - 两个 proposal 保持 pending。
  - 业务数据无写入。

### INT-P0-009 LLM 误判不得突破安全协议

- 前置条件：AI provider 可用。
- 浏览器输入：`5月21号下午1点出发去学校`
- 预期结果：
  - 可以调用 LLM 做语义理解，但最终必须生成 pending event proposal。
  - 未确认前不写入 event。
  - proposal 标题类似 `去学校`。
  - start_time 为 2026-05-21 13:00。
  - 若结束时间缺失，系统说明默认时长。

### INT-P0-010 真实逐条压力验收

- 前置条件：干净库。
- 浏览器操作：
  - 逐条输入至少 50 条自然语言日程创建请求。
  - 每条生成 proposal 后再通过文本或按钮确认。
  - 穿插至少 5 条修改，包括时间、地点、标题、目标编号、裸小时。
- 禁止：
  - 不得一次性输入清单。
  - 不得直调 API 创建日程。
- 预期结果：
  - event 数量大于 50。
  - 时间跨度不少于 30 天。
  - 所有创建和修改均经过 pending proposal。
  - 无 pending 残留，除刻意拒绝用例外无 failed proposal。
  - 浏览器 console 无 error。
  - 网络请求无业务 4xx/5xx。

---

## 十一、浏览器级 P1 验收用例

### INT-P1-001 LLM 结构化理解可观测

- 浏览器输入：`下周三晚上7点在图书馆和同学复盘英语作文`
- 预期结果：
  - 后端 trace 或 debug metadata 中记录 LLM structured understanding。
  - intent 为 `create_event`。
  - title 类似 `复盘英语作文`。
  - location 为 `图书馆`。
  - 时间归一化为下周三 19:00。

### INT-P1-002 LLM 低置信度必须澄清

- 浏览器输入：`那个事情就按之前那样弄一下`
- 预期结果：
  - 系统不得猜测创建或修改任何业务数据。
  - 若无法解析目标，应澄清。
  - 不生成可执行 proposal。

### INT-P1-003 复合请求拆分

- 浏览器输入：`明天下午3点去学校开会，晚上8点提醒我复习英语`
- 预期结果：
  - 系统不得静默只处理其中一个。
  - 应生成两个 proposal，或明确说明将拆成两个待确认事项。
  - 未确认前不落库。

### INT-P1-004 任务排程与单次日程区分

- 前置条件：存在任务 `整理毕设论文`。
- 浏览器输入：`我预计3天整理完成，帮我安排下下午3点到5点`
- 预期结果：
  - 系统识别为 `task_schedule_plan`。
  - 生成未来三天 15:00-17:00 的任务切片 proposal。
  - 不得误创建一个普通日程。

### INT-P1-005 记忆候选也必须走助手消息

- 浏览器输入：`以后学校就指南京大学仙林校区`
- 预期结果：
  - 系统生成记忆候选。
  - 确认记忆时应通过用户消息，例如 `记住 M1`。
  - 未确认前不写入长期记忆文件。

---

## 十二、验收证据模板

每轮浏览器验收完成后，必须记录以下内容：

```text
验收日期：
代码分支 / commit：
后端端口：
前端端口：
SQLite 库：
AI Provider：

用例结果：
- INT-P0-001：通过 / 失败
  证据：
  - 用户消息：
  - 网络请求：
  - proposal 状态：
  - 业务表变化：

失败修复：
- 问题：
- 根因：
- 修复文件：
- 新增测试：
- 复测结果：

最终统计：
- events:
- tasks:
- assistant_proposals by status:
- pending:
- execution_failed:
- browser console errors:
- HTTP 4xx/5xx:
```

---

## 十三、完成定义

本优化计划不能仅以“代码写完”作为完成。

必须同时满足：

1. Phase 1 至 Phase 3 至少完成并通过 P0 浏览器验收。
2. 所有用户可见 proposal 操作均走助手消息通道。
3. 待确认方案卡片无额外自然语言输入框。
4. 多轮上下文用 conversation state 支撑，而不是只靠最近历史文本猜测。
5. LLM structured understanding 有 schema 校验和 fallback。
6. 所有写操作仍保持 proposal-first。
7. 浏览器级 P0 用例全部通过。
8. 后端相关回归测试通过。
9. 前端生产构建通过。
10. 验收报告包含真实浏览器网络、console、数据库状态证据。

---

## 十四、风险与控制

### 14.1 LLM 输出不稳定

控制：

- 强制 JSON schema。
- 低置信度 fallback。
- proposal 前进行 deterministic validation。

### 14.2 上下文过度继承

控制：

- active_goal 设置生命周期。
- 新请求特征强时不得合并旧上下文。
- 多轮补槽必须有明确缺槽状态。

### 14.3 目标误匹配

控制：

- TargetResolver 输出候选评分。
- 分数接近时澄清。
- “改到”后的日期不得反向过滤源事件。

### 14.4 前端绕过助手

控制：

- 组件层只 emit `send`。
- 用户主流程不得绑定 direct proposal confirm / reject / revise API。
- 浏览器网络验收必须检查 direct API 是否出现。

### 14.5 测试走捷径

控制：

- 验收文档明确禁止直写库、直调业务 API、一次性清单导入。
- 真实压力测试必须逐条对话创建和确认。

---

## 十五、推荐实施顺序

1. 固化前端统一消息入口。
2. 建立 conversation state。
3. 定义 LLM structured understanding schema。
4. 接入 schema 校验和 fallback。
5. 拆分 `understanding.py` 巨型逻辑。
6. 引入 ContextResolver / TargetResolver。
7. 引入 TimeNormalizer 解释输出。
8. 引入 LLM Proposal Verifier。
9. 扩展浏览器级验收脚本与报告模板。
10. 用 50+ 真实逐条日程压力测试做最终验收。
