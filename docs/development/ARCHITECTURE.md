# MA-IPAAS 毕业设计系统重构与调优方案

## 1. 重构目标

当前版本的 MA-IPAAS 设计已经具备清晰的产品想法，但在系统架构层面仍存在三个问题：

1. `Agent` 的职责划分偏“概念化”，缺少严格的控制边界。
2. 业务能力、工具能力、状态管理混杂，后期实现容易耦合。
3. 论文层面的“系统设计”与工程层面的“可落地架构”之间还没有完全打通。

本次重构的目标不是推翻原方案，而是将其从“功能构想型设计”升级为“工程化、可论证、可分阶段实现”的毕业设计系统方案。

## 2. 重构后的总体思路

建议将系统由“多个并列 Agent 直接协作”调整为“五层架构 + 监督式编排”。

### 2.1 推荐架构

1. **交互层**
   - Web 前端、移动端封装、语音输入扩展
   - 负责用户输入、日程展示、聊天窗口、结果确认

2. **会话与接入层**
   - HTTP API、WebSocket、鉴权、限流、会话上下文管理
   - 负责把用户请求转成统一的系统输入事件

3. **协调编排层**
   - `Supervisor / Coordinator Agent`
   - 负责意图识别、任务拆解、路由决策、结果汇总、失败回退

4. **领域执行层**
   - `Calendar Agent`
   - `Scheduling Agent`
   - `Navigation & Context Agent`
   - `Task & Notes Agent`

5. **工具与状态层**
   - Calendar Tool、Map Tool、Weather Tool、Notification Tool
   - 用户偏好、会话状态、数据库、缓存、审计日志

### 2.2 为什么改成这个结构

这样调整后，系统的设计会比原来的 `Master / Scheduler / Navigator / Clerk` 更严谨，因为：

1. `Supervisor` 只负责“判断和分配”，不直接承载所有业务逻辑。
2. 领域 Agent 只面向稳定职责，避免一个 Agent 既做推理又直连各种基础设施。
3. 工具层被单独抽离，后续替换高德地图、Google Calendar、通知服务时不会影响 Agent 设计。
4. 论文里可以明确写出分层设计、模块边界、调用链路与可扩展性依据。

## 3. 推荐的 Agent 体系

## 3.1 Supervisor Agent

### 定位

系统唯一的编排入口，不直接负责具体业务执行。

### 职责

1. 识别用户意图：
   - 查询日程
   - 新增日程
   - 修改/取消日程
   - 查询待办
   - 写入纪要
   - 闲聊/问答
2. 抽取结构化槽位：
   - 时间
   - 地点
   - 参与者
   - 优先级
   - 是否固定
3. 根据任务类型路由到合适的领域 Agent。
4. 在多 Agent 返回结果后做冲突汇总与最终答复。
5. 当信息缺失时触发追问或进入人工确认。

### 不应承担的职责

1. 不直接操作数据库。
2. 不直接调用地图、天气、通知等外部 API。
3. 不直接做复杂排程算法。

## 3.2 Calendar Agent

### 定位

负责“日历事件”的 CRUD 语义执行。

### 典型任务

1. 查询指定日期范围事件
2. 创建事件
3. 修改事件
4. 删除事件
5. 获取空闲时间段

### 依赖工具

1. `Calendar Tool`
2. `Event Repository`

## 3.3 Scheduling Agent

### 定位

负责“排程规则与冲突求解”，是核心业务智能模块。

### 典型任务

1. 冲突检测
2. 缓冲时间计算
3. 柔性任务重排
4. 空档填充
5. 固定任务与非固定任务区分处理

### 建议规则

1. 将事件分为 `fixed` 与 `flexible`
2. 将任务分为 `hard deadline` 与 `soft deadline`
3. 将通勤与准备时间视为显式约束，而不是隐式备注

## 3.4 Navigation & Context Agent

### 定位

负责与“出行相关的上下文”打交道，而不是只做地图查询。

### 典型任务

