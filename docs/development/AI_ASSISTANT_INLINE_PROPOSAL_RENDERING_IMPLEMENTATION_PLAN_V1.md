# AI 助手内联方案渲染与多方案交互实施任务书 V1

## 计划元数据

- Plan ID: `ai-assistant-inline-proposal-rendering-v1`
- Version: `v1`
- Last updated: `2026-05-16 00:18 +08:00`
- Canonical progress file: `E:\GraduationProject\docs\development\AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_IMPLEMENTATION_PLAN_V1.md`
- Source requirement file: `E:\GraduationProject\docs\development\AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_REQUIREMENTS_V1.md`
- Related browser scenario file: `E:\GraduationProject\docs\development\AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`
- Current branch: `codex/assistant-browser-acceptance`
- Current active phase: `completed`
- Execution readiness: `completed`

## 目标

把 `AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_REQUIREMENTS_V1.md` 中的“内联方案渲染 + 多方案交互”需求，拆解为可持续执行、可分阶段验收、可浏览器级回归、可失败修复再验收的工程任务书。

这个任务书不是单纯的功能清单，而是要把需求变成一条可追踪的工程路线：

```text
需求冻结
  -> 数据结构扩展
  -> 后端 render block / protocol 扩展
  -> 前端内联卡片渲染
  -> 真实浏览器验收
  -> 失败反馈修复
  -> 复测闭环
  -> 全功能终验
```

最终目标不是“代码能跑”，而是：

1. 内联方案卡片在助手对话气泡内稳定显示。
2. 方案点击只通过助手消息协议流转，不绕过助手。
3. 多方案、拒绝全部、单选锁定、刷新恢复都符合预期。
4. 所有浏览器级验收都通过后，再做一次全功能真实浏览器实测。
5. 全功能实测通过后，才允许宣告完成。
6. 用户选择或拒绝方案后，内联方案卡片保留在原助手气泡中，显示为灰色不可点击终态，而不是从对话中消失。

---

## 范围与约束

### In scope

1. 助手消息支持结构化 render blocks。
2. proposal options 内联渲染到 assistant chat bubble。
3. 从独立“待确认方案”容器迁移到消息内 inline proposal。
4. 方案卡片点击 -> 主输入框协议消息。
5. 单选锁定、拒绝全部、执行失败重试、刷新恢复。
6. 多方案生成策略：
   - 明确一次性日程：单方案即可。
   - 任务或任务拆分：至少 3 方案。
   - 大概时间 / 冲突 / 需要选择时：至少 3 方案。
7. 浏览器级验收修复机制。
8. 最后执行一次全功能浏览器实测。

### Out of scope

1. 不把 LLM 直接开放为前端组件生成器。
2. 不移除 proposal-first 安全边界。
3. 不允许前端直接调用 proposal confirm/reject 作为用户主流程。
4. 不要求本阶段全面重写 assistant agent 架构。
5. 不要求一次性废弃所有 legacy 容器，允许保留调试入口，但不能成为主体验。

### Constraints

1. 所有业务写入仍必须经过 proposal 确认。
2. proposal options 必须来自后端结构化数据，不能从 Markdown 反解。
3. option 卡片必须单选锁定，禁止重复点击。
4. 点击动作必须最终变成用户消息协议文本。
5. 任何 browser-level failure 都必须优先修复后再复测，不允许“记录失败后继续宣告完成”。
6. 所有浏览器验收记录必须可回溯，且要保留输入、点击、网络、数据库与复测证据。
7. 所有 P0/P1 验收都通过之后，还必须额外执行一次全功能真实浏览器实测，才能进入结案判断。

---

## 阶段依赖与门禁

