# AI 助手内联方案渲染与多方案交互需求 V1

> 文档状态：draft
> 版本：V1
> 创建日期：2026-05-15
> 适用范围：智能助手输出文本、对话气泡渲染、proposal 展示与确认协议、多方案生成、浏览器级验收
> 关联文件：`frontend/src/components/AssistantPanel.vue`、`backend/app/services/assistant.py`、`backend/app/services/assistant_proposal_manager.py`、`backend/app/assistant_agents/specialists/understanding.py`

---

## 1. 背景

当前智能助手主要以纯文本方式输出结果，并在对话区之外使用独立的“待确认方案”容器展示 pending proposal。这个设计虽然安全，但体验上存在几个问题：

1. 纯文本回复显得机械、死板，缺少可操作的交互元素。
2. “AI 回复”和“待确认方案卡片”分离，用户需要在两个区域之间切换注意力。
3. proposal 本质上是 AI 回复的一部分，但现在像是系统额外弹出的工作流容器。
4. 当前多数场景只生成一种方案，不足以覆盖任务拆分、时间不明确、冲突处理等真实决策场景。
5. 方案确认按钮和拒绝按钮的交互语义还不够自然，用户更希望直接点选“方案 A / B / C”。

因此，需要把 AI 助手从“文字回复 + 外部待确认栏”升级为“对话气泡内可渲染结构化交互组件”的体验。

---

## 2. 核心目标

### 2.1 产品目标

智能助手在生成待确认方案时，应直接在助手对话气泡中渲染方案选项卡。用户看到的应该像是：

```text
AI：我整理了几种安排方式，你可以选一个：

[方案 A：今天 15:00-16:00 去图书馆]
[方案 B：今天 16:30-17:30 去图书馆]
[方案 C：今晚 19:00-20:00 去图书馆]
[拒绝全部方案]
```

而不是：

```text
AI：我生成了方案。

页面上方/侧边再出现一个独立的待确认方案容器。
```

### 2.2 技术目标

1. 后端回复中携带结构化渲染信号，告诉前端该消息需要渲染方案选项卡。
2. 前端在助手消息气泡内渲染方案卡片、方案按钮、拒绝全部按钮。
3. 用户点击方案选项后，不直接调用业务 API，而是程序性发送固定用户提示词，例如 `接受 P3 方案B`。
4. 点击后该组选项立即进入不可点击状态，避免重复确认。
5. proposal-first 安全边界保持不变：确认前不写入 event/task/memory。

---

## 3. 术语定义

| 术语 | 含义 |
|---|---|
| inline proposal | 渲染在 AI 对话气泡内部的待确认方案组件 |
| proposal group | 一次 AI 回复中产生的一组候选方案，通常对应一个 pending proposal |
| option card | 方案 A / B / C 的可点击卡片 |
| reject-all option | 拒绝整组方案的卡片或按钮 |
| render signal | 后端返回给前端的结构化渲染参数，用于触发组件渲染 |
| protocol prompt | 前端点击后自动发送给助手的固定用户文本，如 `接受 P1 方案A` |

---

## 4. 总体交互设计

### 4.1 新体验

当助手生成 proposal 时，助手消息仍然正常出现在聊天流中，但消息气泡内部除了文本，还要包含可点击的方案选项卡。

示例：

```text
用户：下午我想去图书馆

AI：你只说了大概时间，我可以帮你自动安排几个可选时间：

[方案 A]
今天 14:00-15:00
避开午休，适合短时间自习

[方案 B]
今天 15:30-16:30
和已有日程间隔更充足

[方案 C]
今天 19:00-20:30
晚间整块时间更完整

[拒绝全部方案]
```

用户点击 `方案 B` 后：

```text
用户：接受 P1 方案B
AI：已按方案 B 确认并执行。
```

### 4.2 旧体验需要废弃或降级

独立“待确认方案”容器不再作为主要展示入口。

允许保留为调试/兼容入口，但默认用户体验应满足：

1. 新 proposal 优先内联显示在助手消息中。
2. 用户无需去另一个容器找待确认方案。
3. 内联方案和数据库 proposal 状态保持同步。
4. 如果消息历史中已有已执行/已拒绝方案，刷新后应显示为不可点击状态。

---

## 5. 输出渲染能力需求

### 5.1 助手消息结构

助手消息应支持文本和结构化 UI blocks。

建议结构：