1. 路径规划
2. 通勤时间估计
3. 出发时间建议
4. 实时路况重估
5. 天气、节假日、地理上下文补充

### 设计理由

原设计中的 `Navigator Agent` 只有地图能力，范围偏窄。扩展成 `Navigation & Context Agent` 后，更适合后续纳入天气、城市交通、时间上下文等因素，也更符合实际调度逻辑。

## 3.5 Task & Notes Agent

### 定位

负责待办池、碎片任务、会议纪要和轻量知识记录。

### 典型任务

1. Backlog 管理
2. 会议纪要记录
3. 纪要转待办
4. 待办推荐插入空档
5. 历史任务检索

## 4. 推荐的数据与工具边界

当前设计里最需要加强的是“Tool 层”定义。建议把所有外部能力都包装成稳定工具接口，而不是直接写进 Agent 提示词。

## 4.1 工具层建议

1. **Calendar Tool**
   - `list_events(range)`
   - `create_event(payload)`
   - `update_event(event_id, payload)`
   - `delete_event(event_id)`
   - `query_free_busy(range)`

2. **Scheduling Tool / Policy Engine**
   - `detect_conflicts(candidate_event)`
   - `calculate_buffer(event_type, location, user_profile)`
   - `reschedule_flexible_events(plan)`
   - `find_best_slot(task, constraints)`

3. **Map Tool**
   - `estimate_travel_time(origin, destination, mode, departure_time)`
   - `suggest_departure_time(event)`

4. **Weather Tool**
   - `get_weather(location, time_range)`

5. **Notification Tool**
   - `push_schedule_change(user_id, message)`
   - `send_departure_reminder(event_id)`

## 4.2 为什么工具层必须独立

参考 `calendar-mcp` 这类项目可以看到，只要工具定义稳定，Agent 框架可以替换，具体模型也可以替换，系统本身不会整体推翻。对毕业设计来说，这能显著提高方案的工程合理性。

## 5. 推荐的系统调用链路

## 5.1 新增日程场景

1. 用户输入自然语言请求
2. 接入层建立会话上下文
3. Supervisor Agent 识别意图并抽取槽位
4. 如果缺失关键信息，则先追问
5. Supervisor 调用 `Navigation & Context Agent` 获取通勤和上下文信息
6. Supervisor 调用 `Scheduling Agent` 检查冲突、计算缓冲、生成候选时段
7. Supervisor 调用 `Calendar Agent` 落库或写入外部日历
8. Notification Tool 推送确认或变更消息
9. 前端通过 WebSocket 实时显示过程与结果

## 5.2 延误重排场景

1. 外部事件触发或用户主动上报延误
2. Supervisor 判定是否需要进入重排流程
3. Navigation & Context Agent 重新估算到达时间
4. Scheduling Agent 重新评估后续 `flexible` 任务
5. Calendar Agent 批量调整受影响事件
6. Notification Tool 发出变更提醒

## 6. 推荐的数据模型修正

你原先的数据表方向是对的，但建议从“论文描述字段”升级为“可支撑约束求解”的模型。

## 6.1 `tb_schedule_events` 建议新增字段

1. `event_type`
2. `flexibility_type`
3. `buffer_post`
4. `source`
5. `participant_count`
6. `requires_travel`
7. `parent_task_id`
8. `reschedule_policy`
9. `confidence_score`

### 解释

1. `flexibility_type` 用于区分固定事件和可调整事件。
2. `buffer_post` 用于建模事件后的收尾或通勤缓冲。
3. `source` 用于区分用户手动创建、Agent 创建、外部日历同步。
4. `reschedule_policy` 用于约束系统是否允许自动改动该事件。

## 6.2 `tb_backlog` 建议新增字段

1. `task_type`
2. `energy_level`
3. `splittable`
4. `preferred_time_range`
5. `must_finish_before`
6. `status`

### 解释

这些字段有助于后期实现“碎片填充”和“柔性任务排程”，否则 Backlog 很难真正接入调度逻辑。

