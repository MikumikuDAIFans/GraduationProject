"""ReAct子图实现 - 嵌入LangGraph工作流的动态工具选择

Phase V7 P1-2: 当主工作流遇到复杂场景时，激活ReAct子图
让LLM自主选择工具并执行多轮推理。

设计原则：
- 最多3轮Thought-Action-Observation循环
- 工具通过注册表动态发现
- 子图输出合并到父工作流状态
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from loguru import logger

from app.workflow.state import WorkflowState


class Tool:
    """可被ReAct Agent调用的工具抽象"""
    
    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        parameters: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or {}
    
    def to_prompt_description(self) -> str:
        """生成用于prompt的工具描述"""
        desc = f"- {self.name}: {self.description}"
        if self.parameters:
            desc += f"\n  Parameters: {json.dumps(self.parameters, ensure_ascii=False)}"
        return desc


# 全局工具注册表
_tool_registry: dict[str, Tool] = {}


def register_tool(name: str, description: str, parameters: dict[str, Any] | None = None):
    """装饰器：注册工具到全局注册表"""
    def decorator(func: Callable) -> Callable:
        _tool_registry[name] = Tool(
            name=name,
            description=description,
            func=func,
            parameters=parameters,
        )
        return func
    return decorator


def get_available_tools(intent: str | None = None) -> list[Tool]:
    """根据意图过滤可用工具
    
    简单规则：某些工具只在特定意图下可用
    """
    tools = list(_tool_registry.values())
    
    # 可以根据intent过滤工具
    # 例如：如果intent不是天气相关，就不暴露天气工具
    if intent and intent not in ("event_context_advice", "schedule_guidance"):
        tools = [t for t in tools if t.name not in ("get_weather",)]
    
    return tools


def _build_react_prompt(
    *,
    user_message: str,
    intent: str,
    available_tools: list[Tool],
    current_state: dict[str, Any],
    previous_steps: list[dict[str, str]],
    max_rounds: int = 3,
) -> str:
    """构建ReAct prompt"""
    tools_desc = "\n".join(t.to_prompt_description() for t in available_tools)
    
    steps_history = ""
    for i, step in enumerate(previous_steps, 1):
        steps_history += f"Round {i}:\n"
        steps_history += f"  Thought: {step.get('thought', '')}\n"
        steps_history += f"  Action: {step.get('action', '')}\n"
        steps_history += f"  Observation: {step.get('observation', '')}\n"
    
    state_summary = json.dumps({
        "intent": intent,
        "extracted_slots": current_state.get("extracted_slots", {}),
        "weather": current_state.get("weather"),
        "traffic": current_state.get("traffic"),
        "existing_events_count": len(current_state.get("existing_events", [])),
    }, ensure_ascii=False)
    
    prompt = f"""你是一个智能调度助手，负责分析用户需求并选择合适的工具来完成任务。

## 当前状态
{state_summary}

## 用户消息
{user_message}

## 可用工具
{tools_desc if tools_desc else "无可用工具"}

## 历史步骤
{steps_history if steps_history else "无"}

## 指令
请按照以下格式进行思考：

Thought: 分析当前情况，决定下一步做什么
Action: 选择一个工具并说明参数（JSON格式）
Observation: （将由系统填充工具执行结果）

规则：
1. 最多进行 {max_rounds} 轮推理
2. 每轮只能选择一个工具
3. 如果不需要更多工具，输出 "Thought: 任务完成，无需更多操作。"
4. Action格式必须是：TOOL_NAME: {{"param1": "value1"}}

