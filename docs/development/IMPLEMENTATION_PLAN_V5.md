# 个人事务助手系统实现计划 V5 - 系统优化与稳定性提升

## 0. 现状总结

### 0.1 V4 完成情况回顾

**V4 计划执行进度**: 85%

已完成的核心功能：
- ✅ Tauri 2 桌面端封装（基础框架）
- ✅ Capacitor 移动端封装（基础框架）
- ✅ 地图服务深度集成（高德 + Google双引擎）
- ✅ 天气服务基础集成（和风天气 API）
- ⚠️ 语音输入/输出（仅预留接口，未实际实现）

**当前系统运行状态**：
- ✅ 后端服务正常运行（Docker Compose 4 容器）
- ✅ 前端开发服务器运行中（Vite 端口 8888）
- ✅ Celery Beat定时调度器运行（5 分钟间隔）
- ✅ Celery Worker任务处理正常
- ✅ Redis缓存服务正常
- ✅ 88 个单元测试全部通过

### 0.2 当前暴露的重大问题

基于最新一轮的系统测试和用户反馈，发现以下严重影响可用性的问题：

#### 🔴 P0 级问题（阻碍基本使用）

| 编号 | 问题描述 | 影响范围 | 严重程度 |
|------|----------|----------|----------|
| P0-1 | AI 助手回复文本不可读 | 所有对话场景 | 🔴 严重 |
| P0-2 | 无法开启新对话，上下文无限累积 | 长期使用场景 | 🔴 严重 |
| P0-3 | 提醒模块异常，启动时爆出巨量提醒 | 用户体验 | 🔴 严重 |
| P0-4 | AI 助手稳定性差，失败无报错 | 所有交互场景 | 🔴 严重 |

#### 🟡 P1 级问题（体验缺陷）

| 编号 | 问题描述 | 影响范围 | 严重程度 |
|------|----------|----------|----------|
| P1-1 | 前端不支持国际化 | 中文用户 | 🟡 中等 |
| P1-2 | 模糊提示词处理呆板 | 自然语言交互 | 🟡 中等 |
| P1-3 | 错误处理不完善，静默失败 | 所有功能模块 | 🟡 中等 |
| P1-4 | 日志记录缺失，难以调试 | 开发维护 | 🟡 中等 |

#### 🟢 P2 级问题（体验优化）

| 编号 | 问题描述 | 影响范围 | 严重程度 |
|------|----------|----------|----------|
| P2-1 | WebSocket 未充分利用 | 实时推送 | 🟢 轻微 |
| P2-2 | 前端加载状态缺失 | 用户体验 | 🟢 轻微 |
| P2-3 | 表单验证不足 | 数据质量 | 🟢 轻微 |
| P2-4 | 性能监控空白 | 运维能力 | 🟢 轻微 |

### 0.3 问题根因分析

#### P0-1: AI 回复文本不可读

**现象**：AI 助手的回复包含大量原始 JSON、Markdown 标记混乱、结构化数据直接展示给用户

**根因**：
1. `backend/app/services/assistant.py` 中 `send_message()`方法返回的是原始 Gemini响应
2. 缺少响应后处理层（格式化、结构化、人类可读转换）
3. 前端 `AssistantPanel.vue`直接使用`marked.parse()` 渲染，未做清洗

**涉及文件**：
- `backend/app/services/assistant.py` (第 95-140 行)
- `backend/app/api/routes/assistant.py` (第 45-68 行)
- `frontend/src/components/AssistantPanel.vue` (第 28-32 行)

#### P0-2: 无法开启新对话

**现象**：所有对话上下文永久累积，导致 Token 超限、响应变慢、最终崩溃

**根因**：
1. 数据库中有 `AssistantSession`表但无"新建会话"API
2. 前端无"新建对话"按钮和相关 UI
3. 缺少会话归档/清除机制
4. `AssistantService.get_current_session()`总是返回唯一会话

**涉及文件**：
- `backend/app/repositories/assistant.py` (缺少 create_session 方法)
- `backend/app/api/routes/assistant.py` (缺少 POST /sessions 端点)
- `frontend/src/stores/workspace.ts` (缺少 newSession 动作)
- `frontend/src/components/AssistantPanel.vue` (缺少新建按钮)

#### P0-3: 提醒风暴

**现象**：启动项目进入前端时爆出巨量提醒

**根因**：
1. `backend/app/jobs/reminders.py` 中 `scan_upcoming_reminders()` 每次扫描都会为未来 30 分钟内的事件创建提醒
2. 缺少去重机制（同一事件多次扫描创建多个提醒）
3. 缺少冷却机制（短时间内不重复提醒）
4. 缺少时间窗口限制（历史事件也被触发）

**涉及文件**：
- `backend/app/jobs/reminders.py` (第 20-60 行)
- `backend/app/jobs/reminders.py` (第 70-110 行 departure reminders)
- `backend/app/models.py` (Reminder 模型缺少唯一约束)

#### P0-4: AI 助手稳定性差

**现象**：日程创建失败但无任何报错提示

**根因**：
1. `AssistantService.send_message()` 缺少 try-catch 包裹
2. Gemini API 调用失败时无重试机制
3. 前端 `workspace.sendAssistantMessage()` 未捕获异常
4. Toast 通知仅在成功时显示，失败时静默

**涉及文件**：
- `backend/app/services/assistant.py` (第 95-140 行)
- `backend/app/tools/gemini.py` (缺少重试逻辑)
- `frontend/src/stores/workspace.ts` (sendAssistantMessage 方法)

---

## 1. 实施目标

### 1.1 核心目标

通过本次 V5 优化计划，实现以下目标：

1. **可用性达到生产级别**
   - AI 回复人类可读（Markdown 格式化 + 结构化）
   - 可随时开启/切换/归档会话
   - 不会再被提醒轰炸
   - 错误时有明确友好的提示

2. **国际化支持**
   - 中英文一键切换
   - 日期/时间格式本地化
   - 货币/数字格式适配

3. **智能化增强**
   - 模糊需求会主动追问澄清
   - 多轮对话更自然流畅
   - 上下文理解更准确

4. **稳定性保障**
   - API 失败自动重试（最多 3 次）
   - 超时保护机制（30 秒超时）
   - 完善的错误边界处理

5. **开发友好**
   - 结构化日志便于调试
   - 性能监控定位瓶颈
   - WebSocket 实时推送恢复

### 1.2 技术选型

**保持不变的技术栈**：
- 后端：FastAPI + SQLAlchemy 2.0 + Celery + Redis
- 前端：Vue 3 + TypeScript + Vite
- 数据库：SQLite（开发）/ PostgreSQL（生产可选）
- AI 模型：Google Gemini 2.0 Flash

**新增技术组件**：
- 国际化：`vue-i18n@10.x`
- Markdown 渲染增强：`markdown-it@4.x` + 自定义插件
- 日志增强：`loguru@0.7.x`（后端）
- 状态管理：Pinia（已有，加强使用）