| 阶段 | 依赖 | 进入条件 | 退出条件 |
|---|---|---|---|
| Phase 0 | 需求冻结 | 需求文档完成 | 数据结构、协议、验收标准全部明确 |
| Phase 1 | Phase 0 | 已确认前端/后端耦合边界 | render block schema 与消息协议可落地 |
| Phase 2 | Phase 1 | 可在后端生成 proposal group | proposal 具备 options / reject-all / protocol_label |
| Phase 3 | Phase 2 | 后端已支持 render metadata | 前端可在消息气泡内渲染 inline proposal |
| Phase 4 | Phase 3 | inline card 可显示 | 点击后可通过协议消息确认 / 拒绝 / 重试 |
| Phase 5 | Phase 4 | 单方案渲染稳定 | 多方案场景、任务拆分、模糊时间、冲突场景全部覆盖 |
| Phase 6 | Phase 5 | browser-level P0 场景稳定 | 修复闭环机制生效，回归可重复运行 |
| Phase 7 | Phase 6 | P0/P1 场景通过 | 全功能真实浏览器实测通过 |

Go / No-Go：

1. 任一阶段若破坏 proposal-first，立刻停止推进。
2. 任一阶段若方案点击绕过助手协议，立即回退该变更。
3. 任一阶段若浏览器验收失败，必须先修复再复测，不能跳过。
4. 最终必须额外执行一次全功能实测，不能只靠局部 P0 通过收尾。
5. 只要存在未关闭的浏览器级失败项，就不能把任务状态标记为完成。

---

## 决策记录

### Verified facts

1. 需求源文件已存在：`docs/development/AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_REQUIREMENTS_V1.md`。
2. 当前系统已有 proposal-first 方向，确认前不应写入业务表。
3. 之前已修复前端待确认方案按钮绕过助手的问题，按钮应发送助手协议文本。
4. 浏览器级验收必须使用真实前端页面、真实后端和干净 SQLite 数据库。
5. 独立 pending proposal 容器不再是目标主体验，内联渲染是目标主体验。

### Locked decisions

1. V1 先实现有限 render block，而不是通用 UI 生成器。
2. `proposal_options` 是第一优先级组件；`clarification_choices` 和 `status_receipt` 可作为后续同一结构扩展。
3. 方案点击只能发送协议文本，例如 `接受 P1 方案A`，不得直接调用 confirm/reject API 作为用户主流程。
4. 浏览器验收失败时，必须执行“定位 -> 最小修复 -> 后端测试 -> 前端构建或相关检查 -> 浏览器复测”的闭环。
5. “没有任何 bug”按工程验收语义处理：P0/P1 场景和最终全功能浏览器实测无阻塞缺陷、无已知未关闭回归项，不能承诺数学意义上的绝对无 bug。

### Active assumptions

1. 可以优先在现有 assistant message API/schema 上扩展 `render_blocks`，必要时再增加持久化字段或从 proposal 数据稳定回放。
2. 现有 proposal `payload_json` 可以承载 option card 所需的稳定字段。
3. 旧的 pending proposal 容器可以短期保留为兼容/调试入口，但新 proposal 的用户主入口必须是聊天气泡内卡片。
4. 当前 dirty worktree 中已有改动属于用户或前序工作，后续实现不得回退。

### Open questions

1. `render_blocks` 最终应采用新 DB 字段、消息 metadata，还是从 proposal 表回放，需要在 Phase 1 读代码后确定。
2. 多方案生成第一版是规则生成、LLM 辅助生成，还是混合生成，需要结合当前 assistant conductor 实现确定。
3. 执行失败重试 `重试 P1 方案A` 是否进入 V1 P0，还是作为 P1，在实现时根据当前执行失败处理能力确认。
4. 浏览器验收记录是否要按用例拆分为多份文件，还是先汇总到单一报告后再按失败条目拆分，需要在 Phase 5 固化。

---

## 交付切片

### 1. 数据与协议切片

目标：把 inline proposal 变成后端可返回、前端可消费的稳定数据结构。

具体任务：

1. 定义 assistant message 的 `render_blocks` / `render_json` 结构。
2. 在 proposal payload 中加入稳定渲染字段：
   - `protocol_label`
   - `render.type`
   - `selection_mode`
   - `options`
   - `reject_option`
3. 扩展文本协议：
   - `接受 P1 方案A`
   - `接受 P1 方案B`
   - `拒绝 P1 全部方案`
   - `拒绝全部 P1`
   - 兼容旧语法：`确认 P1 方案A`、`P1 先不要安排`
4. 定义单选锁定状态字段。

产出：

