# 个人事务助手系统实现计划 V6 - 智能化升级与 RAG 习惯学习

> 本文档为系统智能化升级的详细落地方案，聚焦四大核心能力强化 + 向量数据库习惯学习引擎。

---

## 目录

- [一、现状总结与技术债回顾](#一现状总结与技术债回顾)
- [二、V6 升级目标与架构总览](#二v6-升级目标与架构总览)
- [三、向量数据库与习惯学习引擎](#三向量数据库与习惯学习引擎)
- [四、P0 — 核心能力强化](#四p0--核心能力强化)
  - [P0-1: LLM 输出 Pydantic 验证层](#p0-1-llm-输出-pydantic-验证层)
  - [P0-2: 多轮对话槽位补全机制](#p0-2-多轮对话槽位补全机制)
  - [P0-3: 冲突检测算法优化（扫描线 + 冲突图）](#p0-3-冲突检测算法优化扫描线--冲突图)
- [五、P1 — 体验深化](#五p1--体验深化)
  - [P1-1: 用户偏好学习与推荐优化](#p1-1-用户偏好学习与推荐优化)
  - [P1-2: 模糊语义搜索与智能联想](#p1-2-模糊语义搜索与智能联想)
  - [P1-3: 情境感知提醒引擎](#p1-3-情境感知提醒引擎)
  - [P1-4: 提醒聚合与降噪](#p1-4-提醒聚合与降噪)
- [六、P2 — 架构改善](#六p2--架构改善)
  - [P2-1: LangGraph 工作流引擎引入](#p2-1-langgraph-工作流引擎引入)
  - [P2-2: 前端 Store 拆分](#p2-2-前端-store-拆分)
  - [P2-3: 智能任务拆分增强](#p2-3-智能任务拆分增强)
- [七、数据库变更清单](#七数据库变更清单)
- [八、依赖与配置变更](#八依赖与配置变更)
- [九、单元测试规范](#九单元测试规范)
- [十、整体测试验证清单](#十整体测试验证清单)

---

## 一、现状总结与技术债回顾

### 1.1 当前系统能力矩阵

| 核心能力 | 当前状态 | 成熟度 |
|----------|----------|--------|
| 自然语言理解 | 纯 Prompt 工程，无结构化验证 | ⚠️ 基础可用但不稳定 |
| 冲突检测 | O(n²) 暴力遍历 | ⚠️ 小规模可用，缺乏优化 |
| 空档建议 | 规则引擎驱动 | ✅ 基本完成 |
| 主动提醒 | 5 种定时扫描，频率固定 | ✅ 基本完成 |
| 习惯学习 | ❌ 不存在 | ❌ 未实现 |
| 模糊语义匹配 | ❌ 不存在 | ❌ 未实现 |

### 1.2 已知技术债

| 编号 | 技术债 | 影响 | 修复优先级 |
|------|--------|------|------------|
| TD-1 | `assistant.py` 单文件 ~3000 行，无工作流编排 | 难以维护和测试 | P2 |
| TD-2 | `workspace.ts` 单文件 ~1100 行，职责过重 | 前端状态管理混乱 | P2 |
| TD-3 | LLM 输出无 Pydantic 验证 | 格式错误时无 fallback | P0 |
| TD-4 | 冲突检测 O(n²) 复杂度 | 事件量大时性能差 | P0 |
| TD-5 | 提醒无去重和冷却机制 | 可能出现提醒风暴 | P0（已在 V5 部分修复） |
| TD-6 | 无用户偏好学习 | 推荐不够个性化 | P1 |

---

## 二、V6 升级目标与架构总览

### 2.1 V6 核心目标

1. **引入向量数据库**：实现用户习惯的语义化存储与检索
2. **模糊语义匹配**：让 AI 能理解"晚上回家做饭"= "18:00 做饭"的习惯关联
3. **强化四大核心能力**：意图理解、建议质量、冲突处理、主动提醒
4. **架构瘦身**：拆分巨型文件，引入工作流引擎

### 2.2 升级后架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (Vue 3 + Pinia)                     │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐  │
│  │EventsStore│ │Assistant  │ │Reminder   │ │Suggestion    │  │
│  │          │ │Store      │ │Store      │ │Store         │  │
│  └──────────┘ └───────────┘ └───────────┘ └──────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                            │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           LangGraph 工作流引擎                        │    │
│  │  parse_intent → collect_context → schedule_decision  │    │
│  │              → tool_execute → response_render        │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────┐  ┌────────▼────────┐  ┌──────────────────┐    │
│  │ Services │  │ Habit Learning  │  │ Schedule Engine   │    │
│  │ 层       │  │ Engine (NEW)    │  │ (优化版)          │    │
│  └────┬─────┘  └────────┬────────┘  └────────┬─────────┘    │
│       │                 │                     │              │
│  ┌────▼─────┐  ┌────────▼────────┐  ┌────────▼─────────┐    │
│  │ Repos    │  │  ChromaDB       │  │ Conflict Detector │    │
│  │          │  │  (向量存储)      │  │ (扫描线算法)      │    │
│  └──────────┘  └────────┬────────┘  └──────────────────┘    │
│                         │                                    │
│                  ┌──────▼───────┐                            │
│                  │ Gemini Embed │                            │
│                  │  (API 调用)   │                            │
│                  └──────────────┘                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Tools 工具层                              │   │
│  │  Gemini │ Amap │ QWeather │ Google Calendar │ Notify  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────┐              ┌────────────────────────┐   │
│  │ SQLite (主)  │              │ Redis (缓存 + 队列)     │   │
│  └──────────────┘              └────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 技术栈变更

| 组件 | 变更前 | 变更后 | 原因 |
|------|--------|--------|------|
| 向量存储 | ❌ 无 | **ChromaDB** | 轻量嵌入式，零运维，适合个人应用 |
| 嵌入模型 | ❌ 无 | **Gemini Embedding API** | 复用已有 API，零本地资源占用 |
| 工作流引擎 | 无（集中在 assistant.py） | **LangGraph（Phase 3 引入）** | 状态机编排，可测试可调试 |
| 冲突检测 | O(n²) 暴力遍历 | **扫描线算法** | O(n log n) 性能优化 |
| 前端状态 | 单 Store (~1100 行) | **渐进拆分** | 先拆 assistant/reminders，保留 workspace 协调层 |

---

## 三、向量数据库与习惯学习引擎

### 3.1 技术选型

经过调研对比，最终选定：

| 组件 | 选型 | 理由 |
|------|------|------|
| 向量数据库 | **ChromaDB** | 纯 Python，`pip install` 即用，自带持久化，API 极简 |
| 嵌入模型 | **Gemini Embedding API** | 复用已有 API Key，零本地资源占用，中文理解能力强 |
| 存储位置 | `backend/chroma_db/` | 与 SQLite 数据文件同级，Docker volume 持久化 |

**为什么不选其他方案：**

| 方案 | 排除原因 |
|------|----------|
| Milvus/Weaviate | 需要独立服务部署，过于沉重 |
| FAISS | 不支持持久化，需手动管理序列化 |
| SQLite-VSS | Windows 平台兼容性问题 |
| Qdrant 嵌入式 | 功能过剩，依赖较多 |
| BAAI/bge-small-zh | 需要本地下载模型，占用内存，已有 Gemini API 可复用 |

### 3.2 习惯学习引擎架构

```
┌─────────────────────────────────────────────────────┐
│              HabitLearningEngine                     │
│                                                      │
│  ┌─────────────┐    ┌──────────────┐                 │
│  │ HabitCollector│──►│ HabitAnalyzer│                 │
│  │ (习惯采集)   │    │ (习惯分析)    │                 │
│  └──────┬──────┘    └──────┬───────┘                 │
│         │                  │                          │
│  ┌──────▼─────────────────▼───────┐                  │
│  │         VectorStore            │                  │
│  │   (ChromaDB + Gemini Embed)   │                  │
│  └──────────────┬────────────────┘                  │
│                 │                                   │
│  ┌──────────────▼────────────────┐                  │
│  │      HabitRetriever           │                  │
│  │   (语义检索 + 联想推荐)        │                  │
│  └───────────────────────────────┘                  │
└─────────────────────────────────────────────────────┘
```

### 3.3 核心数据结构

#### 3.3.1 ChromaDB Collection 设计

系统维护 **3 个 Collection**：

```python
# Collection 1: 用户习惯模式
user_habits = {
    "documents": ["工作日晚上6点下班后去超市买菜"],
    "metadatas": [{
        "type": "routine",           # 习惯类型
        "time_pattern": "18:00",     # 时间模式
        "day_pattern": "weekday",    # 日期模式
        "location": "超市",           # 地点
        "activity": "买菜",           # 活动
        "frequency": "daily",        # 频率
        "confidence": 0.85,          # 置信度
        "occurrences": 12,           # 出现次数
        "last_occurrence": "2026-04-03"
    }],
    "ids": ["habit_001"]
}

# Collection 2: 历史事件经验
event_experiences = {
    "documents": ["上次会议延期了，因为交通堵塞迟到"],
    "metadatas": [{
        "type": "experience",
        "event_type": "meeting",
        "outcome": "delayed",
        "reason": "traffic",
        "lesson": "提前15分钟出发"
    }],
    "ids": ["exp_001"]
}

# Collection 3: 偏好与约束
user_preferences = {
    "documents": ["我不喜欢早上安排重要会议"],
    "metadatas": [{
        "type": "preference",
        "category": "scheduling",
        "polarity": "negative",      # positive/negative
        "context": "morning_meeting",
        "strength": 0.9
    }],
    "ids": ["pref_001"]
}
```

#### 3.3.1.5 Gemini Embedding API 集成

ChromaDB 支持自定义嵌入函数，我们使用 Gemini Embedding API 替代默认的 Sentence Transformers：

```python
# backend/app/core/embedding.py
import os
import google.generativeai as genai
from chromadb import Documents, EmbeddingFunction, Embeddings

class GeminiEmbeddingFunction(EmbeddingFunction):
    """Gemini Embedding API 适配器，供 ChromaDB 使用"""
    
    def __init__(self, model_name: str = "models/text-embedding-004"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        genai.configure(api_key=api_key)
        self.model_name = model_name
    
    def __call__(self, input: Documents) -> Embeddings:
        """批量生成嵌入向量"""
        # Gemini API 支持批量请求，每次最多 100 条
        embeddings = []
        for text in input:
            result = genai.embed_content(
                model=self.model_name,
                content=text,
                task_type="retrieval_document"
            )
            embeddings.append(result["embedding"])
        return embeddings

# 使用方式
# backend/app/core/vector_store.py
import chromadb
from .embedding import GeminiEmbeddingFunction

class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embed_fn = GeminiEmbeddingFunction()
        
        self.collections = {
            "habits": self._get_or_create("user_habits"),
            "experiences": self._get_or_create("event_experiences"),
            "preferences": self._get_or_create("user_preferences"),
        }
    
    def _get_or_create(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )
    
    def add(self, collection: str, documents: list, metadatas: list, ids: list):
        self.collections[collection].add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    
    def query(self, collection: str, query_texts: list, n_results: int = 5, where: dict = None):
        return self.collections[collection].query(
            query_texts=query_texts,
            n_results=n_results,
            where=where
        )
```

**Gemini Embedding API 注意事项：**

| 关注点 | 说明 |
|--------|------|
| API 限额 | Gemini 免费版每分钟 60 次请求，个人使用足够 |
| 延迟 | 单次嵌入约 100-300ms，批量操作时需控制并发 |
| 离线场景 | 断网时无法生成嵌入，需做好降级处理 |
| 成本控制 | 免费额度充足，超出后按 token 计费，需监控用量 |

**降级策略：**

```python
class VectorStore:
    async def safe_add(self, collection: str, documents: list, metadatas: list, ids: list):
        """安全添加数据，网络异常时降级到 SQLite 存储"""
        try:
            self.add(collection, documents, metadatas, ids)
        except Exception as e:
            logger.warning(f"Vector store write failed, falling back to SQLite: {e}")
            # 仅写入 SQLite 元数据，待网络恢复时补写向量
            await self.habit_repo.bulk_save_pending(metadatas)
```

#### 3.3.3 SQLite 习惯表（元数据持久化）

```python
class Habit(Base):
    """习惯元数据表，与 ChromaDB 向量互补"""
    __tablename__ = "habits"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    habit_type = Column(String(50))  # routine/preference/pattern
    description = Column(Text)       # 自然语言描述
    time_pattern = Column(String(50))  # 时间模式（如 "18:00", "morning"）
    day_pattern = Column(String(50))   # 日期模式（如 "weekday", "monday"）
    location = Column(String(200))
    activity = Column(String(200))
    frequency = Column(String(20))     # daily/weekly/monthly
    confidence = Column(Float)         # 置信度 0-1
    occurrences = Column(Integer)      # 出现次数
    last_occurrence = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 3.4 习惯采集流程（三路并行）

系统采用 **被动采集 + 主动采集 + 对话采集** 三路并行的策略，全方位捕捉用户习惯。

```python
# ============================================
# 路径 1：被动采集 — 事件创建/修改时自动触发
# ============================================
async def on_event_created(event: Event):
    """从事件中抽取习惯模式"""
    habit = HabitAnalyzer.extract_pattern(event)
    if habit.confidence > 0.6:  # 阈值过滤
        await habit_collector.record(habit)

# 在 events.py 的 create/update 方法中调用
async def create_event(self, payload: dict) -> Event:
    event = await self.repo.create(payload)
    # 被动采集：记录习惯
    asyncio.create_task(on_event_created(event))  # 不阻塞主流程
    return event


# ============================================
# 路径 2：主动采集 — 后台定期批量分析
# ============================================
@celery.task(bind=True, max_retries=3)
def analyze_weekly_patterns(self):
    """每周分析一次事件数据，发现新的习惯模式"""
    events = get_events_last_days(30)
    patterns = HabitAnalyzer.discover_patterns(events)
    for pattern in patterns:
        habit_store.upsert(pattern)
    return f"Discovered {len(patterns)} new patterns"

# celery beat 配置（每周日凌晨 3 点执行）
CELERY_BEAT_SCHEDULE = {
    "weekly-pattern-analysis": {
        "task": "app.jobs.habit_learning.analyze_weekly_patterns",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    # 每天凌晨 2 点做一次轻量级增量分析
    "daily-habit-increment": {
        "task": "app.jobs.habit_learning.analyze_daily_habits",
        "schedule": crontab(hour=2, minute=0),
    },
}


# ============================================
# 路径 3：对话采集 — 从用户对话中提取偏好
# ============================================
async def on_user_statement(message: str, context: dict):
    """从用户陈述中提取偏好和习惯"""
    # LLM 提取结构化偏好
    preferences = await llm.extract_preferences(message)
    for pref in preferences:
        await preference_store.add(pref)
    
    # 从对话中识别习惯性表达
    habits = await llm.extract_habits(message)
    for habit in habits:
        await habit_collector.record(habit)

# 在 assistant.py 的消息处理流程中调用
async def process_message(self, message: str, ...):
    # ... 正常处理流程 ...
    
    # 对话采集：后台异步执行，不阻塞回复
    asyncio.create_task(on_user_statement(message, context))
```

### 三种采集方式的协同关系

```
┌─────────────────────────────────────────────────┐
│              习惯采集三路并行                      │
│                                                   │
│  ┌──────────────┐                                │
│  │ 被动采集      │ ← 事件 CRUD 时触发              │
│  │ (即时)        │ ← 低延迟，数据精确               │
│  └──────┬───────┘                                │
│         │                                         │
│  ┌──────▼───────┐                                │
│  │ 主动采集      │ ← Celery 定期批量分析           │
│  │ (周期性)      │ ← 发现隐藏模式，补全被动遗漏     │
│  └──────┬───────┘                                │
│         │                                         │
│  ┌──────▼───────┐                                │
│  │ 对话采集      │ ← 从自然语言中提取显式偏好       │
│  │ (交互式)      │ ← 捕获主观意愿和软约束           │
│  └──────┬───────┘                                │
│         │                                         │
│  ┌──────▼───────┐                                │
│  │  去重 & 合并  │ ← 同一条习惯不重复记录           │
│  │  (dedup)     │ ← 多来源置信度融合              │
│  └──────┬───────┘                                │
│         │                                         │
│  ┌──────▼───────┐                                │
│  │  ChromaDB    │                                 │
│  │  + SQLite    │                                 │
│  └──────────────┘                                │
└─────────────────────────────────────────────────┘
```

### 去重与置信度融合

```python
class HabitDeduplicator:
    """习惯去重与置信度融合"""
    
    async def merge(self, new_habit: Habit, existing: list[Habit]) -> Habit:
        """
        当新习惯与已有习惯相似时，不创建新记录，而是：
        1. 增加 occurrences 计数
        2. 更新置信度（加权平均）
        3. 更新 last_occurrence 时间
        """
        similar = await self.find_similar(new_habit, existing)
        
        if similar:
            # 融合：更新已有习惯
            similar.occurrences += 1
            similar.confidence = self._weighted_average(
                similar.confidence, new_habit.confidence,
                similar.occurrences, 1
            )
            similar.last_occurrence = datetime.utcnow()
            return similar
        else:
            # 全新习惯，创建记录
            return await self.habit_repo.create(new_habit)
    
    def _weighted_average(self, conf_a, conf_b, count_a, count_b) -> float:
        """加权平均置信度"""
        total = count_a + count_b
        return (conf_a * count_a + conf_b * count_b) / total
```

### 3.5 习惯检索与联想

```python
class HabitRetriever:
    """习惯检索器，供 Assistant 工作流调用"""
    
    async def suggest_time(self, activity: str, context: str) -> Optional[str]:
        """根据活动联想常用时间
        例：用户说"做饭"→ 检索到"晚上6点做饭"的习惯
        """
        results = self.vector_store.search(
            query=f"{activity} {context}",
            collection="user_habits",
            n_results=3,
            filters={"type": "routine"}
        )
        if results and results[0].metadata.confidence > 0.7:
            return results[0].metadata.time_pattern
        return None
    
    async def check_preference(self, proposal: dict) -> bool:
        """检查建议是否违反用户偏好"""
        conflicts = self.vector_store.search(
            query=json.dumps(proposal),
            collection="user_preferences",
            n_results=5,
            filters={"polarity": "negative"}
        )
        return len(conflicts) == 0
    
    async def get_similar_experience(self, situation: str) -> list:
        """检索类似场景的历史经验"""
        return self.vector_store.search(
            query=situation,
            collection="event_experiences",
            n_results=3
        )
```

### 3.6 典型使用场景演示

#### 场景 1：模糊语义匹配

```
用户输入："晚上回家做饭"

系统内部流程：
1. IntentParser 识别意图：create_event
2. 槽位抽取：activity="做饭", context="晚上回家"
3. 调用 HabitRetriever.suggest_time("做饭", "晚上")
4. ChromaDB 检索到：
   - "工作日晚上6点下班后去超市买菜" (相似度 0.82)
   - "周末晚上7点做晚饭" (相似度 0.78)
5. 推断时间：18:00-19:00
6. 生成建议："根据你的习惯，通常晚上 6 点左右做饭，安排 18:00-19:00 可以吗？"
```

#### 场景 2：偏好感知的日程建议

```
系统需要安排"重要会议"

1. 检查用户偏好：
   - 检索 "重要会议 早上" → 找到负面偏好 "我不喜欢早上安排重要会议"
2. 避开早上时段
3. 推荐下午 14:00-15:00
4. 附加说明："注意到你不喜欢在早上开重要会议，建议安排在下午"
```

### 3.7 项目结构变更

```
backend/
├── app/
│   ├── core/
│   │   ├── vector_store.py          # NEW: ChromaDB 封装
│   │   └── embedding.py             # NEW: Gemini Embedding API 客户端
│   ├── services/
│   │   ├── habit_collector.py       # NEW: 习惯采集服务
│   │   ├── habit_analyzer.py        # NEW: 习惯分析服务
│   │   └── habit_retriever.py       # NEW: 习惯检索服务
│   ├── repositories/
│   │   └── habits.py                # NEW: 习惯数据访问
│   └── models.py                    # MODIFIED: 新增 Habit 模型
├── chroma_db/                       # NEW: 向量数据目录（.gitignore）
├── embedding_models/                # NEW: 模型缓存目录（.gitignore）
└── requirements.txt                 # MODIFIED: 新增依赖
```

---

## 四、P0 — 核心能力强化

### P0-1: LLM 输出 Pydantic 验证层

**目标**：对 LLM 输出的 JSON 进行严格校验，格式错误时自动 fallback

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/schemas/assistant_actions.py` | 新建 | 定义所有动作的 Pydantic Schema |
| `backend/app/services/assistant.py` | 修改 | 集成验证逻辑 |
| `backend/app/tools/gemini.py` | 修改 | 增加输出格式约束 prompt |
| `backend/tests/test_assistant_validation.py` | 新建 | 验证层单元测试 |

#### 实现方案

```python
# backend/app/schemas/assistant_actions.py
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional
from datetime import datetime

class CreateEventAction(BaseModel):
    type: Literal["create_event"]
    payload: dict = Field(..., description="事件创建参数")
    
    @validator("payload")
    def validate_payload(cls, v):
        required = ["title", "start_time"]
        for field in required:
            if field not in v:
                raise ValueError(f"Missing required field: {field}")
        return v

class CreateTaskAction(BaseModel):
    type: Literal["create_task"]
    payload: dict

class QueryEventsAction(BaseModel):
    type: Literal["query_events"]
    payload: dict = Field(default_factory=lambda: {"range": "today"})

class ClarifyAction(BaseModel):
    """当信息不足时，要求澄清"""
    type: Literal["clarify"]
    missing_fields: list[str]
    question: str

# 统一响应 Schema
class AssistantResponse(BaseModel):
    reply: str = Field(..., description="给用户的自然语言回复")
    actions: list[CreateEventAction | CreateTaskAction | QueryEventsAction | ClarifyAction] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
```

#### 验证流程

```python
# backend/app/services/assistant.py 中集成
async def _validate_llm_output(raw_output: str) -> AssistantResponse:
    """验证并解析 LLM 输出"""
    try:
        # 1. 提取 JSON
        json_str = extract_json_from_markdown(raw_output)
        
        # 2. Pydantic 验证
        response = AssistantResponse.model_validate_json(json_str)
        
        # 3. 进一步校验每个 action 的 payload
        for action in response.actions:
            await validate_action_payload(action)
            
        return response
        
    except (ValidationError, json.JSONDecodeError) as e:
        logger.warning(f"LLM output validation failed: {e}")
        
        # 4. Fallback：尝试修复
        if retry_count < MAX_RETRIES:
            return await _retry_with_feedback(raw_output, str(e))
        
        # 5. 最终 fallback：返回纯文本回复
        return AssistantResponse(
            reply=raw_output,
            actions=[],
            confidence=0.3
        )
```

### P0-2: 多轮对话槽位补全机制

**目标**：当用户提供的信息不完整时，系统能主动追问而非盲目执行

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/dialog_state.py` | 新建 | 对话状态跟踪器 |
| `backend/app/services/assistant.py` | 修改 | 集成槽位补全流程 |
| `backend/app/schemas/assistant_actions.py` | 修改 | 新增 ClarifyAction |

#### 实现方案

```python
# backend/app/services/dialog_state.py
from dataclasses import dataclass, field

@dataclass
class SlotDefinition:
    name: str
    required: bool
    prompt: str  # 追问话术
    extractor: callable  # 从上下文中提取的函数

@dataclass
class DialogState:
    """对话状态跟踪"""
    intent: Optional[str] = None
    slots: dict = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    turn_count: int = 0
    max_turns: int = 3  # 最多追问 3 次
    
    def is_complete(self) -> bool:
        return len(self.missing_slots) == 0
    
    def next_missing_slot(self) -> Optional[SlotDefinition]:
        if self.missing_slots:
            return self.missing_slots.pop(0)
        return None

# 槽位定义模板
CREATE_EVENT_SLOTS = [
    SlotDefinition("title", required=True, prompt="请问事件的标题是什么？"),
    SlotDefinition("start_time", required=True, prompt="请问什么时候开始？"),
    SlotDefinition("end_time", required=False, prompt="请问什么时候结束？"),
    SlotDefinition("location", required=False, prompt="在哪里进行？"),
]

class SlotFiller:
    """槽位填充器"""
    
    async def process_turn(self, user_input: str, state: DialogState) -> DialogState:
        """处理一轮对话，尝试填充缺失的槽位"""
        # 1. 用 LLM 提取槽位值
        extracted = await self.llm.extract_slots(user_input, state.missing_slots)
        
        # 2. 更新状态
        state.slots.update(extracted)
        state.missing_slots = [
            s for s in state.missing_slots 
            if s.name not in extracted
        ]
        state.turn_count += 1
        
        return state
    
    def get_clarification_question(self, state: DialogState) -> str:
        """生成追问问题"""
        next_slot = state.next_missing_slot()
        if next_slot:
            return next_slot.prompt
        return None
```

#### 集成到工作流

```python
# 简化版集成逻辑
async def handle_user_message(message: str, session_id: str):
    # 1. 恢复或创建对话状态
    state = await dialog_store.get_or_create(session_id)
    
    # 2. 如果是新对话，先识别意图
    if state.intent is None:
        state.intent = await intent_classifier.classify(message)
        state.missing_slots = get_required_slots(state.intent)
    
    # 3. 尝试填充槽位
    state = await slot_filler.process_turn(message, state)
    
    # 4. 判断是否完成
    if state.is_complete():
        # 所有槽位已填充，执行操作
        result = await execute_action(state)
        await dialog_store.clear(session_id)
        return result
    elif state.turn_count >= state.max_turns:
        # 超过最大追问次数，使用默认值或取消
        return await handle_incomplete_dialog(state)
    else:
        # 继续追问
        question = slot_filler.get_clarification_question(state)
        await dialog_store.save(state)
        return {"reply": question, "waiting_for_input": True}
```

### P0-3: 冲突检测算法优化（扫描线 + 冲突图）

**目标**：将冲突检测从 O(n²) 优化到 O(n log n)，并支持冲突链检测

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/conflict_detector.py` | 新建 | 新冲突检测器 |
| `backend/app/services/events.py` | 修改 | 替换原有 detect_conflicts |
| `backend/tests/test_conflict_detection.py` | 修改 | 更新测试用例 |

#### 实现方案

```python
# backend/app/services/conflict_detector.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class TimePoint:
    time: datetime
    event_id: str
    is_start: bool

@dataclass
class ConflictPair:
    event_a_id: str
    event_b_id: str
    overlap_minutes: int
    conflict_type: str  # "direct_overlap", "travel_insufficient", "buffer_violation"

class ConflictDetector:
    """基于扫描线算法的冲突检测器"""
    
    def detect_conflicts(self, events: list[Event]) -> list[ConflictPair]:
        """
        扫描线算法：O(n log n)
        
        1. 将所有事件的开始/结束时间点排序
        2. 扫描时间点，维护当前活跃事件集合
        3. 当新事件开始时，检查与活跃事件的冲突
        """
        # 1. 构建时间点列表
        time_points = []
        for event in events:
            effective_start = event.start_time - event.buffer_before
            effective_end = event.end_time + event.buffer_after
            
            time_points.append(TimePoint(effective_start, event.id, True))
            time_points.append(TimePoint(effective_end, event.id, False))
        
        # 2. 按时间排序
        time_points.sort(key=lambda x: (x.time, not x.is_start))
        
        # 3. 扫描
        conflicts = []
        active_events = set()
        
        for point in time_points:
            if point.is_start:
                # 新事件开始，检查与所有活跃事件的冲突
                for active_id in active_events:
                    conflict = self._check_conflict(
                        self._find_event(point.event_id, events),
                        self._find_event(active_id, events)
                    )
                    if conflict:
                        conflicts.append(conflict)
                active_events.add(point.event_id)
            else:
                # 事件结束，从活跃集合移除
                active_events.discard(point.event_id)
        
        return conflicts
    
    def _check_conflict(self, event_a: Event, event_b: Event) -> Optional[ConflictPair]:
        """检查两个事件之间的冲突"""
        a_effective_end = event_a.end_time + event_a.buffer_after
        b_effective_start = event_b.start_time - event_b.buffer_before
        
        # 直接时间重叠
        if a_effective_end > b_effective_start:
            overlap = (a_effective_end - b_effective_start).total_seconds() / 60
            return ConflictPair(
                event_a_id=event_a.id,
                event_b_id=event_b.id,
                overlap_minutes=int(overlap),
                conflict_type="direct_overlap"
            )
        
        # 地点不同，检查通勤时间
        if event_a.location_coords and event_b.location_coords:
            travel_time = self._estimate_travel_time(event_a, event_b)
            if a_effective_end + timedelta(minutes=travel_time) > b_effective_start:
                deficit = (a_effective_end + timedelta(minutes=travel_time) - b_effective_start).total_seconds() / 60
                return ConflictPair(
                    event_a_id=event_a.id,
                    event_b_id=event_b.id,
                    overlap_minutes=int(deficit),
                    conflict_type="travel_insufficient"
                )
        
        return None
    
    def build_conflict_graph(self, events: list[Event]) -> dict[str, list[str]]:
        """
        构建冲突图，支持传递性冲突链检测
        
        返回：{event_id: [与之冲突的所有 event_id]}
        """
        conflicts = self.detect_conflicts(events)
        graph = defaultdict(set)
        
        for conflict in conflicts:
            graph[conflict.event_a_id].add(conflict.event_b_id)
            graph[conflict.event_b_id].add(conflict.event_a_id)
        
        return dict(graph)
    
    def find_conflict_chains(self, events: list[Event]) -> list[list[str]]:
        """
        找出所有冲突链（连通分量）
        例：A↔B↔C 形成一个冲突链
        """
        graph = self.build_conflict_graph(events)
        visited = set()
        chains = []
        
        for event_id in graph:
            if event_id not in visited:
                chain = self._dfs_chain(event_id, graph, visited)
                if len(chain) > 1:
                    chains.append(chain)
        
        return chains
```

---

## 五、P1 — 体验深化

### P1-1: 用户偏好学习与推荐优化

**目标**：基于历史行为数据优化日程推荐质量

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/preference_learner.py` | 新建 | 偏好学习服务 |
| `backend/app/services/suggestions.py` | 修改 | 集成偏好感知 |
| `backend/app/jobs/preference_learning.py` | 新建 | 后台学习任务 |

#### 实现方案

```python
# backend/app/services/preference_learner.py
class PreferenceLearner:
    """从用户行为中学习偏好"""
    
    async def learn_from_history(self, user_id: str, days: int = 30) -> dict:
        """分析过去 N 天的事件数据，提取偏好模式"""
        events = await self.event_repo.get_by_date_range(user_id, days)
        
        preferences = {
            "preferred_time_slots": self._analyze_time_patterns(events),
            "preferred_locations": self._analyze_location_patterns(events),
            "task_acceptance_rate": self._analyze_task_acceptance(events),
            "conflict_resolution_style": self._analyze_conflict_resolutions(events),
            "energy_curve": self._estimate_energy_curve(events),
        }
        
        # 存储到向量数据库
        for pref_type, pref_data in preferences.items():
            await self.vector_store.add_preference(pref_type, pref_data)
        
        return preferences
    
    def _analyze_time_patterns(self, events: list[Event]) -> dict:
        """分析时间偏好：用户通常在什么时间安排什么类型的活动"""
        time_slots = defaultdict(lambda: defaultdict(int))
        
        for event in events:
            hour = event.start_time.hour
            day_type = "weekday" if event.start_time.weekday() < 5 else "weekend"
            time_slots[day_type][hour] += 1
        
        # 找出高峰时段
        preferred = {}
        for day_type, hours in time_slots.items():
            sorted_hours = sorted(hours.items(), key=lambda x: x[1], reverse=True)
            preferred[day_type] = [h for h, _ in sorted_hours[:3]]
        
        return preferred
    
    def _estimate_energy_curve(self, events: list[Event]) -> list[float]:
        """估算用户的精力曲线（基于历史事件完成情况）"""
        # 简化版：假设用户在自己常安排的时段效率更高
        hourly_completion = defaultdict(lambda: {"completed": 0, "total": 0})
        
        for event in events:
            hour = event.start_time.hour
            hourly_completion[hour]["total"] += 1
            if event.status == "completed":
                hourly_completion[hour]["completed"] += 1
        
        curve = []
        for hour in range(24):
            data = hourly_completion[hour]
            if data["total"] > 0:
                curve.append(data["completed"] / data["total"])
            else:
                curve.append(0.5)  # 默认值
        
        return curve
```

#### 集成到建议引擎

```python
# backend/app/services/suggestions.py 中修改
class SuggestionsService:
    async def find_idle_slots(self, user_id: str, date: date) -> list[IdleSlot]:
        slots = await self._calculate_idle_slots(user_id, date)
        
        # 融入偏好学习
        preferences = await self.preference_learner.get_preferences(user_id)
        
        for slot in slots:
            hour = slot.start.hour
            energy = preferences["energy_curve"][hour]
            slot.quality_score = energy * 0.5 + slot.duration_minutes / 60 * 0.5
        
        # 按质量分数排序
        slots.sort(key=lambda s: s.quality_score, reverse=True)
        return slots
```

### P1-2: 模糊语义搜索与智能联想

**目标**：利用向量数据库实现自然语言到具体时间/地点的智能联想

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/intent_parser.py` | 新建 | 增强版意图解析器 |
| `backend/app/services/assistant.py` | 修改 | 集成习惯检索 |
| `backend/app/tools/gemini.py` | 修改 | 增加习惯检索 tool |

#### 实现方案

```python
# backend/app/services/intent_parser.py
class EnhancedIntentParser:
    """增强版意图解析器，结合向量检索"""
    
    def __init__(self, habit_retriever: HabitRetriever):
        self.habit_retriever = habit_retriever
        self.llm = GeminiClient()
    
    async def parse_with_context(self, message: str, user_id: str) -> ParsedIntent:
        """
        结合用户习惯解析意图
        
        例："晚上回家做饭" → 
        1. 基础解析：activity="做饭", time_context="晚上"
        2. 习惯检索：检索到用户常在 18:00 做饭
        3. 增强结果：activity="做饭", start_time="18:00", confidence=0.85
        """
        # 1. 基础 LLM 解析
        base_result = await self.llm.parse_intent(message)
        
        # 2. 如果有活动关键词，检索相关习惯
        if base_result.activity:
            habit_match = await self.habit_retriever.suggest_time(
                activity=base_result.activity,
                context=base_result.time_context or ""
            )
            
            if habit_match:
                # 用习惯数据增强解析结果
                base_result.start_time = habit_match.time_pattern
                base_result.confidence = max(base_result.confidence, habit_match.confidence * 0.9)
                base_result.habit_reference = habit_match.id
        
        # 3. 检查是否违反用户偏好
        if base_result.proposed_schedule:
            violates = await self.habit_retriever.check_preference(base_result.proposed_schedule)
            base_result.preference_warnings = violates
        
        return base_result
```

### P1-3: 情境感知提醒引擎

**目标**：提醒不再是简单的定时触发，而是结合天气、交通、用户状态的智能通知

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/contextual_reminder.py` | 新建 | 情境感知提醒 |
| `backend/app/jobs/reminders.py` | 修改 | 集成情境感知 |

#### 实现方案

```python
# backend/app/services/contextual_reminder.py
class ContextualReminderService:
    """情境感知提醒服务"""
    
    async def generate_smart_reminder(self, event: Event) -> ReminderPayload:
        """生成情境感知的提醒"""
        # 1. 获取当前天气
        weather = await self.weather_tool.get_weather(event.location_coords)
        
        # 2. 获取实时交通
        traffic = await self.maps_tool.get_traffic_status(
            origin=user.home_location_coords,
            destination=event.location_coords,
            departure_time=event.departure_time
        )
        
        # 3. 构建提醒文案
        message = self._build_contextual_message(event, weather, traffic)
        
        return ReminderPayload(
            event_id=event.id,
            message=message,
            priority=self._calculate_priority(event, weather, traffic),
            channels=["websocket", "desktop_notification"]
        )
    
    def _build_contextual_message(
        self, event: Event, weather: dict, traffic: dict
    ) -> str:
        """构建情境感知的提醒文案"""
        parts = []
        
        # 基本信息
        parts.append(f"提醒：{event.title} 将在 {event.start_time.strftime('%H:%M')} 开始")
        
        # 天气增强
        if weather and weather.get("condition") in ["rain", "snow"]:
            parts.append(f"外面正在{weather['condition_description']}，记得带伞")
        
        # 交通增强
        if traffic and traffic.get("congestion_level") == "heavy":
            extra_minutes = traffic.get("extra_delay_minutes", 0)
            parts.append(f"当前路况拥堵，比平时多 {extra_minutes} 分钟，建议提前出发")
        
        # 习惯增强
        habit = await self.habit_retriever.get_similar_experience(event.title)
        if habit:
            parts.append(f"上次类似情况：{habit.metadata.get('lesson', '')}")
        
        return "\n".join(parts)
```

### P1-4: 提醒聚合与降噪

**目标**：避免提醒轰炸，智能聚合相近时间的提醒

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/reminder_aggregator.py` | 新建 | 提醒聚合服务 |
| `backend/app/jobs/reminders.py` | 修改 | 集成聚合逻辑 |

#### 实现方案

```python
# backend/app/services/reminder_aggregator.py
class ReminderAggregator:
    """提醒聚合与降噪服务"""
    
    def __init__(self):
        self.cooldown_minutes = 15  # 冷却时间
        self.aggregation_window_minutes = 30  # 聚合时间窗口
        self.last_sent = {}  # event_id -> last_sent_time
        self.do_not_disturb = {
            "start": "23:00",
            "end": "07:00"
        }
    
    async def should_send_reminder(self, reminder: Reminder) -> bool:
        """判断是否应该发送提醒"""
        # 1. 免打扰时段检查
        if self._is_in_dnd_period():
            return False
        
        # 2. 冷却检查
        if self._is_in_cooldown(reminder.target_id):
            return False
        
        # 3. 重复提醒检查
        if await self._already_sent_similar(reminder):
            return False
        
        return True
    
    async def aggregate_reminders(self, reminders: list[Reminder]) -> list[Reminder]:
        """聚合相近时间的提醒"""
        if len(reminders) <= 1:
            return reminders
        
        # 按时间排序
        reminders.sort(key=lambda r: r.remind_at)
        
        aggregated = []
        current_batch = [reminders[0]]
        
        for reminder in reminders[1:]:
            time_diff = (reminder.remind_at - current_batch[0].remind_at).total_seconds() / 60
            
            if time_diff <= self.aggregation_window_minutes:
                current_batch.append(reminder)
            else:
                # 批次结束，生成聚合提醒
                aggregated.append(self._merge_batch(current_batch))
                current_batch = [reminder]
        
        # 处理最后一批
        if current_batch:
            aggregated.append(self._merge_batch(current_batch))
        
        return aggregated
    
    def _merge_batch(self, batch: list[Reminder]) -> Reminder:
        """将一批提醒合并为一条"""
        messages = [r.message for r in batch]
        merged_message = f"你有 {len(batch)} 条即将发生的提醒：\n" + "\n".join(
            f"- {msg}" for msg in messages
        )
        
        return Reminder(
            id=batch[0].id,
            user_id=batch[0].user_id,
            target_type="batch",
            target_ids=[r.target_id for r in batch],
            message=merged_message,
            remind_at=batch[0].remind_at,
            delivery_channel=batch[0].delivery_channel
        )
```

---

## 六、P2 — 架构改善

### P2-1: LangGraph 工作流引擎引入

**目标**：将集中在 `assistant.py` 的 ~3000 行逻辑拆分为可测试的工作流节点

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/workflow/graph.py` | 新建 | LangGraph 状态图定义 |
| `backend/app/workflow/nodes.py` | 新建 | 各节点实现 |
| `backend/app/workflow/state.py` | 新建 | 工作流状态定义 |
| `backend/app/workflow/prompts.py` | 新建 | Prompt 模板管理 |
| `backend/app/services/assistant.py` | 修改 | 简化为工作流调用入口 |

#### 工作流状态图

```
┌──────────────┐
│   START      │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│ parse_intent │────►│collect_context│
│   (意图识别)  │     │  (上下文收集)  │
└──────────────┘     └──────┬───────┘
                            │
                            ▼
                   ┌────────────────┐
                   │schedule_decision│
                   │  (调度决策)     │
                   └───────┬────────┘
                      ╱    │    ╲
                     ╱     │     ╲
              needs_tool   │   needs_clarify
                   ╲       │       ╱
                    ▼      ▼      ▼
            ┌────────┐ ┌─────┐ ┌──────────┐
            │execute │ │wait │ │clarify   │
            │tools   │ │     │ │and retry │
            └───┬────┘ └─────┘ └──────────┘
                │
                ▼
        ┌──────────────┐
        │render_response│
        │  (回复渲染)    │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │     END      │
        └──────────────┘
```

#### 实现方案

```python
# backend/app/workflow/state.py
from typing import TypedDict, Optional

class WorkflowState(TypedDict):
    """工作流状态"""
    user_message: str
    user_id: str
    session_id: str
    
    # 意图解析结果
    intent: Optional[str]
    extracted_slots: dict
    
    # 上下文
    existing_events: list
    existing_tasks: list
    habits: list
    weather: Optional[dict]
    traffic: Optional[dict]
    
    # 决策结果
    actions: list
    conflicts: list
    suggestions: list
    
    # 回复
    reply: str
    confidence: float
    
    # 控制流
    needs_clarification: bool
    clarification_question: Optional[str]
    retry_count: int
```

```python
# backend/app/workflow/nodes.py
class WorkflowNodes:
    """工作流节点实现"""
    
    @staticmethod
    async def parse_intent(state: WorkflowState) -> WorkflowState:
        """意图识别节点"""
        parser = EnhancedIntentParser(habit_retriever)
        result = await parser.parse_with_context(
            state["user_message"], 
            state["user_id"]
        )
        
        state["intent"] = result.intent
        state["extracted_slots"] = result.slots
        state["confidence"] = result.confidence
        
        return state
    
    @staticmethod
    async def collect_context(state: WorkflowState) -> WorkflowState:
        """上下文收集节点"""
        user_id = state["user_id"]
        slots = state["extracted_slots"]
        
        # 并行收集
        events, tasks, habits = await asyncio.gather(
            event_service.get_relevant_events(user_id, slots.get("time_range")),
            task_service.get_active_tasks(user_id),
            habit_retriever.get_relevant_habits(slots.get("activity")),
        )
        
        state["existing_events"] = events
        state["existing_tasks"] = tasks
        state["habits"] = habits
        
        # 按需获取天气和交通
        if slots.get("location"):
            weather, traffic = await asyncio.gather(
                weather_tool.get_weather(slots["location"]),
                maps_tool.estimate_travel_time(user_id, slots["location"]),
            )
            state["weather"] = weather
            state["traffic"] = traffic
        
        return state
    
    @staticmethod
    async def schedule_decision(state: WorkflowState) -> WorkflowState:
        """调度决策节点"""
        intent = state["intent"]
        
        if intent == "create_event":
            conflicts = conflict_detector.detect_conflicts(
                state["existing_events"] + [state["extracted_slots"]["new_event"]]
            )
            state["conflicts"] = conflicts
            
            if conflicts:
                alternatives = conflict_detector.suggest_alternatives(
                    state["extracted_slots"]["new_event"],
                    state["existing_events"]
                )
                state["suggestions"] = alternatives
        
        return state
    
    @staticmethod
    async def execute_tools(state: WorkflowState) -> WorkflowState:
        """工具执行节点"""
        actions = state.get("actions", [])
        
        for action in actions:
            if action["type"] == "create_event":
                await event_service.create_event(action["payload"])
            elif action["type"] == "create_task":
                await task_service.create_task(action["payload"])
        
        return state
    
    @staticmethod
    async def render_response(state: WorkflowState) -> WorkflowState:
        """回复渲染节点"""
        formatter = ResponseFormatter()
        state["reply"] = await formatter.format_response(
            intent=state["intent"],
            actions=state.get("actions", []),
            conflicts=state.get("conflicts", []),
            suggestions=state.get("suggestions", []),
            habits=state.get("habits", []),
        )
        
        return state
```

```python
# backend/app/workflow/graph.py
from langgraph.graph import StateGraph, END

def build_assistant_workflow() -> StateGraph:
    """构建 Assistant 工作流图"""
    workflow = StateGraph(WorkflowState)
    
    # 添加节点
    workflow.add_node("parse_intent", WorkflowNodes.parse_intent)
    workflow.add_node("collect_context", WorkflowNodes.collect_context)
    workflow.add_node("schedule_decision", WorkflowNodes.schedule_decision)
    workflow.add_node("execute_tools", WorkflowNodes.execute_tools)
    workflow.add_node("render_response", WorkflowNodes.render_response)
    workflow.add_node("clarify", WorkflowNodes.handle_clarification)
    
    # 设置入口
    workflow.set_entry_point("parse_intent")
    
    # 添加边
    workflow.add_edge("parse_intent", "collect_context")
    workflow.add_edge("collect_context", "schedule_decision")
    
    # 条件边：根据决策结果选择不同路径
    workflow.add_conditional_edges(
        "schedule_decision",
        route_after_decision,
        {
            "needs_tool": "execute_tools",
            "needs_clarify": "clarify",
            "direct_response": "render_response",
        }
    )
    
    workflow.add_edge("execute_tools", "render_response")
    workflow.add_edge("clarify", END)
    workflow.add_edge("render_response", END)
    
    return workflow.compile()

def route_after_decision(state: WorkflowState) -> str:
    """决策路由函数"""
    if state.get("needs_clarification"):
        return "needs_clarify"
    if state.get("actions"):
        return "needs_tool"
    return "direct_response"
```

### P2-2: 前端 Store 拆分（渐进式）

**目标**：分阶段将 `workspace.ts` (~1100 行) 拆分为独立 Store，降低风险

**渐进策略**：

| 阶段 | 拆分目标 | 说明 | 风险 |
|------|----------|------|------|
| **第一阶段** | 拆出 `assistant.ts` | 助手对话逻辑最独立，拆分风险最低 | 低 |
| **第二阶段** | 拆出 `reminders.ts` | 提醒与建议模块关联紧密，一起拆出 | 低 |
| **第三阶段** | 拆出 `events.ts` | 事件模块与日历组件耦合，需谨慎 | 中 |
| **第四阶段** | 拆出 `suggestions.ts` | 建议模块相对独立 | 低 |
| **最终** | `workspace.ts` 退化为协调层 | 仅负责跨 Store 通信和数据聚合 | 低 |

#### 第一阶段：拆出 Assistant Store

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/stores/assistant.ts` | 新建 | 助手对话状态（第一阶段） |
| `frontend/src/stores/reminders.ts` | 新建 | 提醒与建议状态（第二阶段） |
| `frontend/src/stores/workspace.ts` | 修改 | 保留事件管理，委托 assistant/reminders 到子 Store |

#### 拆分方案

```typescript
// frontend/src/stores/events.ts
export const useEventsStore = defineStore('events', () => {
  const events = ref<Event[]>([])
  const loading = ref(false)
  const cache = ref<Map<string, Event[]>>(new Map())
  
  const fetchEvents = async (start: string, end: string) => {
    const cacheKey = `${start}-${end}`
    if (cache.value.has(cacheKey)) {
      events.value = cache.value.get(cacheKey)!
      return
    }
    
    loading.value = true
    try {
      const response = await api.get('/api/events', { params: { start, end } })
      events.value = response.data
      cache.value.set(cacheKey, response.data)
    } finally {
      loading.value = false
    }
  }
  
  const createEvent = async (payload: CreateEventPayload) => {
    const response = await api.post('/api/events', payload)
    events.value.push(response.data)
    invalidateCache()
  }
  
  // ... 其他事件操作方法
  
  return { events, loading, fetchEvents, createEvent, updateEvent, deleteEvent }
})
```

```typescript
// frontend/src/stores/assistant.ts
export const useAssistantStore = defineStore('assistant', () => {
  const messages = ref<AssistantMessage[]>([])
  const sessionId = ref<string | null>(null)
  const isStreaming = ref(false)
  const input = ref('')
  
  const sendMessage = async (content: string) => {
    const userMessage: AssistantMessage = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    }
    messages.value.push(userMessage)
    
    isStreaming.value = true
    try {
      const response = await api.post('/api/assistant/message', {
        session_id: sessionId.value,
        message: content
      })
      
      const assistantMessage: AssistantMessage = {
        role: 'assistant',
        content: response.data.reply,
        actions: response.data.actions,
        timestamp: new Date().toISOString()
      }
      messages.value.push(assistantMessage)
      sessionId.value = response.data.session_id
    } finally {
      isStreaming.value = false
    }
  }
  
  const newSession = () => {
    sessionId.value = null
    messages.value = []
  }
  
  return { messages, sessionId, isStreaming, input, sendMessage, newSession }
})
```

### P2-3: 智能任务拆分增强

**目标**：从简单的布尔值 `can_split` 升级为智能拆分建议

#### 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/task_splitter.py` | 新建 | 智能任务拆分服务 |
| `backend/app/models.py` | 修改 | Task 模型增加拆分相关字段 |
| `backend/app/services/suggestions.py` | 修改 | 集成智能拆分 |

#### 实现方案

```python
# backend/app/services/task_splitter.py
class SmartTaskSplitter:
    """智能任务拆分服务"""
    
    async def suggest_splits(self, task: Task, available_slots: list[IdleSlot]) -> list[TaskSplitPlan]:
        """
        为任务智能建议拆分方案
        
        考虑因素：
        1. 任务预估时长 vs 可用空档时长
        2. 用户历史拆分偏好
        3. 任务内容的自然语义理解
        4. 截止时间压力
        """
        # 1. 用 LLM 分析任务内容，判断适合的拆分方式
        split_strategy = await self.llm.analyze_task_splitting(task.content)
        
        # 2. 匹配可用空档
        plan = self._match_slots(task, split_strategy, available_slots)
        
        # 3. 检查是否符合用户偏好
        preferences = await self.preference_learner.get_preferences(task.user_id)
        plan = self._adjust_for_preferences(plan, preferences)
        
        return plan
    
    def _match_slots(
        self, task: Task, strategy: SplitStrategy, available_slots: list[IdleSlot]
    ) -> TaskSplitPlan:
        """将任务拆分并匹配到可用空档"""
        splits = []
        remaining_minutes = task.estimated_duration_minutes
        
        for slot in sorted(available_slots, key=lambda s: s.start):
            if remaining_minutes <= 0:
                break
            
            chunk_minutes = min(slot.duration_minutes, remaining_minutes)
            splits.append(TaskSplit(
                task_id=task.id,
                scheduled_time=slot.start,
                duration_minutes=chunk_minutes,
                description=strategy.subtask_descriptions[len(splits)] if len(strategy.subtask_descriptions) > len(splits) else task.content
            ))
            remaining_minutes -= chunk_minutes
        
        return TaskSplitPlan(
            original_task=task,
            splits=splits,
            completion_percentage=1.0 if remaining_minutes <= 0 else (task.estimated_duration_minutes - remaining_minutes) / task.estimated_duration_minutes
        )
```

---

## 七、数据库变更清单

### 7.1 新增表

```python
# Habit 表 - 用户习惯
class Habit(Base):
    __tablename__ = "habits"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    habit_type = Column(String(50), nullable=False)  # routine/preference/pattern
    description = Column(Text, nullable=False)
    time_pattern = Column(String(50))
    day_pattern = Column(String(50))
    location = Column(String(200))
    activity = Column(String(200))
    frequency = Column(String(20))  # daily/weekly/monthly
    confidence = Column(Float, default=0.5)
    occurrences = Column(Integer, default=1)
    last_occurrence = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# TaskSplit 表 - 任务拆分记录
class TaskSplit(Base):
    __tablename__ = "task_splits"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    split_order = Column(Integer, nullable=False)
    scheduled_time = Column(DateTime)
    duration_minutes = Column(Integer)
    description = Column(Text)
    status = Column(String(20), default="pending")  # pending/completed/skipped
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 7.2 修改表

```python
# Event 表新增字段
class Event(Base):
    # ... 现有字段
    
    # V6 新增
    energy_level = Column(String(20))  # high/medium/low，基于习惯推断
    habit_id = Column(String(36), ForeignKey("habits.id"))  # 关联到的习惯

# Task 表修改
class Task(Base):
    # ... 现有字段
    
    # V6 修改：can_split 改为更丰富的拆分配置
    can_split = Column(Boolean, default=False)  # 保留向后兼容
    max_splits = Column(Integer, default=1)  # 最大拆分次数
    min_chunk_minutes = Column(Integer, default=15)  # 最小拆分单元（分钟）
    split_strategy = Column(String(50))  # equal/priority_based/time_based
```

### 7.3 Alembic 迁移

```bash
# 生成迁移脚本
cd backend
alembic revision --autogenerate -m "add habits and task_splits tables, enhance task splitting"
```

---

## 八、依赖与配置变更

### 8.1 后端依赖新增

```txt
# requirements.txt 新增
chromadb>=0.4.0
langgraph>=0.0.20
# 注意：不再需要 sentence-transformers、torch、transformers
# 因为使用 Gemini Embedding API 替代了本地 BGE 模型
```

### 8.2 Docker Compose 变更

```yaml
# docker-compose.yml 新增 volume 挂载
services:
  backend:
    volumes:
      - ./backend:/app
      - ./chroma_db:/app/chroma_db          # NEW: 向量数据持久化
      # 注意：不再需要 embedding_models 挂载
      # 因为使用 Gemini Embedding API 替代了本地模型
```

### 8.3 .gitignore 新增

```gitignore
# Vector store
chroma_db/
```

### 8.4 环境变量新增

```env
# .env 新增
# ChromaDB 配置
CHROMA_PERSIST_PATH=./chroma_db

# Gemini Embedding 配置（复用已有 GEMINI_API_KEY）
GEMINI_EMBEDDING_MODEL=models/text-embedding-004

# 习惯学习配置
HABIT_CONFIDENCE_THRESHOLD=0.6
HABIT_MIN_OCCURRENCES=3
PREFERENCE_LEARNING_ENABLED=true
```

---

## 九、单元测试规范

### 9.1 新增测试文件

| 测试文件 | 覆盖范围 |
|----------|----------|
| `backend/tests/test_vector_store.py` | ChromaDB 封装、增删改查 |
| `backend/tests/test_habit_learning.py` | 习惯采集、分析、检索 |
| `backend/tests/test_conflict_detector.py` | 扫描线算法、冲突图 |
| `backend/tests/test_dialog_state.py` | 多轮对话槽位补全 |
| `backend/tests/test_reminder_aggregator.py` | 提醒聚合与降噪 |
| `backend/tests/test_workflow.py` | LangGraph 工作流节点 |
| `backend/tests/test_preference_learner.py` | 偏好学习 |
| `backend/tests/test_task_splitter.py` | 智能任务拆分 |

### 9.2 测试重点

```python
# 向量存储测试要点
def test_add_and_search_habit():
    """测试习惯的添加和语义搜索"""
    
def test_search_with_filters():
    """测试带过滤的语义搜索"""
    
def test_persistence():
    """测试数据持久化（重启后数据不丢失）"""

# 冲突检测测试要点
def test_scanline_basic_overlap():
    """测试基本时间重叠检测"""
    
def test_scanline_with_buffer():
    """测试包含缓冲时间的冲突检测"""
    
def test_scanline_with_travel():
    """测试包含通勤时间的冲突检测"""
    
def test_conflict_graph_connectivity():
    """测试冲突图的连通性"""
    
def test_performance_large_dataset():
    """测试大数据集下的性能（1000+ 事件）"""

# 工作流测试要点
def test_workflow_happy_path():
    """测试正常工作流"""
    
def test_workflow_clarification_needed():
    """测试需要澄清的场景"""
    
def test_workflow_conflict_detected():
    """测试检测到冲突的场景"""
```

---

## 十、整体测试验证清单

### 10.1 功能验证

| 编号 | 验证项 | 预期结果 | 状态 |
|------|--------|----------|------|
| FV-1 | 创建事件后自动采集习惯 | ChromaDB 中存在对应向量 | ☐ |
| FV-2 | 模糊语义搜索 "晚上做饭" | 返回 18:00 左右的习惯匹配 | ☐ |
| FV-3 | LLM 输出格式错误 | 自动 fallback，不崩溃 | ☐ |
| FV-4 | 多轮对话槽位补全 | 系统主动追问缺失信息 | ☐ |
| FV-5 | 1000 事件冲突检测 | 响应时间 < 1 秒 | ☐ |
| FV-6 | 冲突链检测 | 正确识别 A↔B↔C 连锁冲突 | ☐ |
| FV-7 | 提醒聚合 | 3 条相近提醒合并为 1 条 | ☐ |
| FV-8 | 免打扰时段 | 23:00-07:00 不发送提醒 | ☐ |
| FV-9 | 偏好感知建议 | 避开用户不喜欢的时段 | ☐ |
| FV-10 | 智能任务拆分 | 根据空档自动拆分长任务 | ☐ |

### 10.2 性能验证

| 编号 | 验证项 | 指标 | 状态 |
|------|--------|------|------|
| PV-1 | 向量搜索延迟 | < 100ms | ☐ |
| PV-2 | Gemini Embedding API 延迟 | < 300ms/句（含网络） | ☐ |
| PV-3 | 冲突检测（1000事件） | < 1s | ☐ |
| PV-4 | 内存占用增长 | 稳定，无泄漏 | ☐ |
| PV-5 | ChromaDB 磁盘占用 | < 500MB（10000条向量） | ☐ |

### 10.3 集成验证

| 编号 | 验证项 | 状态 |
|------|--------|------|
| IV-1 | Docker Compose 全服务启动 | ☐ |
| IV-2 | 前端与后端 API 联调 | ☐ |
| IV-3 | WebSocket 实时推送正常 | ☐ |
| IV-4 | Celery 定时任务正常运行 | ☐ |
| IV-5 | 88 个现有测试全部通过 | ☐ |
| IV-6 | 新增测试全部通过 | ☐ |

---

## 附录：实施路线图

### Phase 1: 基础设施与 P0（预计 3-5 天）

1. 安装 ChromaDB，配置 Gemini Embedding API 客户端
2. 实现向量存储封装和三路习惯采集（被动+主动+对话）
3. 实现 Pydantic 验证层
4. 实现多轮对话槽位补全
5. 替换冲突检测为扫描线算法

### Phase 2: 智能体验 P1（预计 3-4 天）

1. 实现偏好学习服务
2. 实现模糊语义搜索与联想
3. 实现情境感知提醒
4. 实现提醒聚合与降噪

### Phase 3: 架构改善 P2（预计 3-5 天）

1. 引入 LangGraph，重构工作流
2. 前端 Store 渐进拆分（Phase 1: assistant → Phase 2: reminders）
3. 实现智能任务拆分
4. 全面测试与优化

---

> **备注**：本方案为 V6 智能化升级计划，建议在 V5 稳定性修复完成后开始实施。每个 Phase 完成后应进行完整回归测试，确保不破坏现有功能。