```json
{
  "role": "assistant",
  "content": "我整理了几种安排方式，你可以选一个：",
  "render_blocks": [
    {
      "type": "proposal_options",
      "proposal_id": 123,
      "protocol_label": "P1",
      "status": "pending",
      "selection_mode": "single",
      "options": [
        {
          "option_id": "A",
          "title": "下午 2 点开始",
          "summary": "今天 14:00-15:00 去图书馆",
          "rationale": "避开午休，时间较完整",
          "recommended": true,
          "prompt_on_click": "接受 P1 方案A"
        },
        {
          "option_id": "B",
          "title": "下午 3 点半开始",
          "summary": "今天 15:30-16:30 去图书馆",
          "rationale": "和已有日程间隔更充足",
          "recommended": false,
          "prompt_on_click": "接受 P1 方案B"
        }
      ],
      "reject_option": {
        "title": "拒绝全部方案",
        "prompt_on_click": "拒绝 P1 全部方案"
      }
    }
  ]
}
```

### 5.2 渲染组件类型

第一阶段至少支持：

1. `proposal_options`：方案选项卡组。
2. `clarification_choices`：澄清选择，例如“让我补时间 / 自动安排”。
3. `status_receipt`：执行结果回执，例如“已创建日程”。

后续可扩展：

1. `time_slot_picker`：时间段选择。
2. `event_preview`：单个日程预览。
3. `task_split_preview`：任务拆分预览。
4. `conflict_resolution_options`：冲突解决方案。

### 5.3 Markdown 与结构化组件关系

文本仍可用 Markdown 渲染，但结构化 UI 不应依赖 Markdown 解析。

要求：

1. 文本内容用于解释和摘要。
2. 方案选项必须来自结构化字段，不能从 Markdown 文本里正则提取。
3. 前端渲染时，Markdown 文本和 render blocks 按消息内顺序展示。

---

## 6. 方案生成规则

### 6.1 临时性明确日程

如果用户给出完整、明确的一次性日程信息，只需要生成一种方案。

示例：

```text
明天下午3点到4点去学校开会
```

预期：

1. 生成一个 proposal。
2. 内部可以只有 `方案 A`。
3. 仍要有 `拒绝全部方案`。
4. 点击 `方案 A` 即确认。

### 6.2 任务或任务拆分

如果用户是在创建任务，或要求把任务拆成多个日程，必须生成多种方案，至少 3 种。

示例：

```text
我这周要复习英语，帮我安排一下
```

可选方案：

1. 方案 A：集中式，连续两晚长时间复习。
2. 方案 B：分散式，每天短时间复习。
3. 方案 C：冲刺式，临近截止日期集中安排。

要求：

1. 每个方案都要说明时间安排、优缺点、适用场景。
2. 推荐方案必须有明确理由。
3. 点击任一方案后，按该方案生成 task 或 task schedule proposal 的执行动作。

### 6.3 大概时间 + 明确地点

如果用户只给出大概时间和地点，没有精准时间，系统应给用户两类选择：

示例：

```text
下午我想去图书馆
```

预期：

1. 助手先识别为信息不完整但可以自动安排。
2. 对话气泡内显示澄清选项：
   - `我来补充具体时间`
   - `你帮我自动安排`
3. 如果用户选择自动安排，AI 生成至少 3 个时间方案。
4. 这些时间方案以 option cards 形式内联展示。

可选时间方案示例：

1. 方案 A：下午早些时候，例如 14:00-15:00。
2. 方案 B：下午中段，例如 15:30-16:30。
3. 方案 C：下午晚些时候，例如 17:00-18:00。

### 6.4 存在冲突的日程

如果用户指定时间与已有日程冲突，必须生成多方案。

示例：

```text
明天下午3点去学校开会
```

当前 15:00-16:00 已有图书馆自习。

预期至少包含：

1. 方案 A：仍按原时间创建，但明确冲突风险。
2. 方案 B：调整到最近空档。
3. 方案 C：缩短或移动相邻日程后安排。

### 6.5 任务时间预算不明确

示例：

```text
帮我安排复习
```

预期：

1. 不应直接生成方案。
2. 应以内联澄清选项询问：
   - `补充科目和截止时间`
   - `按默认复习计划生成`
   - `先创建一个待办`
3. 如果用户选择默认复习计划，生成至少 3 种任务拆分方案。

### 6.6 用户表达偏好

示例：

```text
我想轻松一点安排论文，不要太满
```

预期：