- 后端 schema
- proposal payload 扩展
- protocol parser 扩展

验收：

- proposal 数据可表达多方案。
- UI 能只靠后端数据恢复 inline block。
- 协议文本可双向追踪。

### 2. 后端 proposal group 切片

目标：支持一个 proposal group 内多 option，而不是只输出单个方案。

具体任务：

1. 修改 proposal builder，让以下场景支持多方案：
   - 任务拆分
   - 模糊时间自动安排
   - 日程冲突
   - 用户要求“给我几个选择”
2. 明确单方案场景：
   - 时间、地点、目标都明确的一次性日程，保留 1 方案。
3. 为每个 option 写清：
   - 标题
   - 摘要
   - 理由
   - 是否推荐
   - 点击后 prompt
4. 增加 reject-all option。

产出：

- proposal builder 改造
- 多方案单测

验收：

- 明确单次日程仍可单方案。
- 任务与模糊时间至少 3 方案。
- 冲突场景至少 2 方案。

### 3. 前端 inline 渲染切片

目标：把 proposal 内联渲染进助手气泡。

具体任务：

1. 扩展 `AssistantPanel.vue` 渲染 render blocks。
2. 在 assistant message 内显示：
   - 方案卡片
   - 推荐标识
   - 拒绝全部按钮
   - 状态标签
3. 去掉新增方案时默认弹出的独立待确认主容器作为主路径。
4. 保留兼容调试显示，但不能干扰主体验。

产出：

- `AssistantPanel.vue`
- 必要的样式与状态管理

验收：

- proposal 出现时，卡片在对话气泡里。
- 页面不需要切到另一个容器找方案。

### 4. 点击协议切片

目标：点击选项卡必须变成协议化用户消息。

具体任务：

1. option card 点击 -> 发送固定用户文本。
2. 方案 A/B/C 都是按钮本体，不再额外需要“确认/拒绝”二级按钮。
3. 每个 group 最后有拒绝全部。
4. 点击后同组全部锁定，卡片保留并变为灰色不可点击状态。
5. 点击后插入主输入框或直接发送，推荐自动发送。

产出：

- 前端点击处理
- 本地锁定状态
- 重复点击保护

验收：

- 网络中只出现助手消息发送。
- 不出现用户直调 proposal confirm/reject 作为主流程。

### 5. 状态恢复与幂等切片

目标：刷新后 inline proposal 仍能正确恢复。

具体任务：

1. 根据 proposal status 恢复是否可点击。
2. 已确认 / 已拒绝 / 已失效项显示 disabled。
3. 已执行项显示回执，不再允许点击。
4. 重复点击和重复发送必须幂等。
5. 刷新后历史内联卡片必须按 proposal 终态恢复为 `已执行` / `已拒绝` / `已替换` 等灰色不可点击状态。

产出：

- 状态恢复逻辑
- 幂等测试

验收：

- 刷新后状态不乱。
- 重复确认不会重复执行。

### 6. 场景生成切片

目标：补齐多方案生成规则，覆盖真实使用场景。

至少覆盖：

1. 明确单次日程。
2. 任务拆分成多个日程。
3. 大概时间 + 明确地点。
4. 冲突日程。
5. 用户想要多个选择。
6. 用户只说“给我看看方案”。
7. 用户临时改变主意。
8. 用户只想拒绝全部。

产出：

- 后端用例
- 浏览器用例

验收：

- 每类场景输出符合预期的 option 结构。

### 7. 浏览器级验收与反馈闭环切片

目标：把“实测失败后如何修复、如何复测、何时结案”固化为固定流程。

具体任务：

1. 为每个 P0/P1 场景定义独立真实浏览器用例。
2. 为每个用例定义统一证据模板：
   - 用户输入
   - AI 回复摘要
   - inline proposal 证据
   - 点击动作
   - 网络请求摘要
   - 数据库写入结果
   - console / request 错误
   - PASS / FAIL
3. 为失败用例定义固定闭环：
   - 定位根因
   - 最小修复
   - 后端测试补强
   - 必要时前端构建或静态检查
   - 浏览器复测
