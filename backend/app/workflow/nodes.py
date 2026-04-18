"""LangGraph工作流节点实现"""

import asyncio
import logging
import re
from typing import Optional

from app.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


class WorkflowNodes:
    """工作流节点实现
    
    每个节点接收当前状态，返回更新后的状态。
    节点应该是纯函数（或异步纯函数），便于测试和调试。
    """
    
    def __init__(
        self,
        intent_parser=None,
        event_service=None,
        task_service=None,
        habit_retriever=None,
        conflict_detector=None,
        weather_service=None,
        maps_service=None,
        dialog_manager=None,
        response_formatter=None,
    ):
        self.intent_parser = intent_parser
        self.event_service = event_service
        self.task_service = task_service
        self.habit_retriever = habit_retriever
        self.conflict_detector = conflict_detector
        self.weather_service = weather_service
        self.maps_service = maps_service
        self.dialog_manager = dialog_manager
        self.response_formatter = response_formatter
    
    @staticmethod
    def _needs_weather(intent: str, user_message: str = "") -> bool:
        """判断是否需要天气上下文"""
        if intent in ("event_context_advice", "schedule_guidance"):
            return True
        if user_message and re.search(r"天气|气温|温度|冷|热|下雨|下雪|weather", user_message, re.I):
            return True
        return False
    
    @staticmethod
    def _needs_traffic(intent: str, user_message: str = "") -> bool:
        """判断是否需要交通上下文"""
        if intent in ("schedule_guidance", "event_context_advice"):
            return True
        if user_message and re.search(r"通勤|出发|多久到|多远|路程|路线|怎么去|traffic|commute", user_message, re.I):
            return True
        return False
    
    @staticmethod
    def _needs_events(intent: str) -> bool:
        """判断是否需要事件上下文"""
        return intent in ("create_event", "query_events", "schedule_guidance", "event_context_advice", "progress_followup")
    
    @staticmethod
    def _needs_tasks(intent: str) -> bool:
        """判断是否需要任务上下文"""
        return intent in ("create_task", "query_tasks", "schedule_guidance", "progress_followup")
    
    @staticmethod
    def _needs_habits(intent: str) -> bool:
        """判断是否需要习惯上下文"""
        return intent in ("schedule_guidance", "create_event")
    
    @staticmethod
    async def parse_intent(state: WorkflowState) -> WorkflowState:
        """意图识别节点
        
        将用户消息解析为结构化意图和槽位。
        """
        try:
            from app.services.enhanced_assistant import EnhancedIntentParser
            
            parser = EnhancedIntentParser()
            result = await parser.parse_with_context(
                state.get("user_message", ""),
                state.get("user_id", "")
            )
            
            state["intent"] = result.intent
            state["extracted_slots"] = result.slots
            state["confidence"] = result.confidence
            
        except Exception as e:
            logger.error(f"Intent parsing failed: {e}")
            state["intent"] = "unknown"
            state["extracted_slots"] = {}
            state["confidence"] = 0.0
        
        return state
    
    @staticmethod
    async def collect_context(state: WorkflowState) -> WorkflowState:
        """上下文收集节点（Phase V7 P1-1: 条件化收集）
        
        根据意图和槽位，按需收集相关的上下文信息。
        不再无条件收集所有上下文。
        """
        user_id = state.get("user_id", "")
        intent = state.get("intent", "unknown")
        slots = state.get("extracted_slots", {})
        user_message = state.get("user_message", "")
        
        # Phase V7 P1-1: Collect context in parallel, but only when needed
        async def _fetch_events():
            if not WorkflowNodes._needs_events(intent):
                return []
            if state.get("event_service"):
                time_range = slots.get("time_range", "today")
                events = await state["event_service"].get_relevant_events(user_id, time_range)
                return events or []
            return []
        
        async def _fetch_tasks():
            if not WorkflowNodes._needs_tasks(intent):
                return []
            if state.get("task_service"):
                tasks = await state["task_service"].get_active_tasks(user_id)
                return tasks or []
            return []
        
        async def _fetch_habits():
            if not WorkflowNodes._needs_habits(intent):
                return []
            if state.get("habit_retriever"):
                activity = slots.get("activity", "")
                if activity:
                    habits = await state["habit_retriever"].get_relevant_habits(activity)
                    return habits or []
            return []
        
        async def _fetch_weather():
            if not WorkflowNodes._needs_weather(intent, user_message):
                return None
            location = slots.get("location")
            if location and state.get("weather_service"):
                try:
                    weather = await state["weather_service"].get_weather(location)
                    return weather
                except Exception as e:
                    logger.warning(f"Weather fetch failed: {e}")
            return None
        
        async def _fetch_traffic():
            if not WorkflowNodes._needs_traffic(intent, user_message):
                return None
            location = slots.get("location")
            if location and state.get("maps_service"):
                try:
                    traffic = await state["maps_service"].estimate_travel_time(user_id, location)
                    return traffic
                except Exception as e:
                    logger.warning(f"Traffic fetch failed: {e}")
            return None
        
        # Execute all fetches in parallel
        try:
            events_result, tasks_result, habits_result, weather_result, traffic_result = await asyncio.gather(
                _fetch_events(),
                _fetch_tasks(),
                _fetch_habits(),
                _fetch_weather(),
                _fetch_traffic(),
            )
            
            state["existing_events"] = events_result
            state["existing_tasks"] = tasks_result
            state["habits"] = habits_result
            state["weather"] = weather_result
            state["traffic"] = traffic_result
                
        except Exception as e:
            logger.error(f"Context collection failed: {e}")
            state.setdefault("existing_events", [])
            state.setdefault("existing_tasks", [])
            state.setdefault("habits", [])
        
        return state
    
    @staticmethod
    async def schedule_decision(state: WorkflowState) -> WorkflowState:
        """调度决策节点
        
        根据意图和上下文，决定如何调度事件/任务。
        Phase V7 P1-3: 增加LLM驱动的路由决策，判断是否需要激活ReAct子图。
        """
        intent = state.get("intent", "")
        slots = state.get("extracted_slots", {})
        existing_events = state.get("existing_events", [])
        
        try:
            if intent == "create_event" and state.get("conflict_detector"):
                # 检测冲突
                new_event = slots.get("new_event", {})
                if new_event:
                    conflicts = state["conflict_detector"].detect_conflicts(
                        existing_events + [new_event]
                    )
                    state["conflicts"] = conflicts or []
                    
                    # 如果有冲突，生成替代建议
                    if conflicts:
                        alternatives = state["conflict_detector"].suggest_alternatives(
                            new_event,
                            existing_events
                        )
                        state["suggestions"] = alternatives or []
            
            elif intent == "create_task" and state.get("task_service"):
                # 任务创建决策
                task_payload = slots.get("task", {})
                if task_payload:
                    state["actions"] = [{
                        "type": "create_task",
                        "payload": task_payload
                    }]
            
            # Phase V7 P1-3: 判断是否需要激活ReAct子图
            state["use_react"] = WorkflowNodes._should_use_react(
                intent=intent,
                slots=slots,
                user_message=state.get("user_message", ""),
            )
            
        except Exception as e:
            logger.error(f"Schedule decision failed: {e}")
            state.setdefault("conflicts", [])
            state.setdefault("suggestions", [])
            state["use_react"] = False
        
        return state
    
    @staticmethod
    def _should_use_react(*, intent: str, slots: dict, user_message: str) -> bool:
        """判断是否需要激活ReAct子图
        
        Phase V7 P1-3: 基于规则的判断，未来可替换为LLM分类器。
        """
        # 复杂调度场景：多个事件需要协调安排
        if intent == "schedule_guidance":
            num_events = len(slots.get("events", []))
            if num_events >= 2:
                return True
        
        # 天气敏感 + 需要通勤判断的复合场景
        if intent == "event_context_advice":
            has_location = bool(slots.get("location"))
            has_time = bool(slots.get("time_range"))
            if has_location and has_time:
                return True
        
        # 用户明确要求详细分析
        if re.search(r"详细|仔细|全面分析|deep|analyze|compare", user_message, re.I):
            return True
        
        return False
    
    @staticmethod
    async def execute_react_subgraph(state: WorkflowState) -> WorkflowState:
        """ReAct子图节点
        
        Phase V7 P1-2: 当需要复杂推理时，激活ReAct子图进行多轮工具选择。
        """
        if not state.get("use_react"):
            logger.info("ReAct subgraph not needed, skipping")
            return state
        
        logger.info("Activating ReAct subgraph for complex reasoning")
        
        try:
            # 导入工具注册表（触发装饰器注册）
            import app.workflow.react_tools  # noqa: F401
            from app.workflow.react_subgraph import react_subgraph
            
            state = await react_subgraph(state, max_rounds=3)
        except Exception as e:
            logger.error(f"ReAct subgraph failed: {e}")
            state.setdefault("react_observations", [])
            state.setdefault("react_steps", [])
        
        return state
    
    @staticmethod
    async def execute_tools(state: WorkflowState) -> WorkflowState:
        """工具执行节点
        
        执行具体的动作（创建事件、任务等）。
        """
        actions = state.get("actions", [])
        
        try:
            for action in actions:
                action_type = action.get("type", "")
                payload = action.get("payload", {})
                
                if action_type == "create_event" and state.get("event_service"):
                    await state["event_service"].create_event(payload)
                    
                elif action_type == "create_task" and state.get("task_service"):
                    await state["task_service"].create_task(payload)
                    
                elif action_type == "update_event" and state.get("event_service"):
                    await state["event_service"].update_event(payload)
                    
                elif action_type == "delete_event" and state.get("event_service"):
                    await state["event_service"].delete_event(payload.get("event_id"))
                    
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            state["reply"] = f"执行操作时出错：{str(e)}"
        
        return state
    
    @staticmethod
    async def render_response(state: WorkflowState) -> WorkflowState:
        """回复渲染节点
        
        根据工作流结果生成自然语言回复。
        """
        try:
            intent = state.get("intent", "")
            actions = state.get("actions", [])
            conflicts = state.get("conflicts", [])
            suggestions = state.get("suggestions", [])
            habits = state.get("habits", [])
            
            # 如果需要澄清
            if state.get("needs_clarification"):
                state["reply"] = state.get(
                    "clarification_question",
                    "我需要更多信息来帮助你。"
                )
                return state
            
            # 构建回复
            reply_parts = []
            
            # 确认操作
            if actions:
                action_descriptions = []
                for action in actions:
                    action_type = action.get("type", "")
                    if action_type == "create_event":
                        title = action.get("payload", {}).get("title", "事件")
                        action_descriptions.append(f"已创建事件：{title}")
                    elif action_type == "create_task":
                        title = action.get("payload", {}).get("title", "任务")
                        action_descriptions.append(f"已创建任务：{title}")
                
                if action_descriptions:
                    reply_parts.append("\n".join(action_descriptions))
            
            # 冲突警告
            if conflicts:
                conflict_msg = f"⚠️ 检测到 {len(conflicts)} 个时间冲突"
                reply_parts.append(conflict_msg)
                
                if suggestions:
                    suggestion_msg = "建议的替代时间：\n" + "\n".join(
                        f"- {s.get('time', '')}: {s.get('reason', '')}"
                        for s in suggestions[:3]
                    )
                    reply_parts.append(suggestion_msg)
            
            # 习惯提示
            if habits:
                habit_msg = "💡 根据你的习惯："
                for habit in habits[:2]:
                    desc = habit.get("description", "")
                    if desc:
                        habit_msg += f"\n- {desc}"
                reply_parts.append(habit_msg)
            
            # 默认回复
            if not reply_parts:
                if intent == "query_events":
                    reply_parts.append("已为你查询相关事件。")
                elif intent == "create_event":
                    reply_parts.append("事件创建成功！")
                else:
                    reply_parts.append("已完成你的请求。")
            
            state["reply"] = "\n\n".join(reply_parts)
            
        except Exception as e:
            logger.error(f"Response rendering failed: {e}")
            state["reply"] = "抱歉，处理你的请求时出现了问题。"
        
        return state
    
    @staticmethod
    async def clarify_and_retry(state: WorkflowState) -> WorkflowState:
        """澄清并重试节点
        
        当信息不足时，向用户发起澄清问题。
        """
        if state.get("needs_clarification"):
            slot_name = state.get("clarification_question", "")
            state["reply"] = f"请问{slot_name}是什么？"
            state["retry_count"] = state.get("retry_count", 0) + 1
        
        return state
