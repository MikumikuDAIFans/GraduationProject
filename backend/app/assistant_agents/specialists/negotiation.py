"""Negotiation specialist that turns drafts into text-first replies."""

from __future__ import annotations

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState, ProposalDraft


class NegotiationSpecialist:
    name = "negotiation"

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        del context
        if state.clarification_question:
            state.reply = state.clarification_question
            return state
        if state.proposals:
            state.reply = self.format_proposals(state.proposals)
        return state

    def format_proposals(self, proposals: list[ProposalDraft]) -> str:
        prefix = "我先给你一个可确认的方案（现在不会直接写入日程/任务）："
        if len(proposals) > 1:
            prefix = "我先给你几个可确认的方案（现在不会直接写入日程/任务）："
        lines = [prefix]
        for index, proposal in enumerate(proposals, start=1):
            display_id = proposal.display_id or f"P{index}"
            lines.append(f"{display_id}：{proposal.summary}")
            for option in proposal.options:
                option_line = f"  方案 {option.option_id}：{option.summary}"
                if option.rationale:
                    option_line += f"（{option.rationale}）"
                lines.append(option_line)
        lines.append("如果认可，请回复类似“确认 P1 方案A”；如果想改，直接告诉我修改点。")
        return "\n".join(lines)
