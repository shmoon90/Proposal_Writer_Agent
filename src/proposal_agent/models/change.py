"""구축 단계 변경관리 모델 (Phase 6).

- ``ChangeRequest``: 변경 요청 1건(접수 → 분석 → 승인/반려 → 반영). 후보(``ChangeCandidate``)와 영향(``ChangeImpact``)을 포함한다.
- 사용자가 편집한 값과 AI/규칙이 추론한 값을 ``source``·``user_edits``로 구분한다.
- 기존 요구사항은 물리 삭제하지 않고, 변경 전후 내용을 ``before``/``after`` 스냅샷으로 보존한다.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import ChangeStatus


class CandidateClass(StrEnum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    DELETE_REQUEST = "DELETE_REQUEST"
    NO_CHANGE = "NO_CHANGE"
    AMBIGUOUS = "AMBIGUOUS"


class InputKind(StrEnum):
    SELECT = "select"  # 요구사항 목록에서 선택
    ADD_BUTTON = "add_button"
    MODIFY_BUTTON = "modify_button"
    DELETE_BUTTON = "delete_button"
    NATURAL_LANGUAGE = "natural_language"
    DOCUMENT = "document"


class StaffingScenario(StrEnum):
    S1_EXISTING_OK = "1"  # 기존 인력·일정으로 대응 가능
    S2_RESCHEDULE = "2"  # 기존 인력 유지, 일정 조정 필요
    S3_EXTEND = "3"  # 기존 인력 투입 기간 연장 필요
    S4_NEW_ROLE = "4"  # 추가 인력 또는 새 기술 역할 필요
    S5_OFFSET = "5"  # 기존 업무 감소·대체로 상쇄
    S6_UNKNOWN = "6"  # 자료 부족 → 사용자 판단

    @property
    def label(self) -> str:
        return {
            "1": "기존 인력과 일정으로 대응 가능",
            "2": "기존 인력 유지, 일정 조정 필요",
            "3": "기존 인력의 투입 기간 연장 필요",
            "4": "추가 인력 또는 새로운 기술 역할 필요",
            "5": "기존 업무 감소·대체로 공수 상쇄 가능",
            "6": "자료 부족 → 사용자 판단 필요",
        }[self.value]


class SemanticFeatures(BaseModel):
    """의미 비교에 쓰는 특징 (코드 추출 + 에이전트 보강)."""

    model_config = ConfigDict(extra="forbid")

    purpose: str = ""
    actors: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    inputs_outputs: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    quality: list[str] = Field(default_factory=list, description="성능·보안 조건")
    screens: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ChangeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    classification: CandidateClass
    requirement_id: str | None = Field(
        default=None, description="관련 기존 요구사항 ID (MODIFY/DELETE/NO_CHANGE)"
    )
    related_ids: list[str] = Field(default_factory=list)
    proposed_name: str = ""
    proposed_description: str = ""
    proposed_type: str = "functional"
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = True
    source: str = Field(default="rule", description="user | rule | ai")
    schedule_constraint: str | None = Field(
        default=None, description="요청문에서 읽은 일정 제약 (예: 다음 배포 전)"
    )
    screens_affected: list[str] = Field(default_factory=list)
    tests_affected: list[str] = Field(default_factory=list)
    change_aspects: list[str] = Field(
        default_factory=list,
        description="문맥 비교에서 달라진 관점 (범위·대상 사용자·입출력·업무 규칙·수치 조건·화면·연계·성능/보안·데이터)",
    )
    difficulty: str | None = Field(
        default=None, description="변경 구현 난이도 상/중/하 (공수·일정 영향 가중치)"
    )
    difficulty_basis: str = ""
    user_decision: str | None = Field(default=None, description="accept | reject | None")
    user_override: dict[str, Any] = Field(
        default_factory=dict, description="사용자가 직접 수정한 필드"
    )
    evidence: list[str] = Field(default_factory=list, description="근거 문장(요청문·문서 인용)")

    def effective(self, key: str) -> Any:
        return self.user_override.get(key, getattr(self, key, None))


class TaskImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wbs_code: str
    task_name: str
    action: str = Field(description="reuse | modify | add | remove | test_add")
    requirement_ids: list[str] = Field(default_factory=list)
    before_start: date | None = None
    before_end: date | None = None
    after_start: date | None = None
    after_end: date | None = None
    effort_before_md: Decimal = Decimal("0")
    effort_added_md: Decimal = Decimal("0")
    effort_reduced_md: Decimal = Decimal("0")
    predecessors_changed: bool = False
    basis: str = ""


class EffortImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_md: Decimal = Decimal("0")
    added_md: Decimal = Decimal("0")
    reduced_md: Decimal = Decimal("0")
    net_md: Decimal = Decimal("0")
    after_md: Decimal = Decimal("0")
    estimate_status: str = Field(default="추정", description="확정 | 추정 | 범위")
    range_min_md: Decimal | None = None
    range_max_md: Decimal | None = None
    basis: str = ""
    assumptions: list[str] = Field(default_factory=list)


class RoleImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    exists_in_plan: bool = True
    before_mm: Decimal = Decimal("0")
    after_mm: Decimal = Decimal("0")
    delta_mm: Decimal = Decimal("0")
    peak_month_before: str | None = None
    peak_month_after: str | None = None
    headcount_before: int = 0
    headcount_needed: int = 0


class ChangeImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskImpact] = Field(default_factory=list)
    affected_requirement_ids: list[str] = Field(
        default_factory=list, description="같은 Task를 공유하는 다른 요구사항"
    )
    schedule_before_end: date | None = None
    schedule_after_end: date | None = None
    schedule_delta_days: int = 0
    project_end: date | None = None
    project_end_exceeded: bool = False
    changed_task_dates: list[str] = Field(default_factory=list)
    dependency_changes: list[str] = Field(default_factory=list)
    effort: EffortImpact = Field(default_factory=EffortImpact)
    staffing_plan_present: bool = False
    staffing_scenario: StaffingScenario = StaffingScenario.S6_UNKNOWN
    staffing_explanation: str = ""
    roles: list[RoleImpact] = Field(default_factory=list)
    cost_before: Decimal | None = None
    cost_after: Decimal | None = None
    cost_delta: Decimal | None = None
    tests_added: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = Field(default=None, description="순환 의존 등으로 계산을 중단한 사유")
    computed_by: str = "code:changes.impact"


class ChangeRequest(ProjectScoped):
    id_prefix: ClassVar[str] = "CR"

    title: str = ""
    input_kind: InputKind = InputKind.NATURAL_LANGUAGE
    request_text: str = ""
    requester: str = ""
    requested_on: date = Field(default_factory=date.today)
    reason: str = ""
    selected_requirement_ids: list[str] = Field(default_factory=list)
    attachment_document_ids: list[str] = Field(default_factory=list)
    status: ChangeStatus = ChangeStatus.REQUESTED
    candidates: list[ChangeCandidate] = Field(default_factory=list)
    impact: ChangeImpact | None = None
    analysis_sources: list[str] = Field(
        default_factory=list, description="rule | ai 등 분석에 쓰인 주체"
    )
    approval_id: str | None = None
    approver: str | None = None
    approved_at: datetime | None = None
    revision_id: str | None = None
    before_files: list[str] = Field(default_factory=list)
    after_files: list[str] = Field(default_factory=list)
    applied_requirement_ids: list[str] = Field(default_factory=list)
    result_summary: str = ""
    unresolved: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    user_edits: dict[str, Any] = Field(
        default_factory=dict, description="사용자가 직접 편집한 요청 필드"
    )

    @property
    def accepted_candidates(self) -> list[ChangeCandidate]:
        return [c for c in self.candidates if c.user_decision == "accept"]
