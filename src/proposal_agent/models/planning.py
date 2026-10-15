"""WBSItem, Dependency, StaffRole, StaffingAllocation (DATA_MODEL.md 4.7~4.8).

Phase 1에서는 모델 정의만 제공한다. 일정·공수 계산은 Phase 3 (planning/).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import DependencyType, WBSLevel


class WBSItem(ProjectScoped):
    id_prefix: ClassVar[str] = "wbs"

    code: str = Field(description="WBS-1.2.3 형식 표시 코드")
    parent_id: str | None = None
    level: WBSLevel
    name: str
    description: str = ""
    planned_start: date | None = None
    planned_end: date | None = None
    duration_days: int | None = None
    effort_md: Decimal = Decimal("0")
    estimate_basis: str = Field(default="", description="산정 근거 (생성 시 필수 검증)")
    deliverable_names: list[str] = Field(default_factory=list)
    order: int = 0


class Dependency(ProjectScoped):
    id_prefix: ClassVar[str] = "dep"

    predecessor_id: str
    successor_id: str
    type: DependencyType = DependencyType.FS
    lag_days: int = 0


class StaffRole(ProjectScoped):
    id_prefix: ClassVar[str] = "role"

    role_name: str
    grade: str | None = None
    unit_cost_per_mm: Decimal | None = None
    headcount_planned: int = 1


class StaffingAllocation(ProjectScoped):
    id_prefix: ClassVar[str] = "alloc"

    wbs_item_id: str
    staff_role_id: str
    person_name: str | None = None
    start: date | None = None
    end: date | None = None
    allocation_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    effort_md: Decimal = Decimal("0")
