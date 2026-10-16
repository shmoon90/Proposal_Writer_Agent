"""근거 구분·대응 전략 기본값 (Phase 17, 요청서 §3).

제안서·추적표는 RFP 명시 / 참고 문서 / 외부 조사 / 설계 제안을 구분해야 한다. 요구사항이 생길 때 코드가 출처를 알고
있으므로(추출·기준 문서 적재·수동 추가·변경 반영) 그때 ``evidence_class``를 붙이고, 비어 있으면 아래 규칙으로 추정한다.
"""

from __future__ import annotations

from proposal_agent.models import Requirement, ScopeClass

# generators.base와 순환 참조를 피하려고 수용 상태 표기를 여기서도 둔다 (값은 generators.base.ACCEPTANCE_LABELS와 같다)
_ACCEPT_LABELS = {
    "accepted": "수용",
    "partially_accepted": "조건부 수용",
    "rejected": "미수용",
    "proposed": "검토 필요",
    "deferred": "검토 필요",
}

EVIDENCE_RFP = "rfp"
EVIDENCE_REFERENCE = "reference_doc"
EVIDENCE_RESEARCH = "research"
EVIDENCE_DESIGN = "design_proposal"
EVIDENCE_LABELS: dict[str, str] = {
    EVIDENCE_RFP: "RFP 명시",
    EVIDENCE_REFERENCE: "참고 문서",
    EVIDENCE_RESEARCH: "외부 조사",
    EVIDENCE_DESIGN: "설계 제안",
}


def default_evidence_class(req: Requirement) -> str:
    """저장된 값이 있으면 그대로, 없으면 출처·범위 분류로 추정한다."""
    if req.evidence_class in EVIDENCE_LABELS:
        return req.evidence_class
    if req.approach_source == "baseline" or (req.rationale or "").startswith("기준 문서 적재"):
        return EVIDENCE_REFERENCE
    if req.scope_class in (
        ScopeClass.SUPPORTING,
        ScopeClass.OPTIONAL_PROPOSAL,
        ScopeClass.OUT_OF_SCOPE,
    ):
        return EVIDENCE_DESIGN
    if req.source_refs or req.rfp_quote:
        return EVIDENCE_RFP
    return EVIDENCE_DESIGN


def evidence_label(req: Requirement) -> str:
    return EVIDENCE_LABELS.get(default_evidence_class(req), default_evidence_class(req))


def default_response_strategy(req: Requirement) -> str:
    """추적표 '대응 전략': 저장값 > 수용 상태 + 구현 방안 첫 줄."""
    if req.response_strategy:
        return req.response_strategy
    accept = _ACCEPT_LABELS.get(req.acceptance_status.value, "검토 필요")
    if req.acceptance_status.value == "rejected":
        return f"{accept} — {req.notes[:60] if req.notes else '사유 검토 필요'}"
    first = ""
    for line in (req.implementation_approach or "").splitlines():
        t = line.strip().lstrip("-•· ").strip()
        if t and not t.startswith("[자동 초안]"):
            first = t
            break
    return f"{accept} — {first[:80]}" if first else f"{accept} — 구현 방안 확정 필요"


__all__ = [
    "EVIDENCE_DESIGN",
    "EVIDENCE_LABELS",
    "EVIDENCE_REFERENCE",
    "EVIDENCE_RESEARCH",
    "EVIDENCE_RFP",
    "default_evidence_class",
    "default_response_strategy",
    "evidence_label",
]