4. 固化最终全功能终验：
   - 所有 P0/P1 验收通过后，必须再跑一次完整真实浏览器实测
   - 终验覆盖普通对话、内联方案、多方案、拒绝全部、修改、刷新恢复、冲突处理、幂等执行
   - 终验结果必须单独记录，不能混在中途回归里

产出：

- 浏览器验收记录文件
- 修复闭环记录
- 最终全功能实测报告

验收：

- 所有失败项都能追溯到修复和复测记录。
- 终验通过后才能宣布任务完成。

---

## 详细阶段计划

### Phase 0 - 设计锁定与验收基线

任务：

1. 锁定需求文档。
2. 锁定 proposal-first 约束。
3. 锁定浏览器级验收路径。
4. 确认当前 P0/P1 现有回归状态。

完成条件：

- 文档和测试计划一致。
- 失败时有明确修复优先级。
- 本任务书包含执行台账、浏览器验收模板和最终完成门槛。

验证方法：

1. 人工检查本计划是否能直接指导实现。
2. 确认需求、实现切片、验收机制没有互相矛盾。
3. 确认“所有验收完成后再做一次全功能终验”的门槛已经写死。

### Phase 1 - 协议与渲染模型

任务：

1. 定义 render blocks schema。
2. 定义 proposal group 与 option card 数据。
3. 定义 reject-all 协议。
4. 定义 option 锁定状态。

完成条件：

- 后端能输出结构化内联信息。
- 前端能消费该结构，不再依赖独立待确认容器。

验证方法：

1. 后端单测覆盖 assistant message schema 序列化。
2. 后端单测覆盖 `接受 P1 方案A`、`拒绝 P1 全部方案`。
3. 若涉及 DB 字段，迁移在干净库上可成功运行。
4. 消息回放可以恢复 inline block，不依赖临时前端状态。

### Phase 2 - 多方案生成

任务：

1. 单方案 / 多方案规则分流。
2. 任务拆分至少 3 方案。
3. 模糊时间至少 3 方案。
4. 冲突至少 2 方案。

完成条件：

- 生成逻辑稳定可测。
- 各方案之间有真实差异，不是同文案换壳。

验证方法：

1. 后端单测覆盖明确日程单方案。
2. 后端单测覆盖任务拆分三方案。
3. 后端单测覆盖模糊时间三方案。
4. 后端单测覆盖冲突场景至少两个方案。
5. 各方案之间必须有真实差异，而不是同一方案换文案。

### Phase 3 - 前端内联卡片

任务：

1. 在 AssistantPanel 中渲染 inline cards。
2. 文本和卡片按消息顺序展示。
3. 删除/降级独立待确认主容器。

完成条件：

- 方案出现在 AI 气泡中。
- 页面不割裂。

验证方法：

1. `npm run build` 通过。
2. 浏览器中 assistant 气泡内可见 option card。
3. 独立 pending proposal 容器不再作为新增 proposal 的主入口。
4. 刷新后消息历史里的 inline card 仍可按状态恢复。

### Phase 4 - 点击与协议闭环

任务：

1. 点击方案卡片发送固定协议文本。
2. 点击拒绝全部发送固定协议文本。
3. 自动锁定同组其余选项。

完成条件：

- 网络层只通过助手消息通道。
- 后端协议能解析所有新文本。

验证方法：

1. Playwright 监听网络请求，点击方案时不得出现 proposal confirm/reject 主流程请求。
2. 对话区出现用户协议消息。
3. 数据库 `assistant_messages` 保存协议消息。
4. 快速连点不产生重复消息或重复业务写入。
5. 同一 proposal group 点击后必须锁定全部其余选项。

### Phase 5 - 浏览器级验收闭环

任务：

1. 为每个 P0 场景配置独立干净库。
2. 每条用例真实浏览器操作。
3. 记录用户每轮输入、assistant 每轮回复、proposal 状态、events/tasks 写入、网络请求、console 错误。
4. 若失败，按“先修复、再复测”的机制推进。

完成条件：

- P0 场景全部通过。
- 失败记录都能对应修复和复测。
- 每个失败项都已经补上对应后端测试或回归保护。

验证方法：

