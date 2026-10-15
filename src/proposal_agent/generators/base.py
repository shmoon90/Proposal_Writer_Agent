"""산출물 생성기 공통.

- 모든 생성기는 공통 데이터(``GenerationContext``)만 입력으로 받고 파일 바이트를 만든다.
- 저장은 ``FileStore``로 (덮어쓰기 금지, 버전 파일명), 기록은 ``Deliverable`` 엔티티.
- 임시 산출물(draft)은 유형별 폴더에, 최종본은 승인 후 ``13_Final_Deliverables``에 복사한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from proposal_agent.models import (
    ArchitectureComponent,
    Dependency,
    Project,
    Requirement,
    StaffingAllocation,
    StaffRole,
    TechnologyResearch,
    WBSItem,
)

ACCEPTANCE_LABELS: dict[str, str] = {
    "accepted": "수용",
    "partially_accepted": "조건부 수용",
    "rejected": "미수용",
    "proposed": "검토 필요",
    "deferred": "검토 필요",
}
ACCEPTANCE_OPTIONS: tuple[str, ...] = ("수용", "조건부 수용", "미수용", "검토 필요")
PENDING_ID = "미정"


@dataclass
class GenerationContext:
    project: Project
    requirements: list[Requirement]
    wbs: list[WBSItem] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    roles: list[StaffRole] = field(default_factory=list)
    allocations: list[StaffingAllocation] = field(default_factory=list)
    components: list[ArchitectureComponent] = field(default_factory=list)
    research: list[TechnologyResearch] = field(default_factory=list)
    analysis: dict[str, Any] | None = None
    proposal_content: dict[str, Any] | None = None
    period_start: date | None = None
    period_end: date | None = None
    diagram_paths: dict[str, str] = field(default_factory=dict)  # kind → 절대 경로
    review_notes: list[str] = field(default_factory=list)
    version: str = "v1.0"
    generated_on: date = field(default_factory=date.today)

    @property
    def wbs_by_id(self) -> dict[str, WBSItem]:
        return {w.id: w for w in self.wbs}

    @property
    def roles_by_id(self) -> dict[str, StaffRole]:
        return {r.id: r for r in self.roles}

    @property
    def total_effort_md(self) -> Decimal:
        return sum((w.effort_md for w in self.wbs if w.parent_id is None), Decimal("0"))

    def mandatory_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.scope_class.value in ("mandatory", "supporting")]


def acceptance_label(req: Requirement) -> str:
    return ACCEPTANCE_LABELS.get(req.acceptance_status.value, "검토 필요")


def requirement_note(req: Requirement) -> str:
    """비고: 근거·제약·검토 의견·미수용 사유를 모아 적는다."""
    parts: list[str] = []
    if req.rationale:
        parts.append(f"근거: {req.rationale}")
    if req.scope_class.value == "optional_proposal":
        parts.append("부가 제안" + (f" (영향: {req.impact_note})" if req.impact_note else ""))
    if req.acceptance_status.value in ("rejected", "partially_accepted"):
        parts.append(f"{acceptance_label(req)} 사유: {req.notes or '사유 미기재 — 검토 필요'}")
    elif req.notes:
        parts.append(req.notes)
    if req.verification_status.value != "verified":
        parts.append(f"검증 상태: {req.verification_status.value}")
    if req.review_status.value == "pending" and req.confidence < 0.6:
        parts.append("저신뢰 추출 — 검토 필요")
    return " / ".join(parts)
