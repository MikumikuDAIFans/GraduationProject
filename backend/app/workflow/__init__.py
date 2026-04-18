"""LangGraph工作流引擎模块

Phase V7: LangGraph++架构 - 核心工作流引擎 + 条件化上下文收集 + ReAct子图
"""

from app.workflow.state import WorkflowState
from app.workflow.nodes import WorkflowNodes
from app.workflow.graph import build_assistant_graph, run_workflow, run_sequential
from app.workflow.prompts import (
    INTENT_DETECTION_TEMPLATE,
    SLOT_FILLING_TEMPLATE,
    CONFLICT_EXPLANATION_TEMPLATE,
    HABIT_HINT_TEMPLATE,
    RESPONSE_RENDER_TEMPLATE,
)
from app.workflow.react_subgraph import (
    Tool,
    register_tool,
    get_available_tools,
    react_subgraph,
)
from app.workflow.react_tools import get_weather, get_traffic, query_events
from app.workflow.visualization import (
    generate_workflow_diagram,
    generate_node_responsibility_table,
    print_workflow_summary,
)

__all__ = [
    "WorkflowState",
    "WorkflowNodes",
    "build_assistant_graph",
    "run_workflow",
    "run_sequential",
    "INTENT_DETECTION_TEMPLATE",
    "SLOT_FILLING_TEMPLATE",
    "CONFLICT_EXPLANATION_TEMPLATE",
    "HABIT_HINT_TEMPLATE",
    "RESPONSE_RENDER_TEMPLATE",
    # Phase V7 P1-2: ReAct子图
    "Tool",
    "register_tool",
    "get_available_tools",
    "react_subgraph",
    "get_weather",
    "get_traffic",
    "query_events",
    # Phase V7 P3: 工作流可视化
    "generate_workflow_diagram",
    "generate_node_responsibility_table",
    "print_workflow_summary",
]
