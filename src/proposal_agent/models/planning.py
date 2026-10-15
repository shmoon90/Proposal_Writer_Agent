"""WBSItem, Dependency, StaffRole, StaffingAllocation (DATA_MODEL.md 4.7~4.8, Phase 4 확장).

날짜·기간·공수 합계는 planning/ 코드가 계산한다. 에이전트는 공수 제안값과 근거만 준다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import DependencyType, WBSLevel


class WorkType(StrEnum):
    """업무 유형 표시용. 실제 의존 관계는 Dependency로 별도 관리한다."""

    PREDECESSOR = "선행업무"
    SUCCESSOR = "후행업무"
    STANDALONE = "단독업무"


class TaskStatus(StrEnum):
    PLANNED = "계획"
    IN_PROGRESS = "진행중"
    DONE = "완료"
    ON_HOLD = "보류"


class TestResult(StrEnum):
    NOT_RUN = "미실행"
    PASSED = "성공"
    FAILED = "실패"
    ON_HOLD = "보류"


class WBSItem(ProjectScoped):
    id_prefix: ClassVar[str] = "wbs"

    code: str = Field(description="1 / 1.1 / 1.1.1 형식 표시 코드 (최대 3단계)")
    parent_id: str | None = None
    level: WBSLevel
    name: str
    description: str = ""
    related_requirement_ids: list[str] = Field(default_factory=list)
    role: str = Field(default="", description="담당 역할")
    work_type: WorkType = WorkType.STANDALONE
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    duration_days: int | None = Field(default=None, description="영업일 기준 기간")
    effort_md: Decimal = Decimal("0")
    estimate_basis: str = Field(default="", description="산정 근거 (생성 시 필수 검증)")
    status: TaskStatus = TaskStatus.PLANNED
    deliverable_names: list[str] = Field(default_factory=list)
    roles: list[dict[str, str]] = Field(
        default_factory=list, description="[{role, ratio}] 공수 배분"
    )
    order: int = 0
    notes: str = ""
    auto_generated: bool = Field(
        default=False, description="에이전트 결과 없이 코드 기본값으로 생성됨 → 검토 필요"
    )


class Dependency(ProjectScoped):
    id_prefix: ClassVar[str] = "dep"

    predecessor_id: str
    successor_id: str
    type: DependencyType = DependencyType.FS
    lag_days: int = 0


class StaffRole(ProjectScoped):
    id_prefix: ClassVar[str] = "role"

    role_name: str
    organization: str = ""
    grade: str | None = Field(default=None, description="기술 등급 (특급/고급/중급/초급)")
    skills: list[str] = Field(default_factory=list)
    duties: str = ""
    unit_cost_per_mm: Decimal | None = Field(
        default=None, description="단가(원/MM). 입력 없으면 비용 계산하지 않음"
    )
    headcount_planned: int = 1
    notes: str = ""


class StaffingAllocation(ProjectScoped):
    id_prefix: ClassVar[str] = "alloc"

    wbs_item_id: str
    staff_role_id: str
    person_name: str | None = None
    start: date | None = None
    end: date | None = None
    allocation_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    effort_md: Decimal = Decimal("0")
    monthly_md: dict[str, str] = Field(
        default_factory=dict, description="YYYY-MM → M/D (Decimal 문자열)"
    )
    estimate_basis: str = ""