1. 每条用例使用干净 SQLite 库或明确清库。
2. 每条用例记录截图、网络摘要、数据库核验和结果。
3. 失败项必须有修复文件路径、测试名和复测结果。
4. 任何 FAIL 不能直接跳过，必须进入修复队列。

### Phase 6 - 全功能真实实测

任务：

1. 在所有 P0/P1 验收通过后，再额外进行一次全功能真实浏览器实测。
2. 全功能实测范围包括：
   - 普通消息
   - inline proposal
   - 多方案选择
   - 拒绝全部
   - 任务拆分
   - 模糊时间
   - 冲突场景
   - 刷新恢复
   - 执行失败重试
3. 生成最终验收报告。

完成条件：

- 全功能实测通过。
- 无阻塞性 bug。
- 验收报告可回溯。

验证方法：

1. 使用新的干净 SQLite 库执行完整真实浏览器流程。
2. 覆盖新旧智能助手主流程，而不是只覆盖 inline proposal。
3. 生成最终验收报告到 `docs/development/browser_acceptance_runs/`。
4. 终验报告必须单独列出是否存在残余非阻塞风险。

---

## 浏览器级用例矩阵

### P0 必过用例

| ID | 场景 | 输入 / 操作 | 必须验证 |
|---|---|---|---|
| INLINE-P0-001 | 明确日程单方案 | `明天下午3点到4点去学校开会` | assistant 气泡内出现方案 A；点击后发送 `接受 P1 方案A`；event 仅新增 1 条 |
| INLINE-P0-002 | 拒绝全部 | 对 pending inline proposal 点击拒绝全部 | 发送 `拒绝 P1 全部方案`；proposal rejected；业务表无新增 |
| INLINE-P0-003 | 单选锁定 | A/B/C 三方案中点击 B，并快速连点其他卡片 | 仅 B 生效；其他 disabled；无重复用户消息；无重复写库 |
| INLINE-P0-004 | 模糊时间自动安排 | `下午我想去图书馆` -> 选择自动安排 | 先澄清；自动安排后至少 3 个时间方案；点击后创建对应日程 |
| INLINE-P0-005 | 任务拆分三方案 | `这周帮我安排复习英语` | 至少 3 个真实差异方案；点击后创建对应任务/日程切片 |
| INLINE-P0-006 | 冲突多方案 | 先建 15:00-16:00 日程，再输入同时间会议 | 至少 2 个方案；一个说明冲突；一个调整到空档；不覆盖旧日程 |
| INLINE-P0-007 | 刷新恢复 pending | 生成 pending inline proposal 后刷新页面 | 卡片仍在历史消息中；状态可点击；点击后正常执行 |
| INLINE-P0-008 | 网络约束 | 点击任意 option card | 不出现 direct confirm/reject 主流程；只通过助手消息提交 |

### P1 加强用例

| ID | 场景 | 输入 / 操作 | 必须验证 |
|---|---|---|---|
| INLINE-P1-001 | 多目标复合请求 | `明天下午3点去学校开会，晚上8点提醒我复习英语` | 不静默丢目标；可分别接受/拒绝 |
| INLINE-P1-002 | 修改某方案 | `把方案B改成晚上8点` | 单 pending 时能定位；多 pending 时要求明确 P 编号 |
| INLINE-P1-003 | 临时改变主意 | `算了，不选了` | 单 pending 映射拒绝；多 pending 先澄清 |
| INLINE-P1-004 | 执行失败重试 | 人为制造执行失败后点击重试 | 失败状态可见；重试仍走助手协议 |
| INLINE-P1-005 | 移动端渲染 | 小视口执行 P0-001/P0-003 | 文本不溢出；按钮可点；状态清晰 |

### 验收反馈闭环规范

每条浏览器用例都必须走同一个闭环，不允许口头跳过：

1. 在真实页面执行，不用 API 代替。
2. 记录失败前最后一个稳定 UI 状态。
3. 判断失败归因于前端渲染、点击协议、proposal 生成、状态机、LLM schema、测试脚本还是数据污染。
4. 只做最小修复，不顺带重构其他模块。
5. 修复后补对应后端测试，必要时补前端构建检查。
6. 回到真实浏览器复测同一条用例。
7. 复测通过后，才允许继续下一条用例。
8. 任一用例未闭环前，终验不得启动。

