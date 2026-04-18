# 项目实现状态审查报告

**审查日期**: 2026-04-18  
**审查范围**: `IMPLEMENTATION_PLAN_V6.md`、`IMPLEMENTATION_PLAN_V7.md` 与当前代码实现  
**结论摘要**: 当前项目应认定为 **V7 当前基线已落地**

---

## 执行摘要

本次审查的核心结论如下：

1. **V6 内容已完成并入当前基线**  
   V6 计划中的数据模型扩展、向量库、习惯学习、槽位补全、扫描线冲突检测、任务拆分、前端 Store 拆分等内容已进入代码库并纳入当前主基线。

2. **V7 核心目标已落地**  
   workflow 已接管助手主入口，复杂场景保留 ReAct 分支，条件化上下文与超时优化已生效。

3. **当前剩余问题属于收尾，不再属于版本未切换**  
   主要集中在迁移一致性、可选依赖与代码瘦身，而不是“workflow 尚未接管”。

---

## 一、版本判断

### 最终判断

| 候选版本 | 结论 | 原因 |
|---|---|---|
| V7 | ✅ 是 | workflow 已接管主入口，V7 主基线成立 |
| V6 | ⚠️ 已被吸纳 | 不再是当前版本归属 |
| 更早（V5 或更早） | ❌ 否 | 已存在明显超出 V5 的能力与结构 |

### 推荐版本表述

> **当前项目状态：V7 当前基线已落地。**

---

## 二、V6 对照审查

### 2.1 已明确进入代码库的 V6 项

| V6 能力 | 当前状态 | 说明 |
|---|---|---|
| ChromaDB 向量存储 | ✅ 已写入代码 | `core/vector_store.py`、`core/embedding.py` |
| 习惯学习相关服务 | ✅ 已写入代码 | `habit_collector.py`、`habit_analyzer.py`、`habit_retriever.py`、`preference_learner.py` |
| 多轮对话槽位补全 | ✅ 已写入代码 | `dialog_state.py` |
| 扫描线冲突检测 | ✅ 已写入代码 | `conflict_detector.py` |
| 智能任务拆分 | ✅ 已写入代码 | `task_splitter.py` |
| 数据模型扩展 | ✅ 已写入代码 | `Habit`、`TaskSplit`、`energy_level`、`habit_id`、`max_splits` 等 |
| 前端 Store 拆分 | ✅ 已接入 | 多个 focused store 已存在，`workspace.ts` 已改为兼容 facade |

### 2.2 V6 已被当前基线吸纳

| V6 能力 | 当前状态 | 说明 |
|---|---|---|
| 前端 Store 拆分 | ✅ 已接入 | 前端运行时已使用新 Store 架构 |
| 任务拆分建议 API | ✅ 已接入 | `/tasks/{task_id}/split-suggestions` 已可用并通过测试 |
| 向量层与习惯层 | ✅ 已接入基线 | 已有实现与测试，缺依赖场景有降级兜底 |

### 2.3 V6 剩余待收口的项

| V6 能力 | 当前状态 | 阻塞点 |
|---|---|---|
| 习惯学习闭环 | ⚠️ 待增强 | 当前已有实现，但 API 面和展示面仍可继续扩展 |
| 多轮槽位补全 | ⚠️ 待深化 | 当前已有基础设施，仍可继续强化对话体验 |
| 数据迁移统一 | ❌ 未完成 | ORM 与 Alembic 仍需完全对齐 |

---

## 三、V7 对照审查

### 3.1 已落地的 V7 核心项

| V7 能力 | 当前状态 | 说明 |
|---|---|---|
| 条件化外部上下文判断 | ✅ 已接入 | `AssistantService._needs_external_context()` |
| 事件级天气/通勤并行获取 | ✅ 已接入 | `_build_event_specific_context()` |
| 地图/天气超时优化 | ✅ 已接入 | Amap / QWeather 已降到 `8s` |
| WebSocket 助手流式输出 | ✅ 已接入 | `/ws/assistant` + 前端流式消费 |
| workflow 主入口接管 | ✅ 已接入 | `AssistantService.send_message()` / `send_message_stream()` 已切到 workflow |
| ReAct 子图 | ✅ 已接入 | 作为复杂场景分支保留 |
| workflow debug 接口 | ✅ 已接入 | `/api/debug/workflow/summary` 与 `/api/debug/workflow/diagram` |
| 前端状态架构继续解耦 | ✅ 已接入 | Store facade 已形成 |

### 3.2 当前仍待继续收口的 V7 项

| V7 项 | 当前状态 | 原因 |
|---|---|---|
| `AssistantService` 体量瘦身 | ⚠️ 未完成 | workflow 已接管，但 helper 仍大量留在 service 内 |
| 向量依赖正式运行说明 | ⚠️ 未完成 | 当前已做可选依赖降级，但仍需生产安装说明 |
| 数据迁移统一 | ⚠️ 持续收口中 | 主迁移已校准并验证，仍建议继续审视历史升级路径 |

### 3.3 当前验证事实

- backend 全量测试已通过
- workflow 测试、assistant 测试、API 测试已通过
- frontend 构建已通过
- Alembic 已成功迁移到 `head`

---

## 四、验证补充

### 本轮可确认结果

- `frontend` 执行 `npm run build` 成功
- `backend/.venv312` 下执行全量 `pytest`
  - **280 passed**
- 临时 SQLite 数据库上执行 `alembic upgrade head` 成功

### 这说明什么

1. 当前基线已经可构建、可测试。
2. 版本切换已经完成，后续重点是收口与清债。
3. 当前可以把项目版本口径升级为 V7。

---

## 五、综合结论

### 结论一

当前项目**已经完成 V7 主基线切换**。

### 结论二

当前项目**应认定为 V7**，因为最关键的 workflow 主入口接管已经完成。

### 结论三

当前项目最准确的状态是：

> **V7 当前基线已落地，后续工作主要是收口数据库迁移、可选依赖与架构清债。**

---

## 六、建议动作

### 优先建议

1. 先以 **V7 收口** 为主目标。
2. 继续修正模型/迁移/API/依赖说明之间的不一致。
3. 继续拆薄 `AssistantService`。

### 暂不建议

1. 在未收口迁移与体量问题前继续横向扩展新分支。
2. 把当前状态描述成“所有理想化扩展都已完成”。

---

**审查结论**: 当前版本应标记为 **V7 当前基线已落地**。