1. 多方案应体现偏好差异。
2. 至少包含：
   - 保守轻量方案。
   - 平衡方案。
   - 高强度方案。

### 6.7 多目标复合请求

示例：

```text
明天下午3点去学校开会，晚上8点提醒我复习英语
```

预期：

1. 不得静默只处理一个目标。
2. 可以生成两个 proposal group。
3. 每个 group 内部都有自己的选项和拒绝全部。
4. 用户可以分别接受其中一个、拒绝另一个。

### 6.8 用户要求“给我几个选择”

示例：

```text
下周帮我安排三次健身，给我几个选择
```

预期：

1. 至少生成 3 个方案。
2. 每个方案包含三次健身的时间分布。
3. 方案之间要有真实差异，而不是同一方案换文案。

---

## 7. 点击操作逻辑

### 7.1 option card 即按钮

方案 A / B / C 本身就是按钮，不再额外显示“确认”按钮。

要求：

1. 点击方案卡片 = 接受该方案。
2. 每个 proposal group 最后必须有 `拒绝全部方案`。
3. 不再显示独立的“确认”和“拒绝”按钮组合。

### 7.2 单选锁定

同一 proposal group 必须单选。

状态规则：

1. 初始状态：所有 option card 和 reject-all 可点击。
2. 点击任一方案后：
   - 当前选项显示为 selected / accepted。
   - 其他方案立即 disabled。
   - reject-all disabled。
3. 点击拒绝全部后：
   - reject-all 显示为 rejected。
   - 所有方案 disabled。
4. 页面刷新后，应根据 proposal status 恢复 disabled 状态。

### 7.3 点击后发送用户提示词

点击不直接调用 proposal API。

点击方案 A 时，前端应程序性发送：

```text
接受 P1 方案A
```

点击方案 B 时：

```text
接受 P1 方案B
```

点击拒绝全部：

```text
拒绝 P1 全部方案
```

要求：

1. 这条文本应作为用户消息出现在对话区。
2. 后端通过现有 proposal 文本协议解析。
3. 业务写入仍由后端 proposal executor 完成。
4. 前端不得直接调用 `/assistant/proposals/{id}/confirm`、`reject`、`revise` 作为用户主流程。

### 7.4 输入框行为

用户点击方案卡片后，前端有两种可接受实现：

推荐实现：

1. 程序性将 `接受 P1 方案A` 填入主输入框。
2. 立即自动发送。
3. 对话区出现这条用户消息。

备选实现：

1. 程序性将 `接受 P1 方案A` 填入主输入框。
2. 用户仍需按发送。

V1 推荐采用“填入并自动发送”，减少无意义点击。

---

## 8. 状态同步需求

### 8.1 前端本地状态

点击后前端应立即锁定当前 option group，避免重复点击。

本地状态建议：

```ts
type LocalInlineProposalState = {
  proposalId: number;
  selectedOptionId?: string;
  rejected?: boolean;
  submittedPrompt: string;
};
```

### 8.2 后端状态

后端 proposal 状态仍然是权威来源。

状态映射：

| proposal status | 前端显示 |
|---|---|
| `pending` | 可点击 |
| `accepted` / `execution_pending` | 已提交，全部 disabled |
| `executed` | 显示已执行 |
| `rejected` | 显示已拒绝 |
| `superseded` / `expired` | 显示已失效 |
| `execution_failed` | 显示失败，可提供“重试此方案”交互 |

### 8.3 刷新恢复

刷新页面后：

1. 已 pending 的 inline proposal 仍应显示可点击。
2. 已 executed/rejected 的 inline proposal 应显示不可点击。
3. 如果聊天历史中消息有 render block，但 proposal 数据已不存在，应显示“该方案已不可用”。

---

## 9. 后端需求

### 9.1 proposal payload 扩展

proposal `payload_json` 应包含用于前端渲染的稳定字段。

建议字段：

```json
{
  "protocol_label": "P1",
  "render": {
    "type": "proposal_options",
    "selection_mode": "single",
    "inline": true
  },
  "options": [
    {
      "option_id": "A",
      "title": "平衡安排",
      "summary": "...",
      "rationale": "...",
      "actions": []
    }
  ]
}
```

### 9.2 assistant message render blocks

生成 proposal 的助手回复应保存 render blocks。

可选实现：

1. 在 `assistant_messages` 增加 `render_json` 字段。
2. 或在现有消息 metadata 中保存 `render_blocks`。
3. 或通过消息内容旁路接口返回，但必须支持刷新后恢复。