---

## 2. 优先级任务清单

### 2.1 P0 级任务（紧急修复 - 必须完成）

| 任务 ID | 任务名称 | 预计工时 | 依赖关系 | 验收标准 |
|---------|----------|----------|----------|----------|
| P0-1 | AI 助手回复文本格式化 | 1 天 | 无 | 回复清晰可读，无原始 JSON |
| P0-2 | 会话管理重构 | 1.5 天 | P0-1 | 可新建/切换/归档会话 |
| P0-3 | 提醒风暴修复 | 1 天 | 无 | 不再批量弹出历史提醒 |
| P0-4 | 错误处理增强 | 1.5 天 | P0-1 | 失败时有明确 Toast 提示 |

**小计**: 5 天

### 2.2 P1 级任务（重要优化 - 应该完成）

| 任务 ID | 任务名称 | 预计工时 | 依赖关系 | 验收标准 |
|---------|----------|----------|----------|----------|
| P1-1 | 前端国际化（i18n） | 2 天 | 无 | 中英双语无缝切换 |
| P1-2 | AI 助手稳定性提升 | 1.5 天 | P0-4 | 自动重试 + 超时保护 |
| P1-3 | 模糊提示词优化 | 1.5 天 | P0-1 | 主动追问澄清 |
| P1-4 | 日志系统完善 | 1 天 | P0-4 | 结构化日志 + 分级记录 |

**小计**: 6 天

### 2.3 P2 级任务（体验提升 - 建议完成）

| 任务 ID | 任务名称 | 预计工时 | 依赖关系 | 验收标准 |
|---------|----------|----------|----------|----------|
| P2-1 | WebSocket 实时推送恢复 | 1 天 | P0-3 | 新消息实时推送到前端 |
| P2-2 | 前端加载状态优化 | 1 天 | P1-1 | Skeleton 屏 + Loading动画 |
| P2-3 | 表单验证增强 | 1 天 | P1-1 | 实时校验 + 友好提示 |
| P2-4 | 性能监控埋点 | 1 天 | P1-4 | 响应时间追踪 dashboard |

**小计**: 4 天

### 2.4 总体时间表

```
第一阶段（5 天）: P0 紧急修复
  Day 1:  AI 回复格式化 + 错误处理基础
  Day 2:  会话管理重构（后端 + 前端）
  Day 3:  提醒风暴修复（去重 + 冷却）
  Day 4:  错误处理完善（全局 ErrorBoundary）
  Day 5:  P0 集成测试 + Bug 修复

第二阶段（6 天）: P1 重要优化
  Day 6-7: 前端国际化（i18n 配置 + 翻译文件）
  Day 8:  AI 稳定性提升（重试 + 超时）
  Day 9:  模糊提示词优化（澄清追问）
  Day 10: 日志系统完善
  Day 11: P1 集成测试 + Bug 修复

第三阶段（4 天）: P2 体验提升
  Day 12: WebSocket 实时推送恢复
  Day 13: 前端加载状态优化
  Day 14: 表单验证增强
  Day 15: 性能监控埋点

第四阶段（3 天）: 总体验收
  Day 16-17: 全链路集成测试
  Day 18: 性能调优 + 文档更新
```

**总计**: 18 个工作日（约 3.5 周）

---

## 3. 详细实现方案

### 3.1 P0-1: AI 助手回复文本格式化

#### 目标

将 AI 助手的原始响应转换为结构清晰、人类可读的 Markdown 格式。

#### 涉及文件

- `backend/app/services/assistant_response_formatter.py` 【新建】
- `backend/app/services/assistant.py` 【修改】
- `backend/app/api/schemas.py` 【修改】
- `frontend/src/components/AssistantPanel.vue` 【修改】

#### 实现步骤

##### Step 1: 创建响应格式化服务

**文件**: `backend/app/services/assistant_response_formatter.py`

```python
"""Assistant response formatter for human-readable output."""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt


class AssistantResponseFormatter:
    """Format raw LLM responses into clean, structured Markdown."""

    def __init__(self) -> None:
        self.md = MarkdownIt()

    def format_response(self, raw_text: str, context: dict[str, Any] | None = None) -> str:
        """
        Format raw LLM response into clean Markdown.
        
        Args:
            raw_text: Raw text from LLM (may contain JSON, code blocks, etc.)
            context: Optional context about what action was taken
            
        Returns:
            Clean, human-readable Markdown string
        """
        # Step 1: Remove any raw JSON objects that slipped through
        cleaned = self._remove_raw_json(raw_text)
        
        # Step 2: Normalize Markdown formatting
        cleaned = self._normalize_markdown(cleaned)
        
        # Step 3: Add contextual header if provided
        if context:
            cleaned = self._add_contextual_header(cleaned, context)
        
        # Step 4: Ensure proper line breaks and spacing
        cleaned = self._ensure_proper_spacing(cleaned)
        
        return cleaned

    def _remove_raw_json(self, text: str) -> str:
        """Remove raw JSON objects from text."""
        # Pattern to match JSON objects (simplified)
        json_pattern = r'\{[^{}]*"[^"]*"[^{}]*\}'
        text = re.sub(json_pattern, '', text)
        
        # Remove lines that are purely JSON arrays
        lines = text.split('\n')
        lines = [line for line in lines if not (line.strip().startswith('[') and line.strip().endswith(']'))]
        
        return '\n'.join(lines)

    def _normalize_markdown(self, text: str) -> str:
        """Normalize Markdown formatting."""
        # Ensure headers have proper spacing
        text = re.sub(r'^(#{1,6})(\w)', r'\1 \2', text, flags=re.MULTILINE)
        
        # Normalize bold formatting (** or __)
        text = re.sub(r'__(.+?)__', r'**\1**', text)
        
        # Normalize italic formatting (* or _)
        text = re.sub(r'_([^_]+?)_', r'*\1*', text)
        
        # Fix code blocks without language specifier
        text = re.sub(r'```\n', '```plaintext\n', text)
        
        return text

    def _add_contextual_header(self, text: str, context: dict[str, Any]) -> str:
        """Add contextual header based on action type."""
        action_type = context.get('action_type', 'general')
        
        headers = {
            'create_event': '✅ 已创建日程',
            'create_task': '✅ 已创建任务',
            'conflict_warning': '⚠️ 检测到冲突',
            'suggest_schedule': '💡 建议安排',
            'apply_schedule': '✅ 已应用建议',
            'propose_event': '📅 日程提议',
            'apply_event_proposal': '✅ 已确认日程',
            'general': '💬 助手回复',
        }
        
        header = headers.get(action_type, headers['general'])
        return f"{header}\n\n{text}"

    def _ensure_proper_spacing(self, text: str) -> str:
        """Ensure proper spacing between paragraphs and sections."""
        # Ensure single blank line between paragraphs
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Ensure space after punctuation
        text = re.sub(r'([。.!?！？])([^\s\n])', r'\1 \2', text)
        
        return text.strip()
```