请输出你的Thought和Action（如果需要的话）："""
    
    return prompt


def _parse_llm_response(response: str) -> dict[str, str] | None:
    """解析LLM的ReAct响应"""
    thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|$)", response, re.DOTALL)
    action_match = re.search(r"Action:\s*(.+?)(?=Observation:|$)", response, re.DOTALL)
    
    if not thought_match:
        return None
    
    thought = thought_match.group(1).strip()
    
    if not action_match:
        return {"thought": thought, "action": None, "done": True}
    
    action_text = action_match.group(1).strip()
    
    # 解析工具名和参数
    if ":" in action_text:
        parts = action_text.split(":", 1)
        tool_name = parts[0].strip()
        try:
            params = json.loads(parts[1].strip())
        except json.JSONDecodeError:
            params = {"raw": parts[1].strip()}
    else:
        tool_name = action_text
        params = {}
    
    return {
        "thought": thought,
        "action": tool_name,
        "params": params,
        "done": False,
    }


async def react_subgraph(
    state: WorkflowState,
    *,
    max_rounds: int = 3,
) -> WorkflowState:
    """ReAct子图入口
    
    在复杂场景下激活，进行多轮工具选择和执行。
    返回增强后的状态，包含所有观察结果。
    """
    user_message = state.get("user_message", "")
    intent = state.get("intent", "unknown")
    
    available_tools = get_available_tools(intent=intent)
    if not available_tools:
        logger.info("ReAct subgraph: no tools available, skipping")
        return state
    
    observations: list[dict[str, Any]] = []
    previous_steps: list[dict[str, str]] = []
    
    try:
        from app.tools.gemini import GeminiClient
        gemini = GeminiClient()
    except Exception as e:
        logger.error(f"ReAct subgraph: failed to initialize Gemini: {e}")
        return state
    
    for round_num in range(max_rounds):
        logger.info(f"ReAct subgraph: round {round_num + 1}/{max_rounds}")
        
        # 构建prompt
        prompt = _build_react_prompt(
            user_message=user_message,
            intent=intent,
            available_tools=available_tools,
            current_state=state,
            previous_steps=previous_steps,
            max_rounds=max_rounds,
        )
        
        try:
            # 调用LLM
            response_text = await gemini.generate_text(prompt)
            parsed = _parse_llm_response(response_text)
            
            if not parsed:
                logger.warning(f"ReAct subgraph: failed to parse LLM response: {response_text[:100]}")
                break
            
            thought = parsed["thought"]
            
            if parsed.get("done"):
                logger.info(f"ReAct subgraph: LLM indicated task is complete after {round_num + 1} rounds")
                previous_steps.append({"thought": thought, "action": "none", "observation": "task complete"})
                break
            
            # 执行选择的工具
            action = parsed.get("action")
            params = parsed.get("params", {})
            
            if not action or action not in _tool_registry:
                logger.warning(f"ReAct subgraph: invalid action '{action}'")
                previous_steps.append({"thought": thought, "action": action or "none", "observation": "invalid action"})
                continue
            
            tool = _tool_registry[action]
            try:
                observation = await tool.func(**params)
                observation_str = json.dumps(observation, ensure_ascii=False) if isinstance(observation, dict) else str(observation)
                observations.append({"tool": action, "result": observation})
                
                # 将观察结果合并到状态
                if action == "get_weather":
                    state["weather"] = observation
                elif action == "get_traffic":
                    state["traffic"] = observation
                elif action == "query_events":
                    state["existing_events"] = observation
                
                previous_steps.append({
                    "thought": thought,
                    "action": f"{action}({json.dumps(params, ensure_ascii=False)})",
                    "observation": observation_str[:500],  # 截断过长结果
                })
            except Exception as e:
                logger.error(f"ReAct subgraph: tool '{action}' failed: {e}")
                previous_steps.append({
                    "thought": thought,
                    "action": f"{action}({json.dumps(params, ensure_ascii=False)})",
                    "observation": f"Error: {str(e)}",
                })
        
        except Exception as e:
            logger.error(f"ReAct subgraph: LLM call failed in round {round_num + 1}: {e}")
            break
    
    # 将ReAct的执行摘要存入状态
    state["react_observations"] = observations
    state["react_steps"] = previous_steps
    
    logger.info(f"ReAct subgraph completed: {len(observations)} observations, {len(previous_steps)} steps")
    return state