### 最终全功能实测矩阵

最终实测必须在 P0/P1 通过之后单独执行，使用新的干净数据库，至少覆盖：

1. 普通闲聊/非日程请求不会误生成 proposal。
2. 明确日程单方案创建。
3. 模糊时间澄清与自动安排。
4. 任务拆分多方案。
5. 方案修改。
6. 拒绝全部。
7. 多 pending proposal 下的明确选择与模糊选择。
8. 刷新恢复。
9. 网络断言：全程没有用户主流程 direct proposal confirm/reject。
10. 数据库断言：确认前无业务写入，确认后写入数量正确。

---

## 浏览器级验收修改机制

这是本任务书的核心要求之一。

### 1. 发现问题

每次浏览器级验收必须记录：

1. 输入文本。
2. AI 回复。
3. 是否出现 inline proposal。
4. 点击后是否正确发送协议文本。
5. proposal 状态是否符合预期。
6. 是否写入业务表。
7. 是否有 console error。
8. 是否有 4xx/5xx。

每条浏览器用例的记录格式：

```text
用例 ID:
数据库:
后端端口:
前端端口:
浏览器视口:
用户输入:
AI 回复摘要:
inline block 证据:
点击动作:
网络证据:
数据库证据:
console / request 错误:
结果: PASS / FAIL
若失败，根因分类:
修复文件:
新增测试:
复测结果:
```

### 2. 归类问题

每个失败必须归因到以下一类之一：

1. 前端渲染问题。
2. 点击协议问题。
3. 后端 proposal 生成问题。
4. 后端状态机问题。
5. LLM schema / fallback 问题。
6. 测试脚本问题。
7. 数据污染问题。

### 3. 修复原则

1. 先修最小修复，不重构整条链路。
2. 修复后必须补对应后端测试。
3. 后端测试通过后，再回到浏览器复测。
4. 复测仍失败，则继续修复，直到通过。

### 4. 复测顺序

推荐循环：

```text
browser fail
  -> classify root cause
  -> minimal patch
  -> backend test
  -> frontend build if needed
  -> browser retest
```

禁止：

1. 跳过 browser retest 直接宣布完成。
2. 用单测通过替代真实浏览器验证。
3. 用 mock 页面替代真实前端组件。

### 5. 验收停止条件

只有同时满足以下条件才允许进入最终宣告阶段：

1. 所有 P0 浏览器验收通过。
2. 所有新增后端回归测试通过。
3. 前端生产构建通过。
4. 全功能真实浏览器实测通过。
5. 最后一次浏览器实测无阻塞错误。

### 6. 推荐验收环境

后端：

```powershell
cd E:\GraduationProject\backend
$env:SQLITE_DB_PATH='./data/browser_inline_<case_id>_<yyyymmdd>.db'
$env:ASSISTANT_CONDUCTOR_MODE='proposal'
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port <backend_port>
```

前端：

```powershell
cd E:\GraduationProject\frontend
$env:VITE_API_BASE_URL='http://127.0.0.1:<backend_port>/api'
npm run dev -- --host 127.0.0.1 --port <frontend_port>
```

记录文件：

```text
docs/development/browser_acceptance_runs/assistant_inline_proposal_<yyyymmdd>.md
```

---

## 任务拆分清单

### 后端

1. 定义 render block schema。
2. 定义 proposal group / option card schema。
3. 扩展 proposal manager 以支持多方案。
4. 扩展文本协议 parser。
5. 扩展 understanding / planner 对多方案场景的识别。
6. 增加 LLM schema 校验和 fallback。
7. 增加必要单测。

### 前端

1. 改造 AssistantPanel，支持 inline card。
2. 消除独立待确认容器的主体验依赖。
3. 实现 option card 点击即发送协议文本。
4. 实现单选锁定、拒绝全部、刷新恢复。
5. 保证移动端和桌面端一致。

### 验收脚本