##### Step 2: 修改 AssistantService 使用格式化器

**文件**: `backend/app/services/assistant.py`

**修改位置**: 第 95-140 行的 `send_message` 方法

```python
# 在文件顶部导入
from app.services.assistant_response_formatter import AssistantResponseFormatter

# 在 AssistantService.__init__ 中添加
def __init__(self) -> None:
    # ... existing code ...
    self.formatter = AssistantResponseFormatter()

# 修改 send_message 方法的返回部分（约第 135 行）
async def send_message(self, user_id: str, payload: AssistantMessageCreate) -> AssistantResponse:
    # ... existing code ...
    
    # 原有代码生成 response_content
    response_content = await self._process_message_flow(...)
    
    # NEW: 格式化响应
    formatted_content = self.formatter.format_response(
        raw_text=response_content,
        context={
            'action_type': last_action.type if last_action else 'general',
            'user_id': user_id,
        }
    )
    
    # 使用格式化后的内容创建消息
    assistant_message = await self.repository.create_message(
        session_id=session.id,
        role="assistant",
        content=formatted_content,  # 使用格式化后的内容
    )
    
    # ... rest of existing code ...
```

##### Step 3: 前端优化 Markdown 渲染

**文件**: `frontend/src/components/AssistantPanel.vue`

**修改位置**: 第 28-32 行的 `renderMarkdown` 函数

```typescript
// 替换原有的 renderMarkdown 函数
function renderMarkdown(text: string): string {
  // Enhanced markdown rendering with better sanitization
  const html = marked.parse(text, {
    async: false,
    gfm: true,
    breaks: true,
  }) as string;
  
  // Sanitize HTML to prevent XSS
  const sanitized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'code', 'pre', 'blockquote'],
    ALLOWED_ATTR: [],
  });
  
  return sanitized;
}
```

**需要安装的依赖**:
```bash
cd frontend
pnpm add dompurify
pnpm add -D @types/dompurify
```

#### 单元测试

**文件**: `backend/tests/test_assistant_response_formatter.py`【新建】

```python
"""Tests for Assistant response formatter."""

import pytest
from app.services.assistant_response_formatter import AssistantResponseFormatter


@pytest.fixture
def formatter():
    return AssistantResponseFormatter()


def test_format_clean_markdown(formatter):
    """Test formatting of clean Markdown input."""
    raw = "## Hello\n\nThis is **bold** and *italic*."
    result = formatter.format_response(raw)
    
    assert "## Hello" in result
    assert "**bold**" in result
    assert "*italic*" in result


def test_remove_raw_json(formatter):
    """Test removal of raw JSON from response."""
    raw = '''Here's the event I created:
{"id": 123, "title": "Meeting"}
    
The event is scheduled for tomorrow.'''
    result = formatter.format_response(raw)
    
    assert '{"id": 123' not in result
    assert "event I created" in result
    assert "scheduled for tomorrow" in result


def test_add_contextual_header(formatter):
    """Test contextual header addition."""
    raw = "Event created successfully."
    result = formatter.format_response(raw, {'action_type': 'create_event'})
    
    assert "✅ 已创建日程" in result
    assert "Event created successfully" in result


def test_normalize_markdown_headers(formatter):
    """Test Markdown header normalization."""
    raw = "#No Space Header"
    result = formatter.format_response(raw)
    
    assert "# No Space Header" in result


def test_ensure_proper_spacing(formatter):
    """Test proper spacing enforcement."""
    raw = "Para 1\n\n\n\nPara 2"
    result = formatter.format_response(raw)
    
    # Should reduce multiple blank lines to one
    assert "\n\n\n" not in result
    assert "Para 1" in result
    assert "Para 2" in result
```

---

### 3.2 P0-2: 会话管理重构

#### 目标

实现完整的会话管理能力：新建、切换、归档、清除历史记录。

#### 涉及文件

- `backend/app/repositories/assistant.py` 【修改】
- `backend/app/api/routes/assistant.py` 【修改】
- `backend/app/api/schemas.py` 【修改】
- `frontend/src/stores/workspace.ts` 【修改】
- `frontend/src/components/AssistantPanel.vue` 【修改】

#### 实现步骤

##### Step 1: 扩展 Repository 层

**文件**: `backend/app/repositories/assistant.py`

**添加方法**（在文件末尾）:

```python
# 在 AssistantRepository 类中添加新方法

async def create_session(
    self,
    user_id: str,
    title: str | None = None,
) -> AssistantSession:
    """Create a new assistant session."""
    session = AssistantSession(
        user_id=user_id,
        title=title or f"新对话 {datetime.now(timezone.utc).strftime('%m-%d %H:%M')}",
        created_at=datetime.now(timezone.utc),
    )
    self.session.add(session)
    await self.session.commit()
    await self.session.refresh(session)
    return session


async def archive_session(self, session_id: int, user_id: str) -> bool:
    """Archive an existing session."""
    session = await self.get_session(session_id, user_id)
    if session is None:
        return False
    
    session.is_archived = True
    await self.session.commit()
    return True


async def get_active_sessions(self, user_id: str, limit: int = 20) -> list[AssistantSession]:
    """Get all active (non-archived) sessions for a user."""
    result = await self.session.execute(
        select(AssistantSession)
        .where(AssistantSession.user_id == user_id)
        .where(AssistantSession.is_archived == False)
        .order_by(AssistantSession.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def clear_session_messages(self, session_id: int, user_id: str) -> bool:
    """Clear all messages in a session."""
    session = await self.get_session(session_id, user_id)
    if session is None:
        return False
    
    await self.session.execute(
        delete(AssistantMessage).where(AssistantMessage.session_id == session_id)
    )
    await self.session.commit()
    return True
```

##### Step 2: 添加 API 端点

**文件**: `backend/app/api/routes/assistant.py`

**添加端点**（在文件适当位置）:

```python
@router.post("/sessions", response_model=AssistantSessionRead, tags=["assistant"])
async def create_assistant_session(
    payload: AssistantSessionCreate,
    current_user: UserProfile = Depends(get_current_user),
) -> AssistantSessionRead:
    """Create a new assistant session."""
    service = AssistantService()
    session = await service.repository.create_session(
        user_id=current_user.id,
        title=payload.title,
    )
    return AssistantSessionRead.model_validate(session)


@router.get("/sessions", response_model=list[AssistantSessionRead], tags=["assistant"])
async def list_assistant_sessions(
    limit: int = Query(20, ge=1, le=100),
    current_user: UserProfile = Depends(get_current_user),
) -> list[AssistantSessionRead]:
    """List all active assistant sessions."""
    service = AssistantService()
    sessions = await service.repository.get_active_sessions(
        user_id=current_user.id,
        limit=limit,
    )
    return [AssistantSessionRead.model_validate(s) for s in sessions]


@router.post("/sessions/{session_id}/archive", tags=["assistant"])
async def archive_assistant_session(
    session_id: int,
    current_user: UserProfile = Depends(get_current_user),
) -> dict[str, bool]:
    """Archive an assistant session."""
    service = AssistantService()
    success = await service.repository.archive_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    return {"success": success}


@router.delete("/sessions/{session_id}/messages", tags=["assistant"])
async def clear_session_messages(
    session_id: int,
    current_user: UserProfile = Depends(get_current_user),
) -> dict[str, bool]:
    """Clear all messages in a session."""
    service = AssistantService()
    success = await service.repository.clear_session_messages(
        session_id=session_id,
        user_id=current_user.id,
    )
    return {"success": success}
```

