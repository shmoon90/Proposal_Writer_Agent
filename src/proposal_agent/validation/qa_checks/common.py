"""독립 QA 공용: 입력(QaInputs)·산출물(CheckArtifacts)·검사 생성/마감 도우미·상수. (independent_qa 분할, 단계 1)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from proposal_agent.config.errors import PathSecurityError
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.generators.base import GenerationContext
from proposal_agent.models import (
    ArchitectureComponent,
    ChangeRequest,
    Deliverable,
    DeliverableKind,
    ExtractedBlock,
    Project,
    ProjectMode,
    QaCategory,
    QaCheck,
    QaResult,
    Requirement,
    Revision,
    SourceDocument,
    TechnologyResearch,
)
from proposal_agent.planning.calendar import BusinessCalendar
from proposal_agent.requirements.id_policy import normalize_text
from proposal_agent.validation.deliverables import (
    QaOutcome,
)

MANDATORY_PATTERNS = (
    "하여야 한다",
    "해야 한다",
    "하여야 함",
    "해야 함",
    "반드시",
    "필수",
    "하여야 하며",
    "해야 하며",
    "제공하여야",
    "지원하여야",
)

SUBMISSION_WORDS = (
    "제출 서류",
    "제출서류",
    "제출 방법",
    "제출방법",
    "제출 기한",
    "제출기한",
    "제안서 제출",
    "제출 장소",
    "제출처",
)

EVALUATION_WORDS = (
    "평가 기준",
    "평가기준",
    "배점",
    "평가 항목",
    "평가항목",
    "평가 방법",
    "심사 기준",
)

VERSION_RE = re.compile(r"\b(\d+(?:\.\d+){1,2})\b")

# Phase 19: QA-CON-10 추상 표현(근거 없이 쓰이는 과장 표현) · 단위 붙은 수치
ABSTRACT_WORDS = (
    "최적의",
    "최고의",
    "최상의",
    "완벽한",
    "완벽하게",
    "혁신적",
    "획기적",
    "세계적",
    "압도적",
    "탁월한",
    "유일한",
    "최첨단",
    "업계 최고",
    "검증된 역량",
    "풍부한 경험",
    "최고 수준",
)

NUMBER_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(\d[\d,]*(?:\.\d+)?)[ \t]*(%|퍼센트|배|초|ms|밀리초|분|시간|건|명|년|개월|주|일|억|만|천|TPS|GB|TB|MB|회|대|식|자리|페이지|장|종|배 이상)"
)  # 줄바꿈을 건너 'FR-013' + '대표…' 를 '013대'로 읽지 않도록 ID·줄바꿈 제외

# Phase 19: QA-CON-11 약어 — 대문자 2~8자(숫자·'/' 허용), ID(FR-001)·로마 숫자·일반 약어 제외
ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9/-])[A-Z][A-Z0-9]{1,7}(?:/[A-Z]{1,3})?(?![A-Za-z0-9/-])")

ROMAN_RE = re.compile(r"^[IVX]+$")

COMMON_ACRONYMS = frozenset(
    {
        "RFP",
        "PPT",
        "WBS",
        "PM",
        "PL",
        "QA",
        "IT",
        "SI",
        "ID",
        "PC",
        "OS",
        "MM",
        "MD",
        "M/D",
        "M/M",
        "S/W",
        "H/W",
        "SW",
        "HW",
        "TOC",
        "NO",
        "OK",
        "AS",
        "TO",
        "IS",
        "BE",
        "CR",
        "TR",
        "KPI",
        "RACI",
        "URL",
        "WEB",
        "CONTENTS",
    }
)

ID_IN_TEXT_RE = re.compile(r"\b[A-Z]{2,5}-\d{2,5}\b")

PROPOSAL_KINDS: tuple[DeliverableKind, ...] = (
    DeliverableKind.REQUIREMENT_SPEC_XLSX,
    DeliverableKind.TRACE_MATRIX_XLSX,
    DeliverableKind.WBS_GANTT_XLSX,
    DeliverableKind.STAFFING_PLAN_XLSX,
    DeliverableKind.SUBMISSION_PPTX,
    DeliverableKind.PRESENTATION_PPTX,
    DeliverableKind.SYSTEM_DIAGRAM_PNG,
    DeliverableKind.SW_DIAGRAM_PNG,
    DeliverableKind.SERVICE_DIAGRAM_PNG,
)

BUILD_KINDS: tuple[DeliverableKind, ...] = (
    DeliverableKind.REQUIREMENT_SPEC_XLSX,
    DeliverableKind.TRACE_MATRIX_XLSX,
    DeliverableKind.WBS_GANTT_XLSX,
)

FIX_REGENERATE = "regenerate"


@dataclass
class QaInputs:
    """검증에 필요한 모든 입력. 서비스가 모아서 넘기고, 검사 함수는 저장소를 직접 만지지 않는다."""

    project: Project
    ctx: GenerationContext
    paths: ProjectPaths
    calendar: BusinessCalendar
    blocks: list[ExtractedBlock] = field(default_factory=list)
    documents: list[SourceDocument] = field(default_factory=list)
    all_requirements: list[Requirement] = field(default_factory=list)
    research: list[TechnologyResearch] = field(default_factory=list)
    deliverables: dict[DeliverableKind, Deliverable] = field(default_factory=dict)
    change_requests: list[ChangeRequest] = field(default_factory=list)
    revisions: list[Revision] = field(default_factory=list)
    decisions: list[Any] = field(default_factory=list)  # 단계 5: Decision(DEC)
    negotiations: list[Any] = field(default_factory=list)  # 단계 5: Negotiation(NEG)
    rfp_analysis: dict[str, Any] | None = None
    id_prefixes: dict[str, str] = field(default_factory=dict)
    rfp_profile: Any | None = None  # ingest.rfp_profile.RfpProfile
    template_profiles: dict[str, Any] = field(default_factory=dict)  # purpose → TemplateProfile
    rfp_toc_tree: list[dict[str, Any]] = field(default_factory=list)
    gate_p_status: str = (
        ""  # Gate P(목차·전략 승인) 상태: PASS | NEEDS_HUMAN_REVIEW | FAIL | ''(미평가) (Phase 18)
    )
    strategy_brief: dict[str, Any] | None = None
    # Phase 21
    render_check: bool = False  # PowerPoint COM 실제 렌더링·재열기(QA-FILE-14) 수행 여부
    render_dir: Path | None = None  # PNG 출력 폴더 (11_QA_Validation_Reports/render)
    page_limit: int | None = None  # RFP 페이지 제한(쪽). 없으면 QA-FILE-13 미실행

    @property
    def mode(self) -> ProjectMode:
        return self.project.mode

    @property
    def requirements(self) -> list[Requirement]:
        return self.ctx.requirements

    @property
    def components(self) -> list[ArchitectureComponent]:
        return self.ctx.components

    @property
    def required_kinds(self) -> tuple[DeliverableKind, ...]:
        if self.mode == ProjectMode.BUILD:
            kinds = list(BUILD_KINDS)
            if self.deliverables.get(DeliverableKind.STAFFING_PLAN_XLSX) or self.ctx.allocations:
                kinds.append(DeliverableKind.STAFFING_PLAN_XLSX)
            return tuple(kinds)
        return PROPOSAL_KINDS


@dataclass
class CheckArtifacts:
    template_fails: list[str] = field(default_factory=list)
    template_reviews: list[str] = field(default_factory=list)
    outcome: QaOutcome = field(default_factory=QaOutcome)
    excel: dict[DeliverableKind, dict[str, list[list[Any]]]] = field(default_factory=dict)
    ppt_texts: dict[str, list[str]] = field(default_factory=dict)
    render_results: dict[str, Any] = field(default_factory=dict)  # 라벨 → RenderResult (Phase 21)


def _check(
    check_id: str,
    category: QaCategory,
    target: str,
    criteria: str,
    *,
    gate: str,
    mandatory: bool = True,
    fixable: str | None = None,
    fix_suggestion: str = "",
) -> QaCheck:
    return QaCheck(
        check_id=check_id,
        category=category,
        target=target,
        criteria=criteria,
        gate=gate,
        mandatory=mandatory,
        fixable=fixable,
        fix_suggestion=fix_suggestion,
    )


def _finish(
    check: QaCheck,
    *,
    fail: list[str] | None = None,
    review: list[str] | None = None,
    req_ids: list[str] | None = None,
    files: list[str] | None = None,
) -> QaCheck:
    fail = fail or []
    review = review or []
    check.issues = [*fail, *review]
    check.requirement_ids = sorted(set(req_ids or []))
    check.files = sorted(set(files or []))
    if fail:
        check.result = QaResult.FAIL
    elif review:
        check.result = QaResult.NEEDS_HUMAN_REVIEW
    else:
        check.result = QaResult.PASS
        check.fixable = None
    return check


def _not_run(check: QaCheck, reason: str, *, applicable: bool = False) -> QaCheck:
    """실행하지 않은 항목. ``applicable=False``(모드상 해당 없음)는 게이트를 막지 않고, True면 검토 필요로 남는다."""
    check.executed = False
    check.applicable = applicable
    check.not_run_reason = reason
    check.result = QaResult.NEEDS_HUMAN_REVIEW
    check.fixable = None
    return check


def _cap(items: list[str], n: int = 10) -> list[str]:
    return items[:n] + ([f"… 외 {len(items) - n}건"] if len(items) > n else [])


# --- RFP 적합성 --------------------------------------------------------------------------------
def _block_text_index(blocks: list[ExtractedBlock]) -> dict[str, str]:
    return {b.id: normalize_text(b.text) for b in blocks}


def _spec_rows(sheets: dict[str, list[list[Any]]]) -> dict[str, dict[str, Any]]:
    """정의서 본문 시트 행을 요구사항 ID → {컬럼명: 값}으로 모은다."""
    out: dict[str, dict[str, Any]] = {}
    for name in ("기능요구사항", "비기능요구사항", "제약·평가·제출조건"):
        data = sheets.get(name)
        if not data or "요구사항 ID" not in data[0]:
            continue
        headers = [str(h) for h in data[0]]
        for row in data[1:]:
            rec = dict(zip(headers, row, strict=False))
            rid = rec.get("요구사항 ID")
            if rid:
                out[str(rid)] = rec
    return out


def _looks_like_req_id(token: str, prefixes: dict[str, str]) -> bool:
    pre = token.split("-")[0]
    return pre in set(prefixes.values()) or pre in {"SFR", "SNR", "FR", "NFR", "CON", "EVA", "SUB"}


def _ids_from_sheets(sheets: dict[str, list[list[Any]]], names: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for n in names:
        data = sheets.get(n)
        if not data or "요구사항 ID" not in data[0]:
            continue
        i = data[0].index("요구사항 ID")
        out |= {str(r[i]) for r in data[1:] if r[i]}
    return out


def _kind_files(inp: QaInputs, *kinds: DeliverableKind) -> list[str]:
    return [inp.deliverables[k].file_path for k in kinds if k in inp.deliverables]


def _deck_paths(inp: QaInputs) -> list[tuple[str, Path]]:
    """(라벨, 절대 경로) — 제출용·발표용 덱 중 존재하는 것."""
    out: list[tuple[str, Path]] = []
    for kind, label in (
        (DeliverableKind.SUBMISSION_PPTX, "제출용"),
        (DeliverableKind.PRESENTATION_PPTX, "발표용"),
    ):
        d = inp.deliverables.get(kind)
        if d is None:
            continue
        try:
            path = inp.paths.resolve_output(d.file_path)
        except PathSecurityError:
            continue
        if path.exists():
            out.append((label, path))
    return out


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if hasattr(v, "date") and callable(v.date):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _is_filled(cell: Any) -> bool:
    try:
        fill = cell.fill
        rgb = getattr(fill.fgColor, "rgb", None)
        return bool(
            fill and fill.fill_type == "solid" and rgb and rgb not in ("00000000", "FFFFFFFF")
        )
    except Exception:  # noqa: BLE001
        return False
