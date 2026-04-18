"""LangGraph工作流状态定义"""

from typing import TypedDict, Optional, Any


class WorkflowState(TypedDict, total=False):
    """工作流状态
    
    使用total=False允许部分字段在初始状态下不存在，
    各节点逐步填充状态。
    """
    # 输入
    user_message: str
    user_id: str
    session_id: str
    history: list
    profile: Any
    external_context: dict
    
    # 意图解析结果
    intent: Optional[str]
    extracted_slots: dict
    confidence: float
    
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
    
    # 控制流
    needs_clarification: bool
    clarification_question: Optional[str]
    retry_count: int
    
    # Phase V7 P1-2: ReAct子图状态
    # 是否激活ReAct子图
    use_react: bool
    # ReAct观察结果列表
    react_observations: list
    # ReAct执行步骤记录
    react_steps: list

    # Runtime-only helpers
    assistant_service: Any
