# AI 助手模型主导重构审查 V1

## 文档元数据

- Status: `draft`
- Version: `v1`
- Last updated: `2026-05-06 17:11 +08:00`
- Authoring context: `Post-Phase-8 architecture reassessment`
- Related progress file: `E:\GraduationProject\docs\development\AI_ASSISTANT_IMPLEMENTATION_TASK_BOOK_V1.md`
- Related source design: `E:\GraduationProject\docs\development\AI_ASSISTANT_REDESIGN_PLAN_V1.md`

## 1. 审查结论

当前 AI 助手并没有实现成“模型主导的多智能体个人助手”，而是：

```text
规则主导的多分支状态机
  + proposal-first 执行边界
  + 少量模型参与
  + 多层 legacy fallback
```

这意味着系统虽然已经具备：

- proposal-first
- confirm-before-write
- 基础多 action 执行
- 长期记忆候选
- 前端 proposal surface

但**核心理解与协商权**并不在主控模型手里，而仍被大量硬路由、模板澄清和旧计划链路控制。

结论不是“再补一些关键词就能好”，而是：

> 当前架构方向本身已经开始阻碍目标产品定义，必须从“规则前置决策”迁移到“模型先整理语义，规则只做后置校验”。

## 2. 关键发现

### 2.1 决策权分裂

`AssistantService.send_message()` 当前仍然存在多套并行/串行决策源：

1. proposal text protocol
2. conductor
3. pending action decision
4. workflow
5. `AssistantPlanRuntime.build_plan()` legacy plan

结果：

- 用户以为在和同一个助手协商
- 实际上系统会在不同链路之间跳转
- 一旦 conductor 没产出可接受结果，就会掉回旧规则链

这会造成：

- 人格不一致
- 回复风格不一致
- 相同语义在不同回合表现完全不同

### 2.2 理解层仍是硬路由

`UnderstandingSpecialist` 仍然依赖：

- regex intent classification
- event/task 二分
- 少量 schedule guidance 特判

这类设计对“口语化 continuation”天然脆弱。

典型失败句式：

- “我预计 3 天整理完成，帮我安排下下午 3 点到 5 点”
- “继续规划整理论文这一项任务”
- “按刚才那个任务分 3 天下去做”
- “这件事我想拆成几块排在下周”

当前系统通常会把它们误判为：

- 新 event creation
- 新 task creation
- unknown -> clarification template

### 2.3 proposal schema 无法承载任务继续规划

现在的核心 proposal 类型偏向：

- `event_creation`
- `task_creation`
- `event_reschedule`
- `event_cancel`
- `event_batch_reschedule`
- `event_status_update`
- `task_status_update`

缺少的恰恰是目标设想中的高频核心类型：

- `task_continuation_plan`
- `task_schedule_plan`
- `task_split_plan`
- `task_schedule_refine`
- `proposal_refine_from_context`
- `multi_block_task_schedule`

因此，即使理解层想表达“继续规划当前任务”，下游也没有合适载体。

### 2.4 澄清与协商仍是模板

`TaskOrEventClarifierSpecialist` 和 `NegotiationSpecialist` 中有大量硬编码文案：

- “你希望把这件事当成一次性日程，还是需要拆成多个日程组合成的任务？”
- “如果认可，请回复类似‘确认 P1 方案A’”

这些文案本身不是绝对错误，但它们现在承担了过多一线交互职责。

只要前面理解稍有偏差，用户立刻就能感受到：

- 僵硬
- 模板化
- 不像在和一个真正理解上下文的主控助手交流

## 3. 为什么“继续补规则”是错误方向

继续补规则的短期收益是：

- 可以修掉几个具体 case
- 看起来“命中率提高了一点”

但长期代价更大：

1. 路由树越来越大
2. case 之间互相打架
3. 用户说法一旦变化就重新失效
4. fallback 触发面越来越难预测
5. 主控模型永远学不会承担真正的语义职责

本质上，用户输入是：

- 随意的
- 口语化的
- 省略大量上下文的
- 带自我修正和中途改口的

这种输入不适合靠前置关键词网关做主决策。

## 4. 目标重构原则

### 4.1 模型先整理语义，规则后置校验

新原则：

```text
用户输入
  -> 模型主控先输出结构化语义判断
  -> 系统规则做唯一性/安全性/执行性校验
  -> 生成 proposal
  -> 用户确认
  -> 执行
```

而不是：

```text
用户输入
  -> 规则先猜 intent
  -> 规则决定 task/event
  -> 规则决定要不要澄清
  -> 模型只补文案
```

### 4.2 主控必须成为唯一决策源

目标状态下，`send_message()` 应该只有一条主线：

1. gather context
2. model-driven orchestration
3. proposal / clarification / answer
4. confirm path