推荐：增加或复用结构化 metadata 字段，保证历史消息可回放。

### 9.3 文本协议扩展

后端应支持以下用户消息：

```text
接受 P1 方案A
接受 P2 方案B
拒绝 P1 全部方案
拒绝全部 P3
```

兼容旧协议：

```text
确认 P1 方案A
P1 先不要安排
```

### 9.4 多方案生成策略

后端 proposal builder 需要支持多 option。

最低要求：

1. 单次明确日程：1 个 option。
2. 冲突日程：至少 2 个 option。
3. 任务拆分：至少 3 个 option。
4. 大概时间自动安排：至少 3 个 option。
5. 用户明确要求多个选择：至少 3 个 option。

### 9.5 安全约束

1. LLM 只能生成候选理解和候选方案，不得直接写库。
2. 所有 option actions 必须经过 deterministic validation。
3. 未点击 option 或拒绝前，proposal 保持 pending，业务表不变。
4. 点击 option 后仍然走 assistant message -> protocol parser -> proposal executor。

---

## 10. 前端需求

### 10.1 AssistantPanel 渲染

`AssistantPanel.vue` 应支持消息内 render blocks。

渲染顺序：

1. 文本说明。
2. inline proposal options。
3. 状态回执或辅助说明。

### 10.2 视觉要求

方案选项卡应具备：

1. 方案编号：A / B / C。
2. 标题。
3. 时间或任务安排摘要。
4. 推荐标识。
5. 简短理由。
6. 当前状态：可选、已选、已拒绝、已失效、执行失败。

交互样式：

1. hover 时体现可点击。
2. disabled 时明显变灰。
3. selected 时有明确高亮。
4. reject-all 不应视觉上比方案更强，避免误点。

### 10.3 移除独立待确认主入口

V1 完成后，独立“待确认方案”容器应默认隐藏或降级为调试模式。

可以保留以下替代入口：

1. 对话顶部小型“还有 N 个待确认方案”提示。
2. 点击后跳转到包含 inline proposal 的历史消息。
3. 开发模式下显示 proposal debug list。

### 10.4 可访问性

1. option card 必须是 button 或具有正确 ARIA role。
2. 键盘可 Tab 访问。
3. Enter/Space 可选择。
4. disabled 状态必须反映到 DOM 属性。

---

## 11. 额外实际场景补充

### 11.1 用户只给目标，不给时间

```text
我想去学校
```

预期：

1. 不直接生成具体日程。
2. 提供澄清选项：
   - `补充时间`
   - `让 AI 推荐时间`
   - `先记为待办`

### 11.2 用户给出多个模糊约束

```text
这两天找个不太累的时间复习英语
```

预期：

1. 生成至少 3 种时间方案。
2. 每种方案说明为什么“不太累”。

### 11.3 用户有已有日程冲突

```text
明天下午安排健身
```

如果下午已有多个日程，预期：

1. AI 自动找空档。
2. 给出多个空档方案。
3. 不得强行塞进冲突时间。

### 11.4 用户要求高效率

```text
这周把论文推进快一点，给我几个方案
```

预期：

1. 方案 A：高强度。
2. 方案 B：平衡。
3. 方案 C：保守但稳定。

### 11.5 用户临时改变主意

```text
算了，不选了
```

如果当前消息紧跟某个 inline proposal group：

1. 应映射为拒绝该 proposal group。
2. 如果多组 pending，应澄清拒绝哪一个。

### 11.6 用户想修改某个方案

```text
把方案B改成晚上8点
```

预期：

1. 如果当前只有一个 inline proposal group，系统应修改该 group 的 B 方案或生成新 proposal。
2. 如果有多个 group，必须要求明确 `P1` / `P2`。
3. 旧 proposal 状态应进入 superseded/revised，新 proposal 内联渲染。

### 11.7 用户选择后又点其他方案

预期：

1. 前端禁止第二次点击。
2. 后端幂等保护，不重复执行。
3. 对话中只出现一次用户接受消息。

### 11.8 执行失败

如果用户选择方案后执行失败：

1. 原 option group 显示 execution_failed。
2. 可显示 `重试该方案` 交互。
3. 点击重试仍发送用户消息：`重试 P1 方案A`。

---

## 12. 浏览器级验收要求

所有验收必须通过真实浏览器页面操作，不允许只调用后端 API。