## 6.3 建议新增审计与状态表

1. `tb_agent_run_logs`
2. `tb_schedule_change_logs`
3. `tb_user_context_memory`

### 作用

1. 支撑答辩中的“可观测性”和“可追溯性”
2. 便于分析 Agent 决策链
3. 避免会话状态完全依赖临时内存

## 7. 推荐技术方案调整

## 7.1 Agent 框架建议

不建议把论文表述过度绑定在 `LangChain` 单一名词上，而建议表述为：

- 采用“监督式多 Agent 编排模式”
- 使用支持状态图/工作流路由的 Agent 编排框架实现
- 当前实现优先考虑 `LangGraph` 风格的 Supervisor 模式

### 原因

1. `LangGraph` 更适合描述状态流转、消息历史控制和多 Agent 路由。
2. 你现在的课题重点不是“提示词试玩”，而是“系统化调度与协同”。
3. 这样论文表述更稳，也更容易吸收开源社区实践。

## 7.2 后端建议

继续保留：

1. `Python 3.11+`
2. `Django + DRF`
3. `Channels`
4. `Celery + Redis`
5. `MySQL`

但建议在实现层明确区分：

1. `Web API`
2. `Realtime Gateway`
3. `Agent Orchestrator`
4. `Tool Service`
5. `Persistence Layer`

## 7.3 前端建议

前端目标不应只写“做一个聊天页面 + 日历页面”，而应描述为“双视图协同界面”：

1. **Calendar Workspace**
   - 日历
   - 时间轴
   - 冲突提示
   - 调整建议

2. **Assistant Workspace**
   - 对话
   - 推理过程摘要
   - 待确认项
   - 自动重排结果

这样能让你的系统和普通日历 App 有明显区分。

## 8. 建议的最小可行版本

为了保证毕业设计能落地，建议采用“三阶段 MVP”而不是一次性全做完。

## 阶段一：单用户基础闭环

目标：

1. 用户通过自然语言创建、查询、修改日程
2. 能检测时间冲突
3. 能给出通勤时间建议

必须完成：

1. Calendar Agent
2. Scheduling Agent
3. Map Tool
4. WebSocket 对话
5. 日历可视化

## 阶段二：调优与弹性排程

目标：

1. 柔性任务插入空档
2. 延误触发重排
3. 用户偏好参与排程决策

必须完成：

1. Backlog 与任务池
2. 柔性任务规则
3. 出发提醒与变更通知

## 阶段三：展示增强

目标：

1. 多端适配
2. 系统运行链路可视化
3. 论文图表和演示素材完备

必须完成：

1. 响应式前端
2. 系统架构图
3. 时序图
4. 关键日志展示

## 9. 建议的论文表达方式

如果你要让毕业设计显得更严谨，论文中的系统设计部分建议用下面这种术语：

1. “监督式多智能体协同架构”
2. “面向个人事务管理的分层式 Agent 系统”
3. “基于工具调用与状态约束的智能排程机制”
4. “支持实时上下文感知的弹性日程重构流程”

不建议继续大量使用“像真人助理一样思考”这类偏宣传性的表述，改成：

1. 结构化意图识别
2. 约束驱动排程
3. 上下文感知重规划
4. 多 Agent 协作与任务编排

## 10. 最终推荐方案

综合参考开源社区实践后，MA-IPAAS 更适合采用如下正式架构：

- 一个 `Supervisor Agent` 作为统一编排入口
- 多个面向业务域的 `Specialized Agents`
- 一层可替换的 `Tool Layer`
- 一层显式的 `State / Memory / Audit Layer`
- 一套 HTTP + WebSocket + 异步任务协同的运行机制

这套方案相较于原始设计的优势在于：

1. 结构边界更清晰
2. 更贴近现有开源 Agent 系统的主流工程实践
3. 更容易分阶段实现
4. 更利于论文中论证系统可扩展性、可维护性和可落地性
