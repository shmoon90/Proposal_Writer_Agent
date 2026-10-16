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
from proposal_agent.validation.independent_qa import QaInputs, gate_status, run_all_checks
from proposal_agent.validation.qa_service import (
    GATE2_KEY,
    GATE3_KEY,
    GATE4_KEY,
    GATE5_KEY,
    QaRunResult,
    QaService,
    render_qa_report,
)
from proposal_agent.validation.render import RenderResult, com_available, render_pptx

__all__ = [
    "GATE2_KEY",
    "GATE3_KEY",
    "GATE4_KEY",
    "GATE5_KEY",
    "QaInputs",
    "RenderResult",
    "com_available",
    "render_pptx",
    "gate_status",
    "render_qa_report",
    "run_all_checks",
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