##### Step 3: 添加 Schema

**文件**: `backend/app/api/schemas.py`

**添加 Schema**（在适当位置）:

```python
class AssistantSessionCreate(BaseModel):
    """Schema for creating a new assistant session."""
    title: str | None = Field(None, description="Optional session title")
    max_length: int | None = None


class AssistantSessionList(BaseModel):
    """Schema for listing assistant sessions."""
    sessions: list[AssistantSessionRead]
    total: int
```

##### Step 4: 前端 Store 扩展

**文件**: `frontend/src/stores/workspace.ts`

**添加 actions**（在 store 中）:

```typescript
// 添加新的 state
const assistantSessions = ref<AssistantSession[]>([]);
const currentSessionId = ref<number | null>(null);

// 添加新的 actions
async function createNewAssistantSession(title?: string) {
  try {
    const response = await api.post('/assistant/sessions', { title });
    const session = response.data;
    assistantSessions.value.unshift(session);
    currentSessionId.value = session.id;
    messages.value = []; // Clear local messages
    showToast({ title: '新对话已创建', type: 'success' });
  } catch (error) {
    showToast({ title: '创建对话失败', type: 'error' });
    throw error;
  }
}

async function switchAssistantSession(sessionId: number) {
  try {
    currentSessionId.value = sessionId;
    // Load messages for this session
    const response = await api.get(`/assistant/sessions/${sessionId}/messages`);
    messages.value = response.data;
  } catch (error) {
    showToast({ title: '切换对话失败', type: 'error' });
    throw error;
  }
}

async function archiveAssistantSession(sessionId: number) {
  try {
    await api.post(`/assistant/sessions/${sessionId}/archive`);
    assistantSessions.value = assistantSessions.value.filter(s => s.id !== sessionId);
    showToast({ title: '对话已归档', type: 'success' });
  } catch (error) {
    showToast({ title: '归档失败', type: 'error' });
    throw error;
  }
}

async function loadAssistantSessions() {
  try {
    const response = await api.get('/assistant/sessions');
    assistantSessions.value = response.data.sessions;
    if (assistantSessions.value.length > 0 && !currentSessionId.value) {
      currentSessionId.value = assistantSessions.value[0].id;
    }
  } catch (error) {
    console.error('Failed to load sessions:', error);
  }
}
```

##### Step 5: 前端 UI 组件

**文件**: `frontend/src/components/AssistantPanel.vue`

**在模板中添加会话控制按钮**（在 header 区域）:

```vue
<!-- Header -->
<div class="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
  <div class="flex items-center gap-2">
    <h2 class="text-base font-bold">{{ t('assistant.title') }}</h2>
    
    <!-- Session selector dropdown -->
    <select 
      v-model="currentSessionId" 
      @change="switchSession"
      class="ml-2 rounded-md border border-border bg-surface px-2 py-1 text-sm"
    >
      <option v-for="session in sessions" :key="session.id" :value="session.id">
        {{ session.title || formatDate(session.created_at) }}
      </option>
    </select>
  </div>
  
  <div class="flex items-center gap-2">
    <!-- New conversation button -->
    <button
      @click="createNewSession"
      class="rounded-lg p-2 hover:bg-surface-2"
      :title="t('assistant.new_conversation')"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
      </svg>
    </button>
    
    <!-- Archive button -->
    <button
      v-if="currentSessionId"
      @click="archiveCurrentSession"
      class="rounded-lg p-2 hover:bg-surface-2"
      :title="t('assistant.archive')"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
    </button>
  </div>
</div>
```

#### 单元测试

**文件**: `backend/tests/test_assistant_sessions.py`【新建】

```python
"""Tests for assistant session management."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def authenticated_client(auth_token):
    client.headers["Authorization"] = f"Bearer {auth_token}"
    return client


def test_create_new_session(authenticated_client):
    """Test creating a new assistant session."""
    response = authenticated_client.post(
        "/api/assistant/sessions",
        json={"title": "Test Conversation"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert "id" in data


def test_list_sessions(authenticated_client):
    """Test listing assistant sessions."""
    response = authenticated_client.get("/api/assistant/sessions")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_archive_session(authenticated_client):
    """Test archiving a session."""
    # Create a session first
    create_resp = authenticated_client.post(
        "/api/assistant/sessions",
        json={"title": "To Archive"}
    )
    session_id = create_resp.json()["id"]
    
    # Archive it
    archive_resp = authenticated_client.post(
        f"/api/assistant/sessions/{session_id}/archive"
    )
    
    assert archive_resp.status_code == 200
    assert archive_resp.json()["success"] is True


def test_clear_session_messages(authenticated_client):
    """Test clearing messages from a session."""
    # Create session and send message first
    create_resp = authenticated_client.post(
        "/api/assistant/sessions",
        json={}
    )
    session_id = create_resp.json()["id"]
    
    # Send a message
    authenticated_client.post(
        "/api/assistant/messages",
        json={
            "session_id": session_id,
            "content": "Hello"
        }
    )
    
    # Clear messages
    clear_resp = authenticated_client.delete(
        f"/api/assistant/sessions/{session_id}/messages"
    )
    
    assert clear_resp.status_code == 200
    assert clear_resp.json()["success"] is True
```

---

### 3.3 P0-3: 提醒风暴修复

#### 目标

修复提醒模块，防止启动时批量弹出历史提醒，实现智能去重和冷却机制。

#### 涉及文件

- `backend/app/jobs/reminders.py` 【修改】
- `backend/app/models.py` 【修改】
- `backend/tests/test_reminder_jobs.py` 【修改】

#### 实现步骤

##### Step 1: 添加数据库唯一约束

**文件**: `backend/app/models.py`

**修改 Reminder 模型**（添加唯一约束）:

```python
class Reminder(Base):
    __tablename__ = "reminders"
    
    # ... existing fields ...
    
    # Add unique constraint to prevent duplicate reminders
    __table_args__ = (
        UniqueConstraint(
            'user_id',
            'target_type',
            'target_id',
            'remind_type',
            'remind_at',
            name='uq_reminder_unique'
        ),
    )
```

**创建 Alembic 迁移**:

```bash
cd backend
alembic revision --autogenerate -m "Add unique constraint to reminders table"
alembic upgrade head
```

##### Step 2: 重构提醒扫描逻辑

**文件**: `backend/app/jobs/reminders.py`

**重写 scan_upcoming_reminders 函数**:

```python
@celery_app.task(name="app.jobs.reminders.scan_upcoming_reminders")
def scan_upcoming_reminders() -> dict[str, int]:
    """Scan for reminders that should soon be delivered."""
    return asyncio.run(_scan_upcoming_reminders())


async def _scan_upcoming_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=30)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.start_time.is_not(None),
                    Event.start_time >= now,
                    Event.start_time <= window_end,
                    # CRITICAL: Only consider events created in last 24 hours
                    Event.created_at >= now - timedelta(hours=24),
                )
            )
        ).all()

        generated_count = 0
        skipped_count = 0
        
        for event in upcoming_events:
            # Check if reminder already exists
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == event.user_id,
                    Reminder.target_type == "event",
                    Reminder.target_id == event.id,
                    Reminder.remind_type == "event_start",
                )
            )
            
            if existing is not None:
                skipped_count += 1
                continue

            # COOLING MECHANISM: Don't create reminder if event started >15 min ago
            minutes_since_start = (now - event.start_time).total_seconds() / 60
            if minutes_since_start > 15:
                skipped_count += 1
                continue

            payload = _build_event_start_reminder_payload(event=event, now=now)
            session.add(
                Reminder(
                    user_id=event.user_id,
                    **payload,
                )
            )
            generated_count += 1

        if generated_count:
            await session.commit()

        pending = await session.scalar(
            select(func.count(Reminder.id)).where(
                Reminder.status == "pending",
                Reminder.remind_at >= now,
                Reminder.remind_at <= window_end,
            )
        )

    return {
        "generated_count": generated_count,
        "skipped_count": skipped_count,
        "pending_count": int(pending or 0),
    }
```

**同样修改 scan_departure_reminders**:

```python
async def _scan_departure_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=2)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        upcoming_events = (
            await session.scalars(
                select(Event).where(
                    Event.departure_time.is_not(None),
                    Event.departure_time >= now,
                    Event.departure_time <= window_end,
                    # CRITICAL: Only recent events
                    Event.created_at >= now - timedelta(hours=24),
                )
            )
        ).all()

        generated_count = 0
        skipped_count = 0
        
        for event in upcoming_events:
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.user_id == event.user_id,
                    Reminder.target_type == "event",
                    Reminder.target_id == event.id,
                    Reminder.remind_type == "departure",
                )
            )
            
            if existing is not None:
                skipped_count += 1
                continue

            session.add(Reminder(user_id=event.user_id, **_build_departure_reminder_payload(event=event, now=now)))
            generated_count += 1

        if generated_count:
            await session.commit()

    return {
        "generated_count": generated_count,
        "skipped_count": skipped_count,
    }
```

##### Step 3: 添加提醒清理任务

**在 reminders.py 中添加新任务**:

```python
@celery_app.task(name="app.jobs.reminders.cleanup_old_reminders")
def cleanup_old_reminders() -> dict[str, int]:
    """Clean up old/archived reminders older than 7 days."""
    return asyncio.run(_cleanup_old_reminders())


async def _cleanup_old_reminders() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        # Delete old completed/cancelled reminders
        result = await session.execute(
            delete(Reminder).where(
                Reminder.status.in_(["completed", "cancelled"]),
                Reminder.remind_at < cutoff,
            )
        )
        
        deleted_count = result.rowcount
        await session.commit()

    return {"deleted_count": deleted_count}
```

**在 Celery Beat 配置中添加定期清理任务**:

**文件**: `backend/app/core/celery_beat.py` 或相应配置文件

```python
CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    "cleanup-old-reminders": {
        "task": "app.jobs.reminders.cleanup_old_reminders",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM
    },
}
```

#### 单元测试

**文件**: `backend/tests/test_reminder_jobs.py`

**添加测试用例**:

```python
def test_scan_upcoming_reminders_no_duplicates():
    """Test that reminder scanning doesn't create duplicates."""
    # Setup: Create an event and its reminder
    event = create_test_event(start_time=datetime.now(timezone.utc) + timedelta(minutes=15))
    create_test_reminder(
        target_type="event",
        target_id=event.id,
        remind_type="event_start",
    )
    
    # Run the scan
    result = scan_upcoming_reminders()
    
    # Should skip existing reminder
    assert result["generated_count"] == 0
    assert result["skipped_count"] == 1


def test_scan_upcoming_reminders_cooling_off():
    """Test cooling-off mechanism prevents old event reminders."""
    # Setup: Create an event that started 20 minutes ago
    old_event = create_test_event(
        start_time=datetime.now(timezone.utc) - timedelta(minutes=20)
    )
    
    # Run the scan
    result = scan_upcoming_reminders()
    
    # Should skip due to cooling-off
    assert result["generated_count"] == 0
    assert result["skipped_count"] == 1


def test_cleanup_old_reminders():
    """Test cleanup of old reminders."""
    # Setup: Create old completed reminders
    create_test_reminder(
        status="completed",
        remind_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    
    # Run cleanup
    result = cleanup_old_reminders()
    
    # Should delete old reminder
    assert result["deleted_count"] == 1
```

---

### 3.4 P0-4: 错误处理增强

#### 目标

实现完善的错误处理机制，确保所有失败都有明确的 Toast 提示和日志记录。

#### 涉及文件

- `backend/app/services/assistant.py` 【修改】
- `backend/app/tools/gemini.py` 【修改】
- `backend/app/core/error_handler.py` 【新建】
- `frontend/src/stores/workspace.ts` 【修改】
- `frontend/src/components/ErrorBoundary.vue` 【新建】

#### 实现步骤

##### Step 1: 创建全局错误处理器

**文件**: `backend/app/core/error_handler.py`

```python
"""Global error handler for the application."""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    """Base application error."""
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)


class AssistantError(AppError):
    """Assistant-specific errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="ASSISTANT_ERROR",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            **kwargs,
        )


class GeminiAPIError(AppError):
    """Gemini API errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="GEMINI_API_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            **kwargs,
        )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all uncaught exceptions."""
    # Log the error with full stack trace
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "request_path": str(request.url.path),
            "method": request.method,
            "traceback": traceback.format_exc(),
        }
    )
    
    # Handle known app errors
    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )
    
    # Handle HTTP exceptions
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": exc.detail,
                }
            },
        )
    
    # Generic 500 error for everything else
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
            }
        },
    )
```

**注册错误处理器**（在 `backend/app/main.py` 中）:

```python
from app.core.error_handler import global_exception_handler

app = FastAPI(title="Personal Assistant API")

# Register exception handler
app.add_exception_handler(Exception, global_exception_handler)
```

##### Step 2: 增强 Gemini Client 错误处理

**文件**: `backend/app/tools/gemini.py`