1. 维护独立 SQLite 库。
2. 逐条真实输入。
3. 逐条确认 / 拒绝 / 修改。
4. 每条记录证据。
5. 全功能实测脚本独立执行。

---

## 验收门槛

### P0 验收门槛

1. 单方案内联渲染。
2. 多方案单选与拒绝全部。
3. 模糊时间自动安排。
4. 任务拆分至少 3 方案。
5. 刷新恢复。
6. 点击后走助手协议。

### 最终完成门槛

1. P0 全部通过。
2. P1 相关新增场景全部通过。
3. 浏览器级修复闭环无遗漏。
4. 全功能实测通过。
5. 最终报告中没有未关闭 P0/P1 缺陷。
6. 已说明任何残余非阻塞风险和后续建议。
7. 没有任何未复测的失败记录遗留在验收文档中。

---

## 关键制品与环境

### Canonical docs

1. `docs/development/AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_REQUIREMENTS_V1.md`
2. `docs/development/AI_ASSISTANT_INLINE_PROPOSAL_RENDERING_IMPLEMENTATION_PLAN_V1.md`
3. `docs/development/AI_ASSISTANT_BROWSER_TEST_SCENARIOS_V1.md`

### Expected code areas

1. `backend/app/api/schemas.py`
2. `backend/app/models.py`
3. `backend/app/services/assistant.py`
4. `backend/app/services/assistant_runtime_text.py`
5. `backend/app/services/assistant_proposal_manager.py`
6. `backend/app/assistant_agents/specialists/understanding.py`
7. `backend/app/assistant_agents/specialists/planning.py`
8. `frontend/src/components/AssistantPanel.vue`
9. `frontend/src/stores/assistant.ts`
10. `frontend/src/i18n/index.ts`

### Required validation commands

后端重点回归：

```powershell
cd E:\GraduationProject\backend
.\.venv312\Scripts\python.exe -m pytest tests/test_assistant_text_protocol.py tests/test_assistant_conductor.py tests/test_assistant_proposal_revise.py tests/test_assistant_service.py
```

前端构建：

```powershell
cd E:\GraduationProject\frontend
npm run build
```

浏览器级验收：

```text
使用 Playwright MCP 或项目脚本在真实页面执行，不用后端 API 代替用户操作。
```

---

## 进度台账

| 阶段 | 状态 | 当前证据 | 下一步 |
|---|---|---|---|
| Phase 0 - 设计锁定与验收基线 | done | 需求文档与实施任务书已建立；浏览器验收机制已写入 | 进入 Phase 1 |
| Phase 1 - 协议与渲染模型 | done | 已完成 schema / render block / message 回放骨架；浏览器验收已通过单方案内联闭环 | 完成 |
| Phase 2 - 多方案生成 | done | proposal 生成路径已具备多 option 渲染载荷；模糊时间、冲突多方案、任务拆分三方案均已在 clean DB 浏览器复测通过 | 完成 |
| Phase 3 - 前端内联卡片 | done | AssistantPanel 已支持消息内 proposal_options 渲染；点击接受/拒绝后内联卡片保留在原气泡中并灰色禁用；刷新后终态卡片仍不可点击；`npm run build` 通过 | 完成 |
| Phase 4 - 点击与协议闭环 | done | 已支持 `接受 P1 方案A` / `接受 P1 方案B` / `拒绝 P1 全部方案` / `重试 P1`；修订方案会在回复中重新渲染 inline card；clean DB 网络记录未发现 direct confirm/reject 主流程 | 完成 |
| Phase 5 - 浏览器级验收闭环 | done | `assistant_inline_proposal_20260515.md` 已记录 clean DB `INLINE-P0-001` 至 `INLINE-P0-008` 全部通过；`INLINE-P1-001` 至 `INLINE-P1-005` 浏览器通过 | 进入 Phase 6 |
| Phase 6 - 全功能真实实测 | done | 新 clean DB `browser_inline_final_20260515.db` 已完成最终完整浏览器验收；后端重点回归 `188 passed`；前端 `npm run build` 通过 | 完成 |

### Overall progress

当前进度：`completed; inline proposal P0/P1 and final full browser acceptance passed on clean DB`

### Latest change summary

