"""ReAct工具注册 - 声明可供ReAct Agent使用的工具

Phase V7 P1-2: 将现有服务包装为ReAct可调用的工具。
工具通过@register_tool装饰器自动注册到全局工具表。
"""

from __future__ import annotations

from loguru import logger

from app.workflow.react_subgraph import register_tool


@register_tool(
    name="get_weather",
    description="获取指定地点的当前天气信息。适用于需要判断是否适合户外活动或出行时调用。",
    parameters={
        "location": {"type": "string", "description": "地点名称或坐标，如'上海'或'31.23,121.47'"},
    },
)
async def get_weather(location: str) -> dict:
    """获取指定地点的当前天气"""
    try:
        from app.services.context import ContextService
        ctx = ContextService()
        weather = await ctx.weather_now(location=location)
        return {
            "location": location,
            "text": weather.text,
            "temp": weather.temp,
            "humidity": weather.humidity,
        }
    except Exception as e:
        logger.error(f"get_weather tool failed: {e}")
        return {"error": str(e)}


@register_tool(
    name="get_traffic",
    description="估算两点之间的通勤时间和距离。适用于规划日程或判断出发时间时调用。",
    parameters={
        "origin": {"type": "string", "description": "起点名称或坐标"},
        "destination": {"type": "string", "description": "终点名称或坐标"},
        "mode": {"type": "string", "description": "出行方式：driving/transit/walking", "default": "driving"},
    },
)
async def get_traffic(origin: str, destination: str, mode: str = "driving") -> dict:
    """估算两点之间的通勤时间和距离"""
    try:
        from app.services.context import ContextService
        ctx = ContextService()
        travel = await ctx.estimate_travel(origin=origin, destination=destination, mode=mode)
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "duration_minutes": travel.duration_minutes,
            "distance_km": travel.distance_km,
        }
    except Exception as e:
        logger.error(f"get_traffic tool failed: {e}")
        return {"error": str(e)}


@register_tool(
    name="query_events",
    description="查询用户在指定时间范围内的事件/日程。适用于判断时间冲突或查找空闲时段时调用。",
    parameters={
        "user_id": {"type": "string", "description": "用户ID"},
        "date": {"type": "string", "description": "日期，格式YYYY-MM-DD"},
    },
)
async def query_events(user_id: str, date: str) -> list[dict]:
    """查询用户在指定日期的事件"""
    try:
        from datetime import datetime, timedelta
        from app.repositories.events import EventRepository
        
        # 计算日期范围
        dt_start = datetime.fromisoformat(date)
        dt_end = dt_start + timedelta(days=1)
        
        repo = EventRepository()
        events = await repo.list_events(user_id=user_id, limit=100)
        
        # 过滤指定日期的事件
        day_events = [
            e for e in events
            if e.start_time and dt_start <= e.start_time < dt_end
        ]
        
        return [
            {
                "id": e.id,
                "title": e.title,
                "start_time": e.start_time.isoformat() if e.start_time else None,
                "end_time": e.end_time.isoformat() if e.end_time else None,
                "location": e.location_name,
            }
            for e in day_events
        ]
    except Exception as e:
        logger.error(f"query_events tool failed: {e}")
        return []