**添加重试逻辑和错误处理**:

```python
"""Gemini AI client with retry logic and error handling."""

from __future__ import annotations

import asyncio
from typing import Any

import google.generativeai as genai
from loguru import logger

from app.core.error_handler import GeminiAPIError


class GeminiClient:
    """Gemini AI client with automatic retry and error handling."""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    TIMEOUT = 30.0  # seconds
    
    def __init__(self) -> None:
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    async def generate_content(
        self,
        prompt: str,
        context: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate content with automatic retry."""
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                return await asyncio.wait_for(
                    self._generate_with_timeout(prompt, context),
                    timeout=self.TIMEOUT,
                )
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Gemini API timeout (attempt {attempt + 1}/{self.MAX_RETRIES})")
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
            except genai.types.BlockedPromptException as e:
                # Don't retry for blocked prompts
                raise GeminiAPIError(
                    message="请求被安全过滤器阻止，请尝试重新表述",
                    details={"reason": str(e)},
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini API error (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        
        # All retries exhausted
        raise GeminiAPIError(
            message=f"AI 服务暂时不可用（已重试{self.MAX_RETRIES}次）",
            details={"last_error": str(last_error)},
        )
    
    async def _generate_with_timeout(
        self,
        prompt: str,
        context: list[dict[str, Any]] | None = None,
    ) -> str:
        """Internal method to generate content."""
        # Build full prompt with context
        full_prompt = self._build_prompt(prompt, context)
        
        # Call Gemini API
        response = await asyncio.to_thread(
            self.model.generate_content,
            full_prompt,
        )
        
        if not response.text:
            raise ValueError("Empty response from Gemini API")
        
        return response.text
    
    def _build_prompt(
        self,
        prompt: str,
        context: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build full prompt with conversation context."""
        if not context:
            return prompt
        
        context_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in context[-10:]  # Last 10 messages for context
        ])
        
        return f"{context_text}\n\nAssistant: {prompt}"
```

##### Step 3: 增强 AssistantService 错误处理

**文件**: `backend/app/services/assistant.py`

**包装 send_message 方法**:

```python
from app.core.error_handler import AssistantError, GeminiAPIError

async def send_message(self, user_id: str, payload: AssistantMessageCreate) -> AssistantResponse:
    try:
        # Validate input
        if not payload.content or not payload.content.strip():
            raise AssistantError(
                message="消息内容不能为空",
                error_code="EMPTY_MESSAGE",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Get or create session
        if payload.session_id is None:
            current = await self.get_current_session(user_id=user_id)
            session = await self.repository.get_session(current.session.id, user_id=user_id)
        else:
            session = await self.repository.get_session(payload.session_id, user_id=user_id)
        
        if session is None:
            raise AssistantError(
                message="会话不存在",
                error_code="SESSION_NOT_FOUND",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Create user message
        user_message = await self.repository.create_message(
            session_id=session.id,
            role="user",
            content=payload.content.strip(),
        )
        
        # Process with Gemini (with error handling)
        try:
            response_content = await self._process_message_flow(
                session=session,
                user_message=user_message,
            )
        except GeminiAPIError as e:
            # Fallback response when AI fails
            response_content = self._get_fallback_response(payload.content)
            logger.warning(f"Using fallback response due to AI error: {e}")
        
        # Format response
        formatted_content = self.formatter.format_response(
            raw_text=response_content,
            context={'action_type': 'general'},
        )
        
        # Create assistant message
        assistant_message = await self.repository.create_message(
            session_id=session.id,
            role="assistant",
            content=formatted_content,
        )
        
        return AssistantResponse(
            message=AssistantMessageRead.model_validate(assistant_message),
            session=AssistantSessionRead.model_validate(session),
        )
        
    except AssistantError:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in send_message: {e}")
        raise AssistantError(
            message="处理消息时发生未知错误，请稍后重试",
            details={"error_type": type(e).__name__},
        )
    
    def _get_fallback_response(self, user_input: str) -> str:
        """Get fallback response when AI is unavailable."""
        return f"""抱歉，AI 服务暂时不可用。

不过我已经记录了您的消息：「{user_input}」

您可以：
1. 稍后重试，我会尽快处理
2. 直接在日历中手动创建日程
3. 查看建议面板获取今日推荐

给您带来不便，敬请谅解！"""
```

##### Step 4: 前端错误处理

**文件**: `frontend/src/stores/workspace.ts`

**增强 sendAssistantMessage**:

```typescript
async function sendAssistantMessage(content: string) {
  if (!content.trim()) {
    showToast({ title: '消息内容不能为空', type: 'warning' });
    return;
  }
  
  sending.value = true;
  
  try {
    // Optimistic update: add user message immediately
    const userMessage: AssistantMessage = {
      id: Date.now(), // Temporary ID
      session_id: currentSessionId.value!,
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
    };
    messages.value.push(userMessage);
    
    // Send to API
    const response = await api.post('/assistant/messages', {
      session_id: currentSessionId.value,
      content: content.trim(),
    });
    
    // Replace optimistic message with real one
    const aiMessageIndex = messages.value.findIndex(m => m.id === userMessage.id);
    if (aiMessageIndex !== -1) {
      messages.value[aiMessageIndex] = response.data.message;
    }
    
    // Update session
    if (response.data.session) {
      // Update session metadata if needed
    }
    
  } catch (error: any) {
    // Remove optimistic message on error
    messages.value = messages.value.filter(m => m.id !== userMessage.id);
    
    // Show error toast
    const errorMessage = error.response?.data?.error?.message 
      || '发送消息失败，请检查网络连接';
    
    showToast({ 
      title: errorMessage, 
      type: 'error',
      duration: 5000, // Longer duration for errors
    });
    
    // Log error for debugging
    console.error('Failed to send message:', error);
    
  } finally {
    sending.value = false;
  }
}
```

##### Step 5: 创建前端错误边界组件

**文件**: `frontend/src/components/ErrorBoundary.vue`

```vue
<script setup lang="ts">
import { defineComponent, h } from 'vue';

export default defineComponent({
  name: 'ErrorBoundary',
  props: {
    fallbackMessage: {
      type: String,
      default: '组件加载失败，请刷新页面重试',
    },
  },
  data() {
    return {
      hasError: false,
      error: null as Error | null,
    };
  },
  errorCaptured(err: Error) {
    this.hasError = true;
    this.error = err;
    console.error('Error captured by boundary:', err);
    return false; // Don't propagate error
  },
  render() {
    if (this.hasError) {
      return h('div', { class: 'p-4 text-center text-red-600' }, [
        h('p', { class: 'font-semibold' }, '出错了'),
        h('p', { class: 'text-sm mt-1' }, this.fallbackMessage),
        h('button', {
          class: 'mt-3 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700',
          onClick: () => window.location.reload(),
        }, '刷新页面'),
      ]);
    }
    return this.$slots.default?.();
  },
});
</script>
```