旧链路要么删除，要么降级成：

- migration fallback
- offline degraded mode
- explicit feature flag rollback

而不是默认参与正常对话。

### 4.3 把规则从“理解器”降级成“守门员”

规则未来只应该做：

- target 是否唯一
- batch 操作是否过大
- proposal 是否缺执行必需字段
- confirm-before-write 是否满足
- rollback/事务边界是否需要保守化

规则不应该继续负责：

- 判定这是不是任务
- 判定这是不是继续规划
- 判定这是不是在接上文

## 5. 新主控中间态建议

建议引入统一的模型主控输出 schema，例如：

```json
{
  "conversation_mode": "proposal|clarification|answer|confirm_existing|revise_existing",
  "user_goal": "plan_task|schedule_blocks|create_event|update_event|review_options",
  "target_scope": {
    "kind": "task|event|proposal|batch_events|none",
    "resolution": "resolved|ambiguous|missing",
    "task_id": 123,
    "event_ids": [1,2]
  },
  "continuation": {
    "is_following_previous_context": true,
    "based_on_active_target": true,
    "based_on_pending_proposal": false
  },
  "planning_intent": {
    "wants_task_split": true,
    "wants_multi_day_schedule": true,
    "time_preferences": [
      {"date": "2026-05-07", "start": "15:00", "end": "17:00"}
    ],
    "duration_hint_days": 3
  },
  "missing_information": [],
  "proposal_shape": "task_schedule_plan"
}
```

重点不是字段名本身，而是：

- continuation 必须成为一等公民
- target resolution 必须和 intent 分开
- planning shape 必须能表达“继续规划任务”

## 6. 建议保留与移除

### 6.1 建议保留

- Proposal Manager
- Action Executor
- active_target thread state
- proposal text protocol
- memory candidate / long-term memory
- rollback / retry / confirm boundary

这些都属于“安全边界”和“执行基础设施”，是对的。

### 6.2 建议降级

- `UnderstandingSpecialist`
- `TaskOrEventClarifierSpecialist`
- `NegotiationSpecialist`
- `AssistantPlanRuntime.build_plan()` 中的 rule-based dominant path

它们不应再主导“这句话是什么意思”，而应转为：

- 结构化补充器
- 执行校验器
- 文案渲染器

### 6.3 建议删除或隔离

- 正常对话默认落回 legacy build_plan 的路径
- 以关键词为中心的 task/event 前置二分
- 将模板澄清作为高频主回复路径

## 7. 分阶段迁移建议

### Phase 9A - Model-Orchestrated Understanding Layer

目标：

- 引入单一模型主控输出 schema
- 让 continuation / active target / pending proposal 成为主输入
- 让旧 understanding 只做 fallback

退出条件：

- “继续规划这个任务”
- “按未来三天下午 3-5 点排”
- “就沿着刚才那个方案改”

这些真实口语化输入可以稳定进入正确 proposal shape。

### Phase 9B - Proposal Shape Expansion

目标：

- 新增任务继续规划类 proposal
- 支持 multi-block / multi-day task schedule draft
- 支持 proposal refine from existing task context

退出条件：

- 任务规划不再退化成新建 task 或误建 event

### Phase 9C - Generated Clarification

目标：

- 澄清由模型按上下文生成
- 模板仅保留最末级兜底

退出条件：

- 用户不再频繁看到“任务还是日程”“缺开始时间”这类机械重复问句

### Phase 9D - Legacy Path Retirement

目标：

- `send_message()` 正常路径只保留 model-driven orchestration
- old build_plan / workflow 仅保留 feature flag fallback

退出条件：

- 主控成为唯一默认决策源

## 8. 执行注意事项

- 不能破坏现有 proposal-first 和 confirmation-before-write。
- 不能在“为了更自由理解”名义下恢复直接写入。
- 不能一边保留旧路由，一边再叠新模型判断，否则只会让决策源更多。
- 迁移期间必须保留可回退开关，但默认路径必须逐步切向新主控。

## 9. 最小下一步

如果继续执行，不建议下一步直接大规模改代码，而建议先做这 3 件事：

1. 定义新的 model-driven orchestration schema。
2. 写 8-12 条真实 transcript 回归测试，覆盖 continuation / task planning / task split / natural confirmation。
3. 画出 `send_message()` 迁移后的单一主线，明确旧链路哪些点会被删、哪些点只保留 fallback。

## 10. 审查结论摘要

一句话总结：

> 当前系统最核心的问题，不是模型不够强，而是架构不允许模型真正成为主控。

如果继续沿规则驱动方向修补，系统只会越来越像“安全但死板的 proposal chatbot”。

如果要回到最初设想，就必须把下一阶段明确改成：

> `模型主导理解与协商，规则只负责安全与执行校验`
