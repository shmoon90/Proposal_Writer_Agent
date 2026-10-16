"""의사결정·기술 협상 엔티티 (지시문 §10·§17, 단계 1).

- ``Decision``: 회의·인터뷰·질의응답·내부 검토에서 나온 **결정·요청·의견·미결 질문** 을 구분해 기록한다.
  회의에서 논의되었다는 사실만으로 승인으로 보지 않는다: ``kind=official_decision`` 이고 ``approved_by`` 가 있을 때만
  승인된 결정이며, 결정 권한이 확인되지 않으면 ``authority_confirmed=False`` 로 남는다.
- ``Negotiation``: 기술 협상·계약 변경 항목. 변경 전/후·사유·합의 여부·영향·승인 상태를 담고, 승인(``applied``) 전에는
  기준선에 자동 반영되지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import DecisionKind, DecisionStatus, NegotiationStatus


class Decision(ProjectScoped):
    id_prefix: ClassVar[str] = "DEC"

    code: str = Field(default="", description="문서 표시 ID (예: DEC-001)")
    title: str = Field(min_length=1)
    kind: DecisionKind = DecisionKind.OPEN_QUESTION
    status: DecisionStatus = DecisionStatus.PROPOSED
    content: str = Field(default="", description="결정·요청·질문 내용")
    rationale: str = Field(default="", description="결정 근거")
    source_document_id: str | None = Field(
        default=None, description="원본 자료(회의록·이메일) 문서 ID"
    )
    source_excerpt: str = Field(default="", description="원문 인용")
    recorded_on: date | None = None
    owner: str = Field(default="", description="담당자")
    due_date: date | None = None
    authority_confirmed: bool = Field(default=False, description="결정 권한 확인 여부")
    approved_by: str = ""
    approved_at: datetime | None = None
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_design_ids: list[str] = Field(
        default_factory=list, description="화면·DB·API·설계 항목 ID"
    )
    related_change_request_ids: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(
        default_factory=list, description="조치 항목 (담당·기한 포함 문장)"
    )
    version: int = 1

    @property
    def is_binding(self) -> bool:
        """승인된 공식 결정만 기준선에 반영할 수 있다."""
        return (
            self.kind == DecisionKind.OFFICIAL_DECISION
            and self.status == DecisionStatus.APPROVED
            and self.authority_confirmed
            and bool(self.approved_by)
        )


class Negotiation(ProjectScoped):
    id_prefix: ClassVar[str] = "NEG"

    code: str = Field(default="", description="문서 표시 ID (예: NEG-001)")
    title: str = Field(min_length=1)
    status: NegotiationStatus = NegotiationStatus.PROPOSED
    before: str = Field(default="", description="변경 전 내용 (요구사항·제안 기준)")
    after: str = Field(default="", description="변경 후 내용")
    reason: str = ""
    customer_agreed: bool | None = Field(default=None, description="고객 합의 여부 (None=미확인)")
    contract_impact: str = ""
    schedule_impact: str = ""
    cost_effort_impact: str = ""
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_deliverable_ids: list[str] = Field(default_factory=list)
    related_decision_ids: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    approved_by: str = ""
    approved_at: datetime | None = None
    version: int = 1

    @property
    def can_apply_to_baseline(self) -> bool:
        return (
            self.status == NegotiationStatus.AGREED
            and self.customer_agreed is True
            and bool(self.approved_by)
        )


__all__ = ["Decision", "Negotiation"]