**在主应用中包裹组件**:

**文件**: `frontend/src/App.vue`

```vue
<template>
  <ErrorBoundary>
    <div class="min-h-screen bg-surface-2 font-body text-ink">
      <!-- Existing content -->
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import ErrorBoundary from '@/components/ErrorBoundary.vue';
// ... other imports
</script>
```

#### 单元测试

**文件**: `backend/tests/test_error_handling.py`【新建】

```python
"""Tests for error handling mechanisms."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.error_handler import AppError, AssistantError

client = TestClient(app)


def test_assistant_error_returns_proper_format():
    """Test that AssistantError returns properly formatted response."""
    @app.get("/test-error")
    def raise_assistant_error():
        raise AssistantError(
            message="Test error message",
            details={"test": "data"},
        )
    
    response = client.get("/test-error")
    
    assert response.status_code == 503
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "ASSISTANT_ERROR"
    assert data["error"]["message"] == "Test error message"
    assert data["error"]["details"]["test"] == "data"


def test_unhandled_exception_returns_500():
    """Test that unhandled exceptions return 500 with generic message."""
    @app.get("/test-unexpected-error")
    def raise_unexpected_error():
        raise ValueError("Unexpected error")
    
    response = client.get("/test-unexpected-error")
    
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert "unexpected error" in data["error"]["message"].lower()


def test_empty_message_returns_400(auth_token):
    """Test that empty message returns 400 error."""
    client.headers["Authorization"] = f"Bearer {auth_token}"
    
    response = client.post(
        "/api/assistant/messages",
        json={"session_id": 1, "content": ""}
    )
    
    assert response.status_code == 400
    assert "不能为空" in response.json()["error"]["message"]
```

---

## 4. 后续优化任务（P1-P2）

由于篇幅限制，P1 和 P2 任务的详细实现方案将在后续文档中展开。以下是简要概述：

### 4.1 P1-1: 前端国际化（i18n）

**目标**: 支持中英文一键切换

**关键步骤**:
1. 安装 `vue-i18n@10.x`
2. 创建翻译文件 (`src/locales/en-US.json`, `zh-CN.json`)
3. 配置 i18n 实例 (`src/i18n.ts`)
4. 在所有组件中使用 `$t()` 替换硬编码文本
5. 添加语言切换器 UI 组件

**预计工时**: 2 天

### 4.2 P1-2: AI 助手稳定性提升

**目标**: 自动重试 + 超时保护 + 降级方案

**关键步骤**:
1. 实现指数退避重试策略
2. 添加电路断路器模式（Circuit Breaker）
3. 完善降级响应模板库
4. 添加 AI 服务健康检查端点

**预计工时**: 1.5 天

### 4.3 P1-3: 模糊提示词优化

**目标**: 主动追问澄清 + 多轮对话优化

**关键步骤**:
1. 实现意图置信度评估
2. 低置信度时触发澄清追问
3. 添加追问模板库（时间不明/地点不明/任务不清等）
4. 优化上下文窗口管理

**预计工时**: 1.5 天

### 4.4 P1-4: 日志系统完善

**目标**: 结构化日志 + 分级记录 + 敏感信息脱敏

**关键步骤**:
1. 全面引入 `loguru`
2. 统一日志格式（JSON 结构化）
3. 实现日志分级（DEBUG/INFO/WARNING/ERROR）
4. 添加请求追踪 ID
5. 敏感信息自动脱敏

**预计工时**: 1 天

### 4.5 P2-1: WebSocket 实时推送恢复

**目标**: 新消息/提醒实时推送到前端

**关键步骤**:
1. 修复 `backend/app/api/ws.py`连接管理
2. 实现消息广播机制
3. 前端添加 WebSocket 客户端
4. 添加断线重连逻辑

**预计工时**: 1 天

### 4.6 P2-2: 前端加载状态优化

**目标**: Skeleton 屏 + Loading 动画

**关键步骤**:
1. 创建通用 Skeleton 组件
2. 为所有异步操作添加 loading 状态
3. 实现渐进式内容加载
4. 添加乐观更新（Optimistic Updates）

**预计工时**: 1 天

### 4.7 P2-3: 表单验证增强

**目标**: 实时校验 + 友好提示

**关键步骤**:
1. 添加表单验证规则引擎
2. 实现实时字段验证
3. 创建友好的错误提示文案
4. 添加防抖提交机制

**预计工时**: 1 天

### 4.8 P2-4: 性能监控埋点

**目标**: 响应时间追踪 + Dashboard

**关键步骤**:
1. 添加 API 响应时间中间件
2. 实现前端性能监控（FP/FCP/LCP）
3. 创建简单的监控 Dashboard
4. 设置性能告警阈值

**预计工时**: 1 天

---

## 5. 单元测试规范

### 5.1 测试覆盖率要求

- **核心服务层**: ≥90%（assistant, events, tasks, suggestions）
- **API 路由层**: ≥80%
- **工具层**: ≥85%（gemini, maps, weather）
- **作业任务层**: ≥75%（reminder jobs, celery tasks）
- **前端组件**: ≥60%（关键组件）

### 5.2 测试编写规范

```python
"""Test module naming convention."""

# File naming: test_<module>.py
# Example: test_assistant_service.py

import pytest
from unittest.mock import Mock, patch, AsyncMock

@pytest.fixture
def mock_gemini_client():
    """Fixture for mocking Gemini client."""
    with patch('app.services.assistant.GeminiClient') as mock:
        yield mock

@pytest.mark.asyncio
async def test_send_message_success(mock_gemini_client):
    """Test successful message sending."""
    # Arrange
    mock_gemini_client.return_value.generate_content = AsyncMock(
        return_value="Success response"
    )
    
    # Act
    result = await service.send_message(user_id="test", payload=payload)
    
    # Assert
    assert result.message.role == "assistant"
    assert result.message.content is not None
```

### 5.3 必测场景清单

**Assistant 服务**:
- [ ] 正常消息发送
- [ ] 空消息拒绝
- [ ] Gemini API 超时
- [ ] Gemini API 返回空响应
- [ ] 会话不存在
- [ ] 格式化响应正确性
- [ ] Fallback 响应触发

**提醒服务**:
- [ ] 扫描即将开始的事件
- [ ] 去重机制有效性
- [ ] 冷却机制有效性
- [ ] 清理旧提醒
- [ ] 出发时间提醒

**会话管理**:
- [ ] 创建新会话
- [ ] 切换会话
- [ ] 归档会话
- [ ] 清除消息
- [ ] 列出活跃会话

**错误处理**:
- [ ] AppError 正确序列化
- [ ] 未处理异常返回 500
- [ ] 前端 Toast 正确显示
- [ ] 日志记录完整堆栈

---

## 6. 测试验证清单

### 6.1 P0 任务验收测试

#### P0-1: AI 回复格式化