1. 已将需求拆为后端、前端、协议、状态恢复、多方案生成和浏览器验收切片。
2. 已补充浏览器实测失败后的修复反馈闭环。
3. 已补充最终全功能真实浏览器实测门槛。
4. 已按最新交互要求修复 inline proposal 点击后的呈现：接受/拒绝后卡片不再消失，而是保留在原助手气泡中并灰色禁用。
5. 已完成 `INLINE-P0-001` 单方案接受与 `INLINE-P0-002` 拒绝全部的真实浏览器验收记录。
6. 已修复 `INLINE-P0-004` 模糊下午时间只出单方案的问题；浏览器复测 A/B/C 时间方案通过。
7. 已修复 `INLINE-P0-005` 任务安排只出单方案的问题；浏览器复测 `这周帮我安排复习英语` 生成 A/B/C 三方案，点击 B 后创建任务与两个 focus block。
8. 已在 fresh clean DB `browser_inline_clean_20260515.db` 重跑 `INLINE-P0-001` 至 `INLINE-P0-008`，全部通过；P0-008 网络记录未发现 direct confirm/reject proposal 端点请求。
9. 已修复 `INLINE-P1-001` 复合目标请求静默丢失第二目标的问题；浏览器复测 P1/P2 可分别拒绝/接受。
10. 已修复 `INLINE-P1-002` 修订 proposal 后不渲染新 inline card 的问题；浏览器复测单 pending 修订显示 20:00 新卡片，多 pending 含糊修订会澄清。
11. 已修复 `INLINE-P1-003` 单 pending 下 `算了，不选了` 被误判为取消日程请求的问题；浏览器复测会拒绝当前 proposal，多 pending 仍澄清。
12. 已完成 `INLINE-P1-004` 执行失败重试浏览器验收；主输入框发送 `重试 P1` 后通过助手协议执行 retry 并创建日程。
13. 已完成 `INLINE-P1-005` 移动端渲染验收；修复 390px 视口会话选择区溢出和长消息刷新后未滚到内联卡片区域的问题，浏览器复测单方案与三方案点击均通过。
14. 已在新 clean DB `browser_inline_final_20260515.db` 完成最终全功能真实浏览器实测，覆盖单方案接受、拒绝全部、多方案任务、修订、复合请求、刷新恢复和移动端渲染。
15. 已完成最终回归：后端重点测试 `188 passed`，前端 `npm run build` 通过。
16. 已完成 2026-05-16 新增交互验收：方案被接受或拒绝后，内联卡片保留为灰色不可点击；刷新后通过按 session 拉取 proposal 终态恢复 `executed/rejected` 状态，不会重新变成可点击 pending。

### Next action

任务完成：P0/P1 浏览器验收和最终全功能真实浏览器实测均已通过，当前无未关闭的阻塞失败项。

### Execution readiness

状态：`completed`

继续实现中，每完成一个切片都必须更新本进度台账，并在浏览器验收阶段把实测证据写入 `docs/development/browser_acceptance_runs/`。

---

## 风险与控制

### 风险 1：前端复杂度上升

控制：

1. render block 只定义有限类型。
2. 先支持 proposal_options，再扩展其他类型。
3. 保持独立调试入口，不让其干扰主体验。

### 风险 2：多方案生成失控

控制：

1. 明确只在冲突、模糊、任务拆分、多选择场景开多方案。
2. 明确单次日程不滥发多方案。

### 风险 3：点击协议绕过助手

控制：

1. 前端点击只发送固定文本。
2. 后端继续按文本协议解析。
3. 浏览器验收必须检查网络请求。

### 风险 4：验收只剩文档，没有实测

控制：

1. 任务书明确 browser-level 修复闭环。
2. 所有失败必须回写脚本和测试。
3. 最终必须有一次全功能实测。

---

## 推荐实施顺序

1. 先定义 render block 协议。
2. 再扩展 proposal builder 支持多方案。
3. 再改 AssistantPanel 做 inline 渲染。
4. 再改点击协议和单选锁定。
5. 然后用浏览器逐条验收。
6. 失败先修复再复测。
7. P0/P1 全通后再做全功能终验。
