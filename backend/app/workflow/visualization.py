"""工作流可视化工具

Phase V7 P3: 提供工作流的 Mermaid 图表生成能力。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_workflow_diagram(include_react: bool = True) -> str:
    """生成工作流的 Mermaid 图表

    Args:
        include_react: 是否包含ReAct子图分支

    Returns:
        Mermaid流程图字符串
    """
    base = """graph TD
    START([START]) --> parse_intent[解析意图]
    parse_intent --> collect_context[收集上下文]
    collect_context --> schedule_decision[调度决策]
    
    schedule_decision -->|需要澄清| clarify[澄清提问]
    schedule_decision -->|需要执行| execute[执行工具]
    schedule_decision -->|无需操作| render[渲染回复]
"""
    
    if include_react:
        base += """
    schedule_decision -->|复杂场景| react[ReAct子图]
    react -->|最多3轮推理| render
    
    subgraph ReAct子图
        direction TB
        react_thought[Thought: 思考]
        react_action[Action: 选择工具]
        react_observe[Observation: 观察结果]
        react_done{是否完成?}
        
        react_thought --> react_action
        react_action --> react_observe
        react_observe --> react_done
        react_done -->|否| react_thought
        react_done -->|是| render
    end
"""
    
    base += """
    clarify --> render
    execute --> render
    render --> END([END])
    
    style START fill:#4CAF50,color:white
    style END fill:#F44336,color:white
    style parse_intent fill:#2196F3,color:white
    style collect_context fill:#2196F3,color:white
    style schedule_decision fill:#FF9800,color:white
    style react fill:#9C27B0,color:white
    style execute fill:#4CAF50,color:white
    style clarify fill:#FF5722,color:white
    style render fill:#607D8B,color:white
"""
    
    return base


def generate_node_responsibility_table() -> list[dict[str, str]]:
    """生成节点职责对照表

    Returns:
        列表，每个字典包含node、responsibility、outputs字段
    """
    return [
        {
            "node": "parse_intent",
            "responsibility": "意图识别 + 槽位提取",
            "outputs": "intent, confidence, extracted_slots",
        },
        {
            "node": "collect_context",
            "responsibility": "条件化上下文收集",
            "outputs": "weather, traffic, events, tasks, habits",
        },
        {
            "node": "schedule_decision",
            "responsibility": "调度决策 + ReAct路由判断",
            "outputs": "conflicts, suggestions, actions, use_react",
        },
        {
            "node": "execute_react_subgraph",
            "responsibility": "ReAct多轮推理（最多3轮）",
            "outputs": "react_observations, react_steps",
        },
        {
            "node": "execute_tools",
            "responsibility": "执行预定义工具链",
            "outputs": "tool_results",
        },
        {
            "node": "clarify_and_retry",
            "responsibility": "生成澄清问题",
            "outputs": "clarification_question",
        },
        {
            "node": "render_response",
            "responsibility": "模板渲染 + 回复生成",
            "outputs": "response",
        },
    ]


def print_workflow_summary() -> None:
    """打印工作流摘要信息"""
    table = generate_node_responsibility_table()
    
    print("=" * 60)
    print("MA-IPAAS LangGraph++ 工作流摘要 (Phase V7)")
    print("=" * 60)
    print()
    
    print("节点职责:")
    print("-" * 60)
    for row in table:
        print(f"  {row['node']:<25} {row['responsibility']}")
        print(f"  {'':25} 输出: {row['outputs']}")
        print()
    
    print("=" * 60)
    print("Mermaid图表:")
    print("=" * 60)
    print(generate_workflow_diagram())
