"""Requirement, RequirementChange, RequirementTrace (DATA_MODEL.md 4.3~4.5, 4.14)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped, utcnow
from proposal_agent.models.enums import (
    AcceptanceStatus,
    ChangeStatus,
    ChangeType,
    Priority,
    RequirementCategory,
    RequirementStatus,
    RequirementType,
    ReviewStatus,
    ScopeClass,
    TraceTargetType,
    VerificationStatus,
)


class SourceRef(BaseModel):
    """원본 출처 좌표. 확인할 수 없는 값은 None (페이지 추측 금지)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    block_id: str | None = None
    page: int | None = None
    section: str | None = None
    location_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    quote: str = ""


class RequirementDraft(BaseModel):
    """에이전트 출력용 서브셋. ID·상태·감사 필드는 받지 않는다 (DATA_MODEL.md 4.3)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="요구사항명 (간결한 한 문장)")
    description: str = Field(min_length=1, description="상세 내용. 원문 의미를 바꾸지 않는다")
    type: RequirementType = Field(
        description="functional/non_functional/constraint/evaluation/submission"
    )
    category: RequirementCategory = RequirementCategory.OTHER
    scope_class: ScopeClass = Field(
        default=ScopeClass.MANDATORY,
        description="mandatory(RFP 필수)/supporting(필수 구현 지원)/optional_proposal(부가 제안)/out_of_scope(과잉)",
    )
    is_mandatory: bool = Field(default=True, description="RFP가 요구하는 필수 항목인지")
    priority: Priority = Priority.MEDIUM
    rfp_quote: str = Field(default="", description="근거가 된 원문 인용 (그대로 복사)")
    source_block_ids: list[str] = Field(
        default_factory=list, description="입력으로 받은 블록 ID. 반드시 입력 블록 ID 중에서 선택"
    )
    rationale: str | None = Field(default=None, description="추출·분류 근거")
    implementation_approach: str | None = None
    verification_method: str | None = Field(
        default=None, description="검증 방법 (시연/시험/검사/분석)"
    )
    impact_note: str | None = Field(
        default=None, description="부가 제안일 때 비용·일정·운영 영향. 필수 항목은 None"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="추출 신뢰도")


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    actor: str
    action: str
    changes: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class Requirement(ProjectScoped):
    """요구사항. ``id``는 id_policy가 발급한 ``FR-001`` 형식이며 재발급하지 않는다."""

    id_prefix: ClassVar[str] = "REQ"

    name: str = Field(min_length=1)
    description: str = ""
    type: RequirementType
    category: RequirementCategory = RequirementCategory.OTHER
    scope_class: ScopeClass = ScopeClass.MANDATORY
    is_mandatory: bool = True
    implementation_approach: str | None = None
    acceptance_status: AcceptanceStatus = AcceptanceStatus.PROPOSED
    status: RequirementStatus = RequirementStatus.DRAFT
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    review_status: ReviewStatus = ReviewStatus.PENDING
    priority: Priority = Priority.MEDIUM
    verification_method: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    rfp_quote: str | None = None
    rationale: str | None = None
    impact_note: str | None = None
    notes: str = ""
    linked_deliverables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    history: list[HistoryEntry] = Field(default_factory=list)
    version: int = 1
    added_by: str | None = Field(default=None, description="구축 단계에서 추가 요청한 사람")
    added_on: date | None = None
    change_state: str = Field(
        default="none", description="none | added | modified | delete_requested | deleted"
    )
    change_summary: str = ""
    previous_versions: list[dict[str, Any]] = Field(
        default_factory=list, description="변경 전 스냅샷 (이전 버전 보존)"
    )

    @classmethod
    def from_draft(
        cls,
        draft: RequirementDraft,
        *,
        id: str,
        project_id: str,
        created_by: str,
        source_refs: list[SourceRef] | None = None,
    ) -> Requirement:
        data = draft.model_dump(exclude={"source_block_ids"})
        return cls(
            id=id,
            project_id=project_id,
            created_by=created_by,
            source_refs=source_refs or [],
            **data,
        )

    def add_history(
        self, actor: str, action: str, changes: dict[str, Any] | None = None, note: str = ""
    ) -> None:
        self.history.append(
            HistoryEntry(
                at=utcnow().isoformat(),
                actor=actor,
                action=action,
                changes=changes or {},
                note=note,
            )
        )
        self.version += 1


# 허용된 상태 전이 (DATA_MODEL.md 5절)
REQUIREMENT_TRANSITIONS: dict[RequirementStatus, frozenset[RequirementStatus]] = {
    RequirementStatus.DRAFT: frozenset({RequirementStatus.DRAFT, RequirementStatus.VERIFIED}),
    RequirementStatus.VERIFIED: frozenset({RequirementStatus.DRAFT, RequirementStatus.BASELINE}),
    RequirementStatus.BASELINE: frozenset({RequirementStatus.CHANGED, RequirementStatus.DELETED}),
    RequirementStatus.CHANGED: frozenset({RequirementStatus.BASELINE}),
    RequirementStatus.DELETED: frozenset({RequirementStatus.BASELINE}),
}


def can_transition(current: RequirementStatus, new: RequirementStatus) -> bool:
    return new in REQUIREMENT_TRANSITIONS.get(current, frozenset())


class ImpactAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_requirement_ids: list[str] = Field(default_factory=list)
    suggested_requirement_ids: list[str] = Field(
        default_factory=list, description="에이전트가 의미적으로 제안한 추가 영향 (라벨 구분)"
    )
    affected_deliverables: list[str] = Field(default_factory=list)
    affected_wbs_item_ids: list[str] = Field(default_factory=list)
    schedule_delta_days: int = 0
    effort_delta_md: Decimal = Decimal("0")
    staffing_delta: list[dict[str, Any]] = Field(default_factory=list)
    cost_delta: Decimal | None = None
    narrative: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RequirementChange(ProjectScoped):
    id_prefix: ClassVar[str] = "chg"

    requirement_id: str | None = None
    change_type: ChangeType
    status: ChangeStatus = ChangeStatus.REQUESTED
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    diff_summary: str = ""
    semantic_summary: str | None = None
    impact: ImpactAnalysis | None = None
    requested_by: str = ""
    reason: str = ""
    approval_id: str | None = None
    revision_id: str | None = None


class RequirementTrace(ProjectScoped):
    id_prefix: ClassVar[str] = "trc"

    requirement_id: str
    target_type: TraceTargetType
    target_id: str
    note: str | None = None
    review_status: str = Field(default="유효", description="유효 | 재검토 필요 | 무효")
    review_reason: str = ""
