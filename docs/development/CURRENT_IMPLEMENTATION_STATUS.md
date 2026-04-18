# 当前实现状态审计

**审计日期**: 2026-04-18  
**审计范围**: 当前工作区代码、`IMPLEMENTATION_PLAN_V6.md`、`IMPLEMENTATION_PLAN_V7.md`、`docs/README.md`

## 结论

当前项目**不是 V7 完成态**，也**不是停留在 V5 或更早**。

更准确的判断是：

- **主体实现已推进到 V6 施工阶段**
- **并且已经混入部分 V7 优化**
- **但 V6 仍未完全收口，V7 更未真正接管主链路**

因此，当前版本建议标记为：

> **“V6 在建，附带少量 V7 前置改造”**

## 判定依据

### 1. 已落地并进入主链路的能力

以下内容已明确进入当前运行链路或前端主界面：

- 助手 WebSocket 流式输出
  - 后端存在 `/ws/assistant`
  - 前端 `assistant.ts` 已优先使用流式发送
- 外部上下文部分优化
  - `AssistantService._needs_external_context()` 已用于跳过部分无关外部调用
  - `AssistantService._build_event_specific_context()` 已并行获取通勤/天气
- 地图与天气工具超时优化
  - 高德与和风天气客户端已调整到 `8s`
- 前端 Store 拆分已基本完成
  - 已有 `assistant.ts`、`events.ts`、`reminder.ts`、`suggestion.ts`、`profile.ts`、`context.ts`、`googleCalendar.ts`、`system.ts`
  - `workspace.ts` 已退化为兼容门面层
- 任务拆分接口已接入 API
  - `GET /api/tasks/{task_id}/split-suggestions`
- 语音输入/输出接口已接入后端路由
  - `/api/assistant/voice`
  - `/api/assistant/speak`
- 移动端/桌面端壳目录已存在
  - `frontend/capacitor.config.ts`
  - `frontend/src-tauri/`
  - `frontend/android/`
  - `frontend/ios/`

### 2. 已写入代码库、但尚未真正接入主链路的 V6 能力

以下能力明显属于 V6，但当前更像“已落代码和测试草案”，而不是“已贯通上线”：

- ChromaDB 向量存储
  - `app/core/vector_store.py`
  - `app/core/embedding.py`
  - `main.py` 启动时初始化目录与向量库
- 习惯学习相关服务
  - `habit_collector.py`
  - `habit_analyzer.py`
  - `habit_retriever.py`
  - `preference_learner.py`
- 多轮对话槽位补全
  - `dialog_state.py`
- 扫描线冲突检测
  - `conflict_detector.py`
- 智能任务拆分服务
  - `task_splitter.py`
- 新增模型与迁移草稿
  - `Habit`
  - `TaskSplit`
  - `events.energy_level`
  - `events.habit_id`
  - `tasks.max_splits`
  - `tasks.min_chunk_minutes`
  - `tasks.split_strategy`

但这些能力目前存在明显“未接通”特征：

- 主助手入口仍然是**超大单体 `AssistantService`**
- 当前 API 依赖注入仍直接返回 `app.services.assistant.AssistantService`
- 现有主链路没有把 V6 的 `DialogStateManager`、`ConflictDetector`、`HabitRetriever`、`PreferenceLearner`、`VectorStore` 系统性串起来
- 缺少习惯/偏好独立 API 路由，说明尚未形成完整外部能力面

### 3. V7 相关实现的实际状态

当前仓库里已经出现明显的 V7 方向代码：

- `app/workflow/graph.py`
- `app/workflow/nodes.py`
- `app/workflow/react_subgraph.py`
- `app/workflow/react_tools.py`
- `app/workflow/visualization.py`

但这些内容**尚不能判定为 V7 已完成**，主要原因是：

- 生产主流程没有通过 LangGraph 工作流执行
- `AssistantService.send_message()` 仍是主入口
- `get_assistant_service()` 也没有切到 workflow 驱动实现
- ReAct 子图只是存在于代码库，并未成为线上默认路径

## 当前主要不一致与风险

以下问题说明项目仍处于“施工中”，不能视为稳定的 V6 完成版，更不能视为 V7 完成版：

### 1. 工作流未真正接管

- `workflow/` 目录完整，但当前助手主入口仍未切换到工作流
- `WorkflowNodes.parse_intent()` 里引用路径与真实实现不一致：
  - 使用 `from app.services.enhanced_assistant import EnhancedIntentParser`
  - 实际 `EnhancedIntentParser` 定义在 `app/services/intent_parser.py`

### 2. V6 数据模型与迁移不一致

- ORM 中 `Habit.id` 为 `String(36)`，迁移中却是 `Integer`
- `TaskSplit.id` ORM 为 `String(36)`，迁移中却是 `Integer`
- 说明数据库迁移尚未完成收口

### 3. 智能任务拆分仍有实现缺口

- 路由已经暴露 `split-suggestions`
- 但 `task_splitter.py` 中对 `UserProfile` 的查询字段写法与现有模型不一致
- 说明 API 面已出现，内部实现还未完全校准

### 4. ReAct 工具层仍偏草稿

- `react_tools.py` 中部分工具依赖构造方式与现有 Repository 模式不完全匹配
- 更像“概念验证代码”而非稳定生产接入

### 5. 测试与当前环境不一致

- `docs/testing/V6_NEW_FEATURES_REPORT.md` 声称大量测试通过
- 但当前本机直接执行 `pytest -q` 因缺少依赖而在收集阶段失败
- 这说明“测试报告”和“当前工作区可复现实况”并不完全一致

## 当前版本判断

### 不应判定为 V7 的原因

- LangGraph++ 没有接管生产主流程
- ReAct 子图没有形成默认执行路径
- 工具注册机制与监控可视化仍停留在代码层/测试层

### 不应判定为 V5 或更早的原因

- 已经存在 V6 级别的数据模型扩展、向量存储、习惯学习、对话槽位、冲突检测、任务拆分、前端 Store 重构
- 已经落入代码库并部分进入界面和 API

## 推荐对外表述

如果要在论文、答辩或项目汇报中描述当前状态，建议使用：

> 当前项目已从 V5 主体能力推进到 **V6 施工阶段**，并完成了部分 **V7 性能/交互优化前置改造**；但 LangGraph++ 工作流重构尚未正式接管主链路，因此当前不应认定为完整 V7 版本。

## 建议的下一步

1. 先决定是否以 **“稳定收口 V6”** 为主，而不是继续同时推进 V6/V7 两条线。
2. 若以 V6 为主，应优先完成：
   - 主助手入口接入 V6 增强能力
   - 迁移与 ORM 对齐
   - 习惯/偏好 API 与主流程打通
3. 若继续推进 V7，应先完成：
   - `AssistantService` 到 workflow 的切换
   - ReAct/工具注册链路打通
   - 删除或收敛当前重复实现