- [ ] 创建事件后回复清晰可读（无原始 JSON）
- [ ] 冲突警告格式化正确
- [ ] 建议列表格式化正确
- [ ] Markdown 渲染无乱码
- [ ] 特殊字符正确处理

#### P0-2: 会话管理

- [ ] 点击"新建对话"创建新会话
- [ ] 下拉菜单切换会话正常
- [ ] 归档后可从列表中隐藏
- [ ] 清除消息后会话保留但内容为空
- [ ] 不同会话消息隔离

#### P0-3: 提醒风暴

- [ ] 重启系统不再批量弹出历史提醒
- [ ] 同一事件不会收到重复提醒
- [ ] 已开始超过 15 分钟的事件不触发提醒
- [ ] 清理任务正常工作

#### P0-4: 错误处理

- [ ] AI 服务超时时显示友好提示
- [ ] 网络错误时显示 Toast
- [ ] 空消息提交被拦截
- [ ] 后端错误日志记录完整堆栈
- [ ] 前端错误边界捕获组件崩溃

### 6.2 P1 任务验收测试

#### P1-1: 国际化

- [ ] 中英文切换立即生效
- [ ] 所有界面文本已翻译
- [ ] 日期格式符合区域习惯
- [ ] 语言偏好持久化保存

#### P1-2: AI 稳定性

- [ ] API 失败自动重试（最多 3 次）
- [ ] 30 秒超时触发降级响应
- [ ] 降级回应有实际帮助价值

#### P1-3: 模糊提示词

- [ ] "明天开会"触发时间追问
- [ ] "见朋友"触发地点/时间追问
- [ ] 多轮对话上下文保持

#### P1-4: 日志系统

- [ ] 所有错误记录到日志文件
- [ ] 日志可按级别过滤
- [ ] 敏感信息自动脱敏

### 6.3 P2 任务验收测试

#### P2-1: WebSocket

- [ ] 新消息实时推送到前端
- [ ] 提醒实时弹窗通知
- [ ] 断线后自动重连

#### P2-2: 加载状态

- [ ] 数据加载时显示 Skeleton
- [ ] 提交按钮显示 Loading 旋转图标
- [ ] 长时间操作显示进度条

#### P2-3: 表单验证

- [ ] 无效邮箱即时提示
- [ ] 必填字段未填禁止提交
- [ ] 错误提示友好具体

#### P2-4: 性能监控

- [ ] Dashboard 显示 API 响应时间
- [ ] 慢查询自动告警
- [ ] 前端加载时间可追踪

---

## 7. 风险评估与缓解措施

### 7.1 技术风险

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| Gemini API 不稳定 | 高 | 高 | 降级方案 + 多模型备份 |
| WebSocket兼容性问题 | 中 | 中 | 降级为 SSE/轮询 |
| 数据库迁移失败 | 低 | 高 | 完整备份 + 回滚脚本 |
| 前端 i18n破坏现有布局 | 中 | 低 | 渐进式迁移 + 视觉回归测试 |

### 7.2 进度风险

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| P0 任务复杂度低估 | 中 | 高 | 优先保证 P0,P1 延期可接受 |
| 测试发现重大缺陷 | 高 | 中 | 预留 3 天 buffer 时间 |
| 依赖库版本冲突 | 中 | 中 | 锁定版本号 + 虚拟环境隔离 |

### 7.3 质量风险

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| 测试覆盖率不达标 | 高 | 中 | CI强制检查 + 每日报告 |
| 性能退化 | 中 | 高 | 基准测试 + 性能预算 |
| 回归缺陷 | 高 | 中 | 自动化回归测试套件 |

---

## 8. 交付物清单

### 8.1 代码交付物

- [ ] `backend/app/services/assistant_response_formatter.py`
- [ ] `backend/app/core/error_handler.py`
- [ ] `backend/app/api/routes/assistant.py` (增强版)
- [ ] `backend/app/jobs/reminders.py` (修复版)
- [ ] `backend/app/tools/gemini.py` (增强版)
- [ ] `frontend/src/i18n.ts`
- [ ] `frontend/src/locales/en-US.json`
- [ ] `frontend/src/locales/zh-CN.json`
- [ ] `frontend/src/components/ErrorBoundary.vue`
- [ ] `frontend/src/components/SkeletonLoader.vue`
- [ ] 至少 15 个新增测试文件

### 8.2 文档交付物

- [ ] 本 IMPLEMENTATION_PLAN_V5.md
- [ ] 更新后的 API 文档（Swagger/OpenAPI）
- [ ] 错误代码字典
- [ ] 国际化术语表
- [ ] 性能基准报告

### 8.3 测试交付物

- [ ] 单元测试覆盖率报告（≥85%）
- [ ] 集成测试通过报告
- [ ] 性能测试结果
- [ ] 回归测试用例集

---

## 9. 成功标准

### 9.1 功能性标准

- ✅ 所有 P0 任务 100% 完成并通过验收测试
- ✅ P1 任务完成率 ≥90%
- ✅ P2 任务完成率 ≥70%
- ✅ 零 P0 级缺陷遗留

### 9.2 质量性标准

- ✅ 单元测试覆盖率 ≥85%
- ✅ 所有 API 响应时间 <500ms（P95）
- ✅ 前端首屏加载时间 <2s
- ✅ 无内存泄漏（压力测试验证）

### 9.3 用户体验标准

- ✅ AI 回复 100% 人类可读
- ✅ 错误提示 100% 友好明确
- ✅ 支持中英文无缝切换
- ✅ 不再出现提醒风暴

### 9.4 可维护性标准

- ✅ 结构化日志覆盖所有关键路径
- ✅ 性能监控 Dashboard 可用
- ✅ 错误追踪体系完善
- ✅ 文档完整度 ≥90%

---

## 10. 附录

### 10.1 参考资料

1. [Vue I18n 官方文档](https://vue-i18n.intlify.dev/)
2. [Loguru 最佳实践](https://loguru.readthedocs.io/)
3. [FastAPI 错误处理指南](https://fastapi.tiangolo.com/tutorial/handling-errors/)
4. [Marked.js 配置选项](https://marked.js.org/#/USING_ADVANCED.md)
5. [DOMPurify 安全实践](https://github.com/cure53/DOMPurify)

### 10.2 相关文档

- [IMPLEMENTABLE_TECHNICAL_SPEC_V2.md](IMPLEMENTABLE_TECHNICAL_SPEC_V2.md) - 原始技术规格书
- [IMPLEMENTATION_PLAN_V3.md](IMPLEMENTATION_PLAN_V3.md) - 上一版实现计划
- [IMPLEMENTATION_PLAN_V4.md](IMPLEMENTATION_PLAN_V4.md) - 跨平台扩展计划
- [TASK_BOOK.md](TASK_BOOK.md) - 毕业设计任务书

### 10.3 变更日志

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| V5.0 | 2026-04-02 | 初始版本：P0-P2优化任务 | Copilot |

---

**文档结束**
