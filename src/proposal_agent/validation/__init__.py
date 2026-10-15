"""독립 검증 및 QA."""

from proposal_agent.validation.deliverables import (
    Finding,
    QaOutcome,
    check_consistency,
    check_pptx,
    check_xlsx,
    pptx_texts,
    render_report,
)
from proposal_agent.validation.qa_service import GATE4_KEY, QaRunResult, QaService

__all__ = [
    "GATE4_KEY",
    "Finding",
    "QaOutcome",
    "QaRunResult",
    "QaService",
    "check_consistency",
    "check_pptx",
    "check_xlsx",
    "pptx_texts",
    "render_report",
]
