"""Specialist registry used by the assistant conductor."""

from __future__ import annotations

from app.assistant_agents.contracts import AssistantAgentContext, AssistantSpecialist, ConductorState


class SpecialistRegistry:
    """Small pluggable registry for assistant specialists."""

    def __init__(self) -> None:
        self._specialists: dict[str, AssistantSpecialist] = {}

    def register(self, specialist: AssistantSpecialist) -> None:
        if not specialist.name:
            raise ValueError("specialist name cannot be empty")
        if specialist.name in self._specialists:
            raise ValueError(f"specialist already registered: {specialist.name}")
        self._specialists[specialist.name] = specialist

    def get(self, name: str) -> AssistantSpecialist:
        try:
            return self._specialists[name]
        except KeyError as exc:
            raise KeyError(f"specialist not registered: {name}") from exc

    def names(self) -> list[str]:
        return list(self._specialists)

    async def run(self, name: str, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        return await self.get(name).run(context, state)
