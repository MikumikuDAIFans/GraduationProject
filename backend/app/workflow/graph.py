"""LangGraph工作流图定义"""

import logging
from typing import Literal

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

from app.workflow.state import WorkflowState
from app.workflow.nodes import WorkflowNodes

logger = logging.getLogger(__name__)


def build_assistant_graph(nodes: WorkflowNodes):
    """构建助手工作流图
    
    LangGraph++工作流：
    parse_intent → collect_context → schedule_decision → [execute_react_subgraph | execute_tools | clarify] → render_response → END
    
    Phase V7 P1-2: 增加execute_react_subgraph节点，支持复杂场景下的动态工具选择。
    """
    if not HAS_LANGGRAPH:
        logger.warning("LangGraph not installed, falling back to sequential execution")
        return None
    
    graph = StateGraph(WorkflowState)
    
    # 添加节点
    graph.add_node("parse_intent", nodes.parse_intent)
    graph.add_node("collect_context", nodes.collect_context)
    graph.add_node("schedule_decision", nodes.schedule_decision)
    graph.add_node("execute_react_subgraph", nodes.execute_react_subgraph)
    graph.add_node("execute_tools", nodes.execute_tools)
    graph.add_node("clarify_and_retry", nodes.clarify_and_retry)
    graph.add_node("render_response", nodes.render_response)
    
    # 设置入口点
    graph.set_entry_point("parse_intent")
    
    # 添加边
    graph.add_edge("parse_intent", "collect_context")
    graph.add_edge("collect_context", "schedule_decision")
    
    # Phase V7 P1-2: 条件边 - 调度决策后根据情况路由
    graph.add_conditional_edges(
        "schedule_decision",
        route_after_decision,
        {
            "react": "execute_react_subgraph",
            "execute": "execute_tools",
            "clarify": "clarify_and_retry",
            "render": "render_response",
        }
    )
    
    # ReAct执行完后渲染回复
    graph.add_edge("execute_react_subgraph", "render_response")
    
    # 执行工具后渲染回复
    graph.add_edge("execute_tools", "render_response")
    
    # 澄清后也渲染回复
    graph.add_edge("clarify_and_retry", "render_response")
    
    # 渲染回复后结束
    graph.add_edge("render_response", END)
    
    return graph.compile()


def route_after_decision(state: WorkflowState) -> Literal["react", "execute", "clarify", "render"]:
    """调度决策后的路由逻辑
    
    Phase V7 P1-2: 优先检查是否需要ReAct子图。
    """
    # Phase V7: 如果需要ReAct子图，优先走ReAct分支
    if state.get("use_react"):
        return "react"
    
    # 如果需要澄清，走澄清分支
    if state.get("needs_clarification"):
        return "clarify"
    
    # 如果有动作需要执行，走执行分支
    if state.get("actions"):
        return "execute"
    
    # 否则直接渲染回复
    return "render"


async def run_workflow(graph, initial_state: dict) -> WorkflowState:
    """运行工作流
    
    Args:
        graph: 编译后的LangGraph图
        initial_state: 初始状态字典
    
    Returns:
        最终工作流状态
    """
    if graph is None:
        # Fallback: 顺序执行节点
        return await run_sequential(initial_state)
    
    # 运行LangGraph
    final_state = await graph.ainvoke(initial_state)
    return final_state


async def run_sequential(initial_state: dict) -> WorkflowState:
    """顺序执行节点（LangGraph不可用时的降级方案）
    
    Phase V7 P1-2: 增加ReAct子图支持。
    """
    nodes = WorkflowNodes()
    
    state = WorkflowState(**initial_state)
    state = await nodes.parse_intent(state)
    state = await nodes.collect_context(state)
    state = await nodes.schedule_decision(state)
    
    # 路由决策
    route = route_after_decision(state)
    if route == "react":
        state = await nodes.execute_react_subgraph(state)
    elif route == "execute":
        state = await nodes.execute_tools(state)
    elif route == "clarify":
        state = await nodes.clarify_and_retry(state)
    
    state = await nodes.render_response(state)
    
    return state