### 12.1 INT-INLINE-P0-001 单方案内联渲染

输入：

```text
明天下午3点到4点去学校开会
```

预期：

1. AI 对话气泡中出现方案 A option card。
2. 不出现独立主待确认容器。
3. 点击方案 A 后，对话区出现用户消息 `接受 P1 方案A`。
4. proposal executed，event 新增 1 条。

### 12.2 INT-INLINE-P0-002 拒绝全部

前置：存在一个 inline proposal group。

操作：点击 `拒绝全部方案`。

预期：

1. 对话区出现用户消息 `拒绝 P1 全部方案`。
2. proposal rejected。
3. event/task 无新增。
4. 所有 option disabled。

### 12.3 INT-INLINE-P0-003 单选锁定

前置：存在 A/B/C 三个方案。

操作：点击方案 B。

预期：

1. B 显示已选中。
2. A/C/reject-all disabled。
3. 快速连点不会产生第二条用户消息。
4. 后端只执行一次。

### 12.4 INT-INLINE-P0-004 模糊时间自动安排

输入：

```text
下午我想去图书馆
```

预期：

1. AI 先给出澄清选择：补具体时间 / 自动安排。
2. 点击自动安排后，生成至少 3 个时间方案。
3. 点击任一时间方案后，创建对应日程。

### 12.5 INT-INLINE-P0-005 任务拆分三方案

输入：

```text
这周帮我安排复习英语
```

预期：

1. 生成至少 3 个任务拆分方案。
2. 方案之间时间分布不同。
3. 点击其中一个后，创建 task schedule proposal 对应的日程切片。

### 12.6 INT-INLINE-P0-006 冲突多方案

前置：明天下午 15:00-16:00 已有日程。

输入：

```text
明天下午3点去学校开会
```

预期：

1. AI 内联展示至少 2 个方案。
2. 至少一个方案明确说明冲突。
3. 至少一个方案是调整到空档。
4. 点击调整方案后，不覆盖原日程。

### 12.7 INT-INLINE-P0-007 刷新恢复

前置：存在 pending inline proposal。

操作：刷新浏览器。

预期：

1. 历史消息中的 option cards 仍显示。
2. pending 状态仍可点击。
3. 点击后可正常确认执行。

### 12.8 INT-INLINE-P0-008 网络与 API 约束

操作：点击任意方案 option card。

预期：

1. 网络请求不得出现 `/assistant/proposals/{id}/confirm` 作为用户主流程。
2. 必须出现 assistant message 发送。
3. 数据库中 assistant_messages 有 `接受 Pn 方案X`。

---

## 13. 完成定义

本需求完成必须同时满足：

1. AI 回复支持结构化 render blocks。
2. proposal options 可内联渲染在助手消息气泡中。
3. 新 proposal 默认不再依赖独立待确认容器作为主入口。
4. option card 本身就是接受按钮。
5. 每个 proposal group 都有拒绝全部方案。
6. option group 点击后单选锁定，不能重复点击。
7. 点击后通过主助手消息发送协议文本，不直调 proposal API。
8. 明确临时日程可单方案。
9. 任务拆分、模糊时间、冲突、用户要求多个选择时至少给 3 个或多个合理方案。
10. 刷新后 inline proposal 状态可恢复。
11. 后端仍保持 proposal-first，确认前不写入业务表。
12. 浏览器级 P0 验收全部通过。

---

## 14. 非目标

V1 不要求：

1. 实现任意富文本 UI 生成器。
2. 让 LLM 直接输出前端组件代码。
3. 让前端从 Markdown 中正则解析方案。
4. 废弃后端 proposal 状态机。
5. 允许点击 UI 后绕过助手协议直接写库。

---

## 15. 推荐实施顺序

1. 定义 assistant message render block 数据结构。
2. 扩展后端 proposal reply，把 proposal options 写入消息 render metadata。
3. 扩展前端 AssistantPanel，支持消息内 `proposal_options` 渲染。
4. 将 option card 点击映射为 `接受 Pn 方案X` / `拒绝 Pn 全部方案`。
5. 实现单选锁定和刷新状态恢复。
6. 将独立待确认容器降级为调试/辅助入口。
7. 扩展 proposal builder：任务拆分、模糊时间、冲突场景生成多方案。
8. 补齐文本协议：接受/拒绝全部/重试/修改方案。
9. 编写后端测试。
10. 编写并执行浏览器级真实验收。
