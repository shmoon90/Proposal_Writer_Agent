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
# 그림 정책 (Phase 16): 사진·일러스트·장식·참고 이미지는 이미지 삽입을 허용하되 도형 이름을 '<태그>:<설명>'으로 붙인다.
# 태그 없는 그림은 표·구조도·차트·목업 같은 정보성 자료를 이미지로 만든 것으로 보고 QA-FILE-12가 실패시킨다.
PICTURE_TAGS: tuple[str, ...] = ("photo", "illustration", "decoration", "reference")
PICTURE_TAG_LABELS: dict[str, str] = {
    "photo": "사진",
    "illustration": "일러스트",
    "decoration": "장식 배경",
    "reference": "참고 이미지",
}


def picture_name(tag: str, label: str) -> str:
    """허용 그림의 도형 이름. 태그가 허용 목록에 없으면 ValueError."""
    if tag not in PICTURE_TAGS:
        raise ValueError(f"허용되지 않는 그림 태그: {tag} (허용: {', '.join(PICTURE_TAGS)})")
    return f"{tag}:{label[:60]}"


def parse_picture_name(file_name: str) -> tuple[str, str]:
    """업로드 파일명 '<태그>__<설명>.png' → (태그, 설명). 태그가 없으면 reference."""
    stem = str(file_name).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if "__" in stem:
        tag, caption = stem.split("__", 1)
        if tag in PICTURE_TAGS:
            return tag, caption.strip() or stem
    return "reference", stem


def picture_tag(shape_name: str | None) -> str | None:
    """도형 이름에서 허용 태그를 읽는다. 없으면 None (정보성 자료로 간주)."""
    head = (shape_name or "").split(":", 1)[0].strip().lower()
    return head if head in PICTURE_TAGS else None


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
    change_log: list[list[Any]] = field(default_factory=list)  # 구축 단계 변경관리대장 행 (CR 단위)
    settings: Any | None = None  # ProjectSettings (단계 4: 분량 모드·단가·예산)
    design_links: dict[str, dict[str, list[str]]] = field(
        default_factory=dict
    )  # 요구사항 ID → {strategy|api|db_table|design_item|code_module|test_case: [코드…]} (단계 4 추적표)
    strategies: list[Any] = field(
        default_factory=list
    )  # 제안 전략 STR 엔티티 (단계 3, ProposalStrategy) — 덱 '제안 전략' 소절
    designs: list[dict[str, Any]] = field(
        default_factory=list
    )  # 요구사항 묶음별 구현 설계 (Phase 23, design_writer 출력의 designs[])
    slide_specs: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )  # profile → 소절별 슬라이드 범위·명세 (Phase 19, 덱 생성 중 기록)
    extra_paths: dict[str, str] = field(
        default_factory=dict
    )  # 보조 파일(슬라이드 명세 등) → 절대 경로
    pictures: list[dict[str, Any]] = field(
        default_factory=list
    )  # 등록된 참고 그림 [{file_name, path, tag, caption}] (Phase 20, DocumentKind.PICTURE)
    used_pictures: set[str] = field(default_factory=set)  # 덱 본문에 이미 넣은 그림 파일명
    page_map: dict[str, dict[str, list[int]]] = field(
        default_factory=dict
    )  # 요구사항 ID → {"submission": [슬라이드…], "presentation": [...]} (Phase 17, 덱 생성 후 채움)

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
