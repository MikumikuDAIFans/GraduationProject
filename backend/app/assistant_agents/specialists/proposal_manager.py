"""Proposal draft preparation specialist."""

from __future__ import annotations

import hashlib
import json

from app.assistant_agents.contracts import AssistantAgentContext, ConductorState


class ProposalManagerSpecialist:
    """Prepare proposal drafts for later persistence without writing them."""

    name = "proposal_manager"

    async def run(self, context: AssistantAgentContext, state: ConductorState) -> ConductorState:
        create_payloads: list[dict] = []
        for index, proposal in enumerate(state.proposals, start=1):
            proposal.display_id = f"P{index}"
            proposal.dedup_key = proposal.dedup_key or self._dedup_key(context, proposal.to_payload())
            payload = proposal.to_payload()
            payload["session_id"] = context.session_id
            payload["trigger_type"] = "user_message"
            create_payloads.append(payload)
        state.metadata["proposal_create_payloads"] = create_payloads
        return state

    def _dedup_key(self, context: AssistantAgentContext, payload: dict) -> str:
        raw = json.dumps(
            {
                "user_id": context.user_id,
                "session_id": context.session_id,
                "message": context.user_message,
                "proposal_type": payload.get("proposal_type"),
                "options": payload.get("payload_json", {}).get("options", []),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return "proposal:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()
