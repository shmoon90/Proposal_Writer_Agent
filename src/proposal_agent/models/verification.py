"""독립 검증 결과와 Gate 평가 모델 (Phase 2).

``VerificationFinding``은 검증 에이전트의 구조화 출력 항목이며, 코드가 ``ValidationResult``로 저장한다.
``GateEvaluation``은 코드가 계산한 Gate 상태(PASS/FAIL/NEEDS_HUMAN_REVIEW)와 근거다.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import GateStatus, ScopeClass

FINDING_KINDS: tuple[str, ...] = (
    "missing_requirement",  # 누락된 요구사항
    "duplicate",  # 중복 추출
    "distortion",  # 의미 왜곡
    "misinterpretation",  # 원문과 다른 해석
    "weak_acceptance_basis",  # 수용 여부 판단 근거 부족
    "missing_source",  # 원본 출처 누락
    "contradiction",  # 요구사항 간 모순
    "feasibility_check_needed",  # 기술적 구현 가능성 확인 필요
    "scope_creep",  # 과도하게 확장된 범위
    "table_or_image_omission",  # 표·이미지 누락
    "classification",  # 종류/범위 분류 오류
)


class VerificationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="다음 중 하나: " + ", ".join(FINDING_KINDS))
    severity: str = Field(description="error | warning | info")
    requirement_ids: list[str] = Field(
        default_factory=list, description="관련 요구사항 ID (있으면)"
    )
    message: str
    evidence_quote: str = Field(default="", description="원문 인용 근거")
    source_block_ids: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None
    suggested_scope_class: ScopeClass | None = None


class RequirementVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    verdict: str = Field(description="verified | needs_revision | rejected")
    scope_class_opinion: ScopeClass | None = None
    comment: str = ""


class VerificationReport(BaseModel):
    """검증 에이전트 구조화 출력."""

    model_config = ConfigDict(extra="forbid")

    verdicts: list[RequirementVerdict] = Field(default_factory=list)
    findings: list[VerificationFinding] = Field(default_factory=list)
    coverage_estimate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="원문 요구사항 중 추출된 비율 추정"
    )
    summary: str = ""


class GateEvaluation(ProjectScoped):
    id_prefix: ClassVar[str] = "gev"

    gate_key: str = Field(description="gate0 | gate1 | ...")
    status: GateStatus
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evaluated_by: str = "code"
    approval_id: str | None = Field(
        default=None, description="사람이 NEEDS_HUMAN_REVIEW를 승인한 경우"
    )
    step_run_id: str | None = None
