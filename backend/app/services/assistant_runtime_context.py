"""Context and event-context runtime helpers for the assistant service."""

from __future__ import annotations

import asyncio
import re
from typing import Any


class AssistantContextRuntime:
    """Owns external context gathering and event-specific context enrichment."""

    def __init__(self, owner) -> None:
        self.owner = owner

    async def build_event_specific_context(
        self,
        *,
        payload: dict[str, Any],
        profile,
        user_message: str,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if not location_name and not location_coords:
            return context

        destination = location_coords or location_name
        destination_coords = location_coords
        if location_name and not destination_coords:
            try:
                geocoded = await self.owner.context_service.geocode(location_name)
                destination_coords = geocoded.location
                context["destination_coords"] = geocoded.location
            except Exception:
                destination_coords = None

        origin_name, origin_value = self.select_commute_origin(profile=profile, user_message=user_message)
        weather_location = destination_coords or getattr(profile, "home_location_coords", None)

        async def _fetch_commute():
            if origin_value and destination:
                try:
                    travel = await self.owner.context_service.estimate_travel(
                        origin=origin_value,
                        destination=destination_coords or destination,
                        mode=profile.transport_preference or "driving",
                    )
                    commute_minutes = int(round(travel.duration_minutes))
                    distance = travel.distance_km
                    if self.owner.text_runtime._prefers_chinese(user_message):
                        summary = f"从{origin_name}到{location_name or '目的地'}预计约 {commute_minutes} 分钟，路程约 {distance} 公里。"
                    else:
                        summary = f"Estimated commute from {origin_name} to {location_name or 'the destination'} is about {commute_minutes} minutes for {distance} km."
                    return {
                        "commute_minutes": commute_minutes,
                        "distance_km": distance,
                        "commute_summary": summary,
                        "origin_name": origin_name,
                    }
                except Exception:
                    pass
            return None

        async def _fetch_weather():
            if weather_location:
                try:
                    weather = await self.owner.context_service.weather_now(location=weather_location)
                    weather_text = f"{weather.text}, {weather.temp}°C"
                    if self.owner.text_runtime._prefers_chinese(user_message):
                        summary = f"{location_name or '该地点'}当前天气 {weather_text}。"
                    else:
                        summary = f"Current weather near {location_name or 'the destination'} is {weather_text}."
                    return {
                        "weather_summary": summary,
                        "weather_text": weather.text,
                        "weather_temp": weather.temp,
                    }
                except Exception:
                    pass
            return None

        commute_result, weather_result = await asyncio.gather(_fetch_commute(), _fetch_weather())

        if commute_result:
            context.update({k: v for k, v in commute_result.items() if k != "origin_name"})
        if weather_result:
            context.update(weather_result)

        advice_parts: list[str] = []
        if self.is_outdoor_request(user_message, location_name):
            weather_text = str(context.get("weather_text") or "")
            if re.search(r"雨|雪|雷|风|雾", weather_text):
                advice_parts.append("建议带伞或预留天气变化时间。" if self.owner.text_runtime._prefers_chinese(user_message) else "Consider bringing an umbrella or extra buffer for the weather.")
            else:
                advice_parts.append("如果是户外活动，当前天气看起来相对可行。" if self.owner.text_runtime._prefers_chinese(user_message) else "For an outdoor activity, the current weather looks relatively manageable.")
        elif "带伞" in user_message and context.get("weather_text"):
            weather_text = str(context.get("weather_text"))
            if re.search(r"雨|雪|雷", weather_text):
                advice_parts.append("看起来有降水风险，建议带伞。" if self.owner.text_runtime._prefers_chinese(user_message) else "There appears to be precipitation risk, so bringing an umbrella is a good idea.")
            else:
                advice_parts.append("当前天气里没有明显降水信号。" if self.owner.text_runtime._prefers_chinese(user_message) else "Current conditions do not show an obvious sign of rain.")

        if advice_parts:
            context["advice_summary"] = " ".join(advice_parts)

        return context

    def select_commute_origin(self, *, profile, user_message: str) -> tuple[str, str | None]:
        if re.search(r"从学校|下课后|从办公室|从实验室|下班后", user_message):
            if getattr(profile, "work_location_coords", None):
                return profile.work_location_name or "工作地点", profile.work_location_coords
            if getattr(profile, "work_location_name", None):
                return profile.work_location_name, profile.work_location_name

        if getattr(profile, "home_location_coords", None):
            return profile.home_location_name or "家", profile.home_location_coords
        if getattr(profile, "home_location_name", None):
            return profile.home_location_name, profile.home_location_name
        if getattr(profile, "work_location_coords", None):
            return profile.work_location_name or "工作地点", profile.work_location_coords
        if getattr(profile, "work_location_name", None):
            return profile.work_location_name, profile.work_location_name
        return "当前位置", None

    def is_outdoor_request(self, user_message: str, location_name: str | None) -> bool:
        if re.search(r"公园|操场|跑步|散步|骑行|户外|露营|打球|外面", user_message):
            return True
        if location_name and re.search(r"公园|操场|广场|校园|户外|球场", location_name):
            return True
        return False

    async def build_external_context(
        self,
        *,
        profile,
        user_message: str | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        if not self.needs_external_context(user_message=user_message, intent=intent):
            return {}

        async def _fetch_weather():
            if profile.home_location_coords:
                try:
                    weather = await self.owner.context_service.weather_now(location=profile.home_location_coords)
                    return {"temp": weather.temp, "text": weather.text, "humidity": weather.humidity}
                except Exception:
                    pass
            return None

        async def _fetch_commute():
            origin = profile.home_location_coords or profile.home_location_name
            destination = profile.work_location_coords or profile.work_location_name
            if origin and destination:
                try:
                    travel = await self.owner.context_service.estimate_travel(
                        origin=origin,
                        destination=destination,
                        mode=profile.transport_preference or "driving",
                    )
                    return {"duration_minutes": travel.duration_minutes, "distance_km": travel.distance_km}
                except Exception:
                    pass
            return None

        weather_result, commute_result = await asyncio.gather(_fetch_weather(), _fetch_commute())

        context: dict[str, Any] = {}
        if weather_result is not None:
            context["weather_now"] = weather_result
        if commute_result is not None:
            context["default_commute"] = commute_result
        return context

    def needs_external_context(
        self,
        *,
        user_message: str | None = None,
        intent: str | None = None,
    ) -> bool:
        if intent in {"event_context_advice", "create_event"}:
            return True
        if intent == "schedule_guidance":
            return True
        if intent == "progress_followup":
            return False

        if user_message:
            needs_weather = bool(re.search(r"天气|气温|温度|冷|热|下雨|下雪|weather|temperature", user_message, re.I))
            needs_commute = bool(re.search(r"通勤|出发|多久到|多远|路程|路线|怎么去|commute|how long.*get|travel time", user_message, re.I))
            needs_location = bool(re.search(r"在哪里|地址|位置|地点|where|address|location", user_message, re.I))
            if needs_weather or needs_commute or needs_location:
                return True

        return user_message is not None
