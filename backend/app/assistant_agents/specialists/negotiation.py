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
            state.reply = self.format_proposals(state.proposals, state=state)
        return state

    def format_proposals(self, proposals: list[ProposalDraft], *, state: ConductorState | None = None) -> str:
        orchestration = state.understanding.orchestration if state and state.understanding else None
        if orchestration and orchestration.proposal_shape == "task_schedule_plan":
            if state is not None:
                state.metadata["proposal_reply_source"] = "orchestration"
            return self._format_task_schedule_plan(proposals, target_label=orchestration.target_scope.label)
        if orchestration and orchestration.proposal_shape == "event_reschedule":
            if state is not None:
                state.metadata["proposal_reply_source"] = "orchestration"
            return self._format_event_reschedule(proposals, target_label=orchestration.target_scope.label)
        if orchestration and orchestration.proposal_shape == "event_creation":
            if state is not None:
                state.metadata["proposal_reply_source"] = "orchestration"
            return self._format_event_creation(proposals, target_label=orchestration.target_scope.label)
        if orchestration and orchestration.proposal_shape == "task_creation":
            if state is not None:
                state.metadata["proposal_reply_source"] = "orchestration"
            return self._format_task_creation(proposals, target_label=orchestration.target_scope.label)
        if orchestration and orchestration.proposal_shape in {
            "event_cancel",
            "event_status_update",
            "event_batch_cancel",
            "event_batch_reschedule",
            "task_status_update",
        }:
            if state is not None:
                state.metadata["proposal_reply_source"] = "orchestration"
            return self._format_update_proposal(
                proposals,
                proposal_shape=orchestration.proposal_shape,
                target_label=orchestration.target_scope.label,
            )

        prefix = "我先给你一个可确认的方案（现在不会直接写入日程/任务）："
        if len(proposals) > 1:
            prefix = "我先给你几个可确认的方案（现在不会直接写入日程/任务）："
        lines = [prefix]
        lines.extend(self._format_proposal_lines(proposals))
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _format_task_schedule_plan(self, proposals: list[ProposalDraft], *, target_label: str | None) -> str:
        target = target_label or (proposals[0].related_task_id if proposals else None) or "当前任务"
        lines = [f"我先把“{target}”整理成可确认的任务排程方案（确认前不会写入日程）："]
        lines.extend(self._format_proposal_lines(proposals))
        lines.append("确认后我才会创建这些专注时段；如果要改日期、时间或拆分方式，直接告诉我修改点。")
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _format_event_reschedule(self, proposals: list[ProposalDraft], *, target_label: str | None) -> str:
        target = target_label or (proposals[0].related_event_id if proposals else None) or "这个日程"
        lines = [f"我先把“{target}”整理成可确认的改期方案（确认前不会修改日程）："]
        lines.extend(self._format_proposal_lines(proposals))
        lines.append("确认后我才会改动原日程；如果时间不合适，直接告诉我新的日期或时间段。")
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _format_event_creation(self, proposals: list[ProposalDraft], *, target_label: str | None) -> str:
        target = target_label or "这个日程"
        lines = [f"我先把“{target}”整理成可确认的新日程方案（现在不会直接写入日程）："]
        lines.extend(self._format_proposal_lines(proposals))
        if self._has_default_duration_assumption(proposals):
            lines.append("未说明结束时间时，我会默认1小时；确认前你仍然可以修改开始时间、结束时间或持续时长。")
        lines.append("确认后我才会创建日程；如果标题、时间、地点要改，直接告诉我修改点。")
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _format_task_creation(self, proposals: list[ProposalDraft], *, target_label: str | None) -> str:
        target = target_label or "这个任务"
        lines = [f"我先把“{target}”整理成可确认的新任务方案（现在不会直接写入任务）："]
        lines.extend(self._format_proposal_lines(proposals))
        lines.append("确认后我才会创建任务；如果要补截止时间、优先级或拆分方式，直接告诉我。")
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _format_update_proposal(
        self,
        proposals: list[ProposalDraft],
        *,
        proposal_shape: str,
        target_label: str | None,
    ) -> str:
        label = target_label or self._update_target_label(proposals)
        shape_labels = {
            "event_cancel": "取消日程方案",
            "event_status_update": "日程状态更新方案",
            "event_batch_cancel": "批量取消日程方案",
            "event_batch_reschedule": "批量改期方案",
            "task_status_update": "任务状态更新方案",
        }
        domain = "任务" if proposal_shape == "task_status_update" else "日程"
        title = shape_labels.get(proposal_shape, "更新方案")
        lines = [f"我先把“{label}”整理成可确认的{title}（确认前不会修改{domain}）："]
        lines.extend(self._format_proposal_lines(proposals))
        lines.append(f"确认后我才会执行这次{title}；如果目标或规则不对，直接告诉我修改点。")
        lines.extend(self._format_protocol_tail(proposals))
        return "\n".join(lines)

    def _update_target_label(self, proposals: list[ProposalDraft]) -> str:
        if not proposals:
            return "当前目标"
        proposal = proposals[0]
        payload = proposal.payload_json or {}
        if payload.get("target_date"):
            return str(payload["target_date"])
        if payload.get("target_title"):
            return str(payload["target_title"])
        if proposal.related_task_id is not None:
            return f"任务 {proposal.related_task_id}"
        if proposal.related_event_id is not None:
            return f"日程 {proposal.related_event_id}"
        return "当前目标"

    def _format_proposal_lines(self, proposals: list[ProposalDraft]) -> list[str]:
        lines: list[str] = []
        for index, proposal in enumerate(proposals, start=1):
            display_id = proposal.display_id or f"P{index}"
            lines.append(f"{display_id}：{proposal.summary}")
            for option in proposal.options:
                option_line = f"  方案 {option.option_id}：{option.summary}"
                if option.rationale:
                    option_line += f"（{option.rationale}）"
                lines.append(option_line)
        return lines

    def _has_default_duration_assumption(self, proposals: list[ProposalDraft]) -> bool:
        for proposal in proposals:
            assumptions = proposal.payload_json.get("assumptions") if isinstance(proposal.payload_json, dict) else None
            if isinstance(assumptions, list) and "default_event_duration_60_minutes" in assumptions:
                return True
            for option in proposal.options:
                if option.rationale and ("1 小时" in option.rationale or "默认1小时" in option.rationale):
                    return True
        return False

    def _format_protocol_tail(self, proposals: list[ProposalDraft]) -> list[str]:
        if not proposals:
            return [
                "推荐：先补充关键信息后再生成方案。",
                "原因：当前没有足够信息形成可执行写入。",
                "可回复示例：接受：确认 P1 方案A；修改：把 P1 改到4点开始；拒绝：P1 先不要安排。",
            ]

        primary = proposals[0]
        primary_id = primary.display_id or "P1"
        recommended_option_id = primary.recommended_option_id or (primary.options[0].option_id if primary.options else "A")
        recommended_option = next(
            (option for option in primary.options if option.option_id == recommended_option_id),
            primary.options[0] if primary.options else None,
        )
        reason = (
            recommended_option.rationale
            if recommended_option is not None and recommended_option.rationale
            else "它是基于当前信息最完整、风险最低的可执行方案。"
        )
        return [
            f"推荐：优先采用 {primary_id} 方案{recommended_option_id}。",
            f"原因：{reason}",
            f"可回复示例：接受：确认 {primary_id} 方案{recommended_option_id}；修改：把 {primary_id} 改到4点开始；拒绝：{primary_id} 先不要安排。",
        ]
