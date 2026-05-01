from __future__ import annotations

from app.assistant_agents.contracts import ProposalDraft, ProposalOptionDraft
from app.assistant_agents.specialists.negotiation import NegotiationSpecialist


def test_negotiation_text_labels_multiple_proposals() -> None:
    proposals = [
        ProposalDraft(
            proposal_type="event_creation",
            summary="建议创建日程 A",
            display_id="P1",
            options=[ProposalOptionDraft(option_id="A", title="创建", summary="明天 15:00-16:00")],
        ),
        ProposalDraft(
            proposal_type="task_creation",
            summary="建议创建任务 B",
            display_id="P2",
            options=[ProposalOptionDraft(option_id="A", title="创建", summary="进入待排程")],
        ),
    ]

    text = NegotiationSpecialist().format_proposals(proposals)

    assert "P1" in text
    assert "P2" in text
    assert "确认 P1 方案A" in text
    assert "不会直接写入" in text
