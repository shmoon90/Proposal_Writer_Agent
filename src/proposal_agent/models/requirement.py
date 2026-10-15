"""Requirement, RequirementChange, RequirementTrace (DATA_MODEL.md 4.3~4.5, 4.14)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import (
    AcceptanceStatus,
    ChangeStatus,
    ChangeType,
    Priority,
    RequirementCategory,
    RequirementStatus,
    RequirementType,
    ScopeClass,
    TraceTargetType,
    VerificationStatus,
)


class SourceRef(BaseModel):
    """원본 출처 좌표."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    page: int | None = None
    section: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    quote: str = ""


class RequirementDraft(BaseModel):
    """에이전트 출력용 서브셋. ID·상태·감사 필드는 받지 않는다 (DATA_MODEL.md 4.3)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    type: RequirementType
    category: RequirementCategory = RequirementCategory.OTHER
    scope_class: ScopeClass = ScopeClass.MANDATORY
    priority: Priority = Priority.MEDIUM
    rfp_quote: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    rationale: str | None = None
    implementation_approach: str | None = None


class Requirement(ProjectScoped):
    """요구사항. ``id``는 id_policy가 발급한 ``REQ-F-001`` 형식이며 재발급하지 않는다."""

    id_prefix: ClassVar[str] = "REQ"

    name: str = Field(min_length=1)
    description: str = ""
    type: RequirementType
    category: RequirementCategory = RequirementCategory.OTHER
    scope_class: ScopeClass = ScopeClass.MANDATORY
    implementation_approach: str | None = None
    acceptance_status: AcceptanceStatus = AcceptanceStatus.PROPOSED
    status: RequirementStatus = RequirementStatus.DRAFT
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    priority: Priority = Priority.MEDIUM
    source_refs: list[SourceRef] = Field(default_factory=list)
    rfp_quote: str | None = None
    rationale: str | None = None
    tags: list[str] = Field(default_factory=list)
    version: int = 1

    @classmethod
    def from_draft(
        cls, draft: RequirementDraft, *, id: str, project_id: str, created_by: str
    ) -> Requirement:
        return cls(
            id=id,
            project_id=project_id,
            created_by=created_by,
            **draft.model_dump(),
        )


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
