"""RFP 구조 프로파일 (결정적 코드).

고객사마다 RFP 양식이 다르지만 공통으로 나타나는 구조를 추출 블록에서 찾아 요구사항 분석에 쓴다.

- 절(section) 종류 판별: 사업 개요 / 운영 현황 / 구축 계획 / 사업 범위 / 요구사항 / 제안서 작성요령·목차 / 제출·입찰 안내 / 평가 / 별첨
- RFP 자체 요구사항 ID(예: ``SFR-001``, ``PCR-002``) 체계 추론과 **요구사항 색인**(ID·명칭·분류·블록)
- 세부 요구사항 표의 세로 병합 라벨 잡음("요구 사항 세부 상세 내용 설명") 제거
- 제안서 목차(작성요령 절), 평가 항목·배점, 제출 서류 목록 추출
- 각 블록에 ``section_kind``·``rfp_requirement_id``를 태깅해 청크 분할·추출 프롬프트·커버리지 검사에 쓴다
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models import BlockType, ExtractedBlock

SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("evaluation", re.compile(r"평가\s*(방법|기준|항목)|낙찰자\s*결정|배점|심사\s*기준")),
    (
        "submission",
        re.compile(
            r"제출\s*서류|입찰\s*참가|제안\s*안내|제안서\s*제출|제안\s*설명회|입찰\s*안내|참가\s*자격|제출\s*조건|제출\s*기한|제출\s*방법"
        ),
    ),
    (
        "proposal_guide",
        re.compile(
            r"제안서\s*작성|작성\s*요령|작성\s*지침|제안서\s*목차|작성\s*방법|제안서의?\s*효력|유의\s*사항"
        ),
    ),
    ("appendix", re.compile(r"^\s*\[?\s*(별첨|별지|별표|부록|첨부|서식)")),
    (
        "requirements",
        re.compile(
            r"요구\s*사항|제안\s*요건|과업\s*내용|기능\s*요건|요구\s*조건|제약\s*사항|제약\s*조건"
        ),
    ),
    ("scope", re.compile(r"사업\s*범위|과업\s*범위|추진\s*범위|구축\s*범위")),
    ("plan", re.compile(r"구축\s*계획|추진\s*일정|추진\s*체계|추진\s*계획|사업\s*일정")),
    ("current_state", re.compile(r"운영\s*현황|시스템\s*현황|현황\s*및|현황$")),
    (
        "overview",
        re.compile(
            r"사업\s*개요|추진\s*배경|사업\s*목적|사업명|사업\s*예산|사업\s*기간|업체\s*선정"
        ),
    ),
)
SECTION_LABELS = {
    "overview": "사업 개요",
    "current_state": "운영 현황",
    "plan": "구축 계획·일정",
    "scope": "사업 범위",
    "requirements": "요구사항",
    "proposal_guide": "제안서 작성요령·목차",
    "submission": "제출·입찰 안내",
    "evaluation": "평가 기준",
    "appendix": "별첨·서식",
    "other": "기타",
}
RFP_ID_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2,5})-(\d{2,4})(?!\d)")
ID_HEADER_RE = re.compile(
    r"(고유\s*번호|요구사항\s*ID|요구사항\s*번호|ID)\s*[:：|]?\s*(?P<id>[A-Z]{2,5}-\d{2,4})"
)
NAME_RE = re.compile(r"(요구사항\s*)?(명칭|요구사항명|제목)\s*[:：|]?\s*(?P<name>[^|\n]{2,80})")
# 세로 병합 셀 라벨: 줄 전체가 이 토큰들로만 이루어지면 잡음
LABEL_TOKENS = {
    "요구",
    "사항",
    "세부",
    "상세",
    "내용",
    "설명",
    "요구사항",
    "고유번호",
    "명칭",
    "정의",
    "구분",
    "분류",
}
TOC_ROMAN_RE = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,4})\s*[.．]\s*(?P<title>\S.{1,60})$")
TOC_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*(?P<title>[^○※\-].{1,60})$")
POINTS_RE = re.compile(r"(?P<name>[가-힣A-Za-z·/()\s]{2,40}?)\s*(?P<pts>\d{1,3})\s*$")
SUBMISSION_ITEM_RE = re.compile(r"^\s*([-•·▪○□■※]|\d+[.)]|[가-힣][.)])\s*(?P<item>.{3,100})$")


class SectionSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    heading: str
    start_order: int
    end_order: int
    page_start: int | None = None
    page_end: int | None = None
    block_count: int = 0


class RfpRequirementEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfp_id: str
    name: str = ""
    category: str = ""
    block_ids: list[str] = Field(default_factory=list)
    page: int | None = None


class RfpProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[SectionSpan] = Field(default_factory=list)
    id_prefixes: dict[str, int] = Field(default_factory=dict, description="접두사 → 고유 ID 수")
    id_width: int | None = None
    requirement_index: list[RfpRequirementEntry] = Field(default_factory=list)
    proposal_toc: list[str] = Field(default_factory=list)
    evaluation_items: list[dict[str, Any]] = Field(
        default_factory=list, description="[{name, points}]"
    )
    submission_items: list[str] = Field(default_factory=list)
    block_kinds: dict[str, str] = Field(default_factory=dict, description="block_id → section kind")
    block_rfp_ids: dict[str, str] = Field(
        default_factory=dict, description="block_id → RFP 요구사항 ID"
    )
    noise_lines_removed: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def has_requirement_ids(self) -> bool:
        return bool(self.requirement_index)

    def kinds_present(self) -> list[str]:
        seen: list[str] = []
        for s in self.sections:
            if s.kind not in seen:
                seen.append(s.kind)
        return seen

    def summary_text(self) -> str:
        parts = [
            "절 구성: "
            + ", ".join(
                f"{SECTION_LABELS.get(s.kind, s.kind)}({s.heading[:20]})"
                for s in self.sections[:12]
            ),
        ]
        if self.id_prefixes:
            parts.append(
                "RFP 요구사항 ID 체계: "
                + ", ".join(f"{p} {n}건" for p, n in self.id_prefixes.items())
                + f" (총 {len(self.requirement_index)}건)"
            )
        if self.proposal_toc:
            parts.append("제안서 목차 지정: " + " / ".join(self.proposal_toc[:12]))
        if self.evaluation_items:
            parts.append(
                "평가 항목: "
                + ", ".join(f"{e['name']}({e['points']})" for e in self.evaluation_items[:12])
            )
        if self.submission_items:
            parts.append(f"제출 서류·조건 {len(self.submission_items)}건")
        return "\n".join(parts)


# --- 잡음 제거 ----------------------------------------------------------------------------------


def _is_label_line(line: str) -> bool:
    toks = [t for t in re.split(r"[\s|·]+", line.strip()) if t]
    return bool(toks) and all(t in LABEL_TOKENS for t in toks)


def _leading_vertical_labels(cells: list[str]) -> int:
    """행 앞쪽의 세로 병합 라벨 셀 수. 라벨 셀 뒤에 또 라벨 셀이 오면 앞 것은 세로 라벨(잡음)로 본다.

    "요구사항 | 고유번호 | SFR-001" → 1 ("요구사항"만 제거, "고유번호"는 가로 라벨이라 보존)
    "정의 | 사건 관리" → 0
    """
    n = 0
    while n + 1 < len(cells) and _is_label_line(cells[n]) and _is_label_line(cells[n + 1]):
        n += 1
    return n


def clean_text(text: str) -> tuple[str, int]:
    """세로 병합 라벨만 있는 줄을 제거하고, 표 행 앞의 세로 라벨 셀을 지운다. (정리된 텍스트, 제거 수)

    가로 라벨("고유번호", "정의", "내용" 등 값 바로 앞의 셀)은 의미가 있으므로 남긴다.
    """
    out: list[str] = []
    removed = 0
    for line in text.splitlines():
        if _is_label_line(line):
            removed += 1
            continue
        if " | " in line:
            cells = line.split(" | ")
            skip = _leading_vertical_labels(cells)
            if skip:
                removed += 1
                line = " | ".join(cells[skip:])
            if not line.strip():
                continue
        out.append(line)
    return "\n".join(out), removed


def clean_cells(cells: list[list[str]]) -> list[list[str]]:
    out: list[list[str]] = []
    for row in cells:
        skip = _leading_vertical_labels([c or "" for c in row])
        out.append(["" if i < skip else c for i, c in enumerate(row)])
    return out


# --- 프로파일 -----------------------------------------------------------------------------------


def classify_heading(text: str) -> str | None:
    t = text.strip()
    if len(t) > 80:
        return None
    for kind, pat in SECTION_PATTERNS:
        if pat.search(t):
            return kind
    return None


def profile_blocks(blocks: list[ExtractedBlock], *, apply: bool = True) -> RfpProfile:
    """블록 목록에서 구조 프로파일을 만든다. ``apply=True``면 블록의 텍스트 정리·태그를 제자리에서 갱신한다."""
    prof = RfpProfile()
    ordered = sorted(blocks, key=lambda b: b.order)
    # 1) 절 구간: 제목 블록(상위 2단계)마다 종류 판별, 다음 제목까지가 구간
    current_kind = "other"
    current: SectionSpan | None = None
    for b in ordered:
        is_heading = b.block_type in (BlockType.HEADING, BlockType.TITLE, BlockType.APPENDIX)
        if is_heading and (
            b.heading_level is None or b.heading_level <= 2 or b.block_type == BlockType.APPENDIX
        ):
            kind = classify_heading(b.text)
            if kind is not None:
                if current is not None:
                    current.end_order = b.order - 1
                current_kind = kind
                current = SectionSpan(
                    kind=kind,
                    heading=b.text.strip()[:80],
                    start_order=b.order,
                    end_order=b.order,
                    page_start=b.location.page,
                    page_end=b.location.page,
                )
                prof.sections.append(current)
        prof.block_kinds[b.id] = current_kind
        if current is not None:
            current.end_order = b.order
            current.block_count += 1
            if b.location.page is not None:
                current.page_end = b.location.page
    # 2) 잡음 정리 + RFP ID 태깅 (요구사항 구간 우선, 없으면 전체)
    req_blocks = [b for b in ordered if prof.block_kinds.get(b.id) == "requirements"]
    scan = req_blocks or ordered
    last_id: str | None = None
    entries: dict[str, RfpRequirementEntry] = {}
    all_ids: list[str] = []
    for b in scan:
        text = b.text
        if apply:
            cleaned, removed = clean_text(text)
            if removed:
                prof.noise_lines_removed += removed
                b.text = cleaned
                if b.table_cells:
                    b.table_cells = clean_cells(b.table_cells)
            text = b.text
        ids = [f"{p}-{n}" for p, n in RFP_ID_RE.findall(text)]
        header = ID_HEADER_RE.search(text)
        if header:
            last_id = header.group("id")
        elif ids and (b.block_type == BlockType.TABLE or len(ids) == 1):
            # 표 한 행에 ID가 하나면 그 ID의 블록, 목록 표(여러 ID)면 색인만 갱신
            if len(ids) == 1:
                last_id = ids[0]
        for rid in ids:
            all_ids.append(rid)
            entry = entries.setdefault(
                rid,
                RfpRequirementEntry(
                    rfp_id=rid, category=b.location.section or "", page=b.location.page
                ),
            )
            if not entry.name:
                entry.name = _name_near(text, rid)
        if (
            last_id
            and ids
            and last_id in ids
            or (
                last_id
                and not ids
                and prof.block_kinds.get(b.id) == "requirements"
                and b.block_type != BlockType.HEADING
            )
        ):
            prof.block_rfp_ids[b.id] = last_id
            if last_id in entries and b.id not in entries[last_id].block_ids:
                entries[last_id].block_ids.append(b.id)
        if (
            b.block_type == BlockType.HEADING
            and b.heading_level is not None
            and b.heading_level <= 2
        ):
            last_id = None  # 새 절이 시작되면 ID 연속 적용을 끊는다
    if all_ids:
        counts = Counter(p.split("-")[0] for p in set(all_ids))
        prof.id_prefixes = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        widths = Counter(len(i.split("-")[1]) for i in set(all_ids))
        prof.id_width = widths.most_common(1)[0][0]
        prof.requirement_index = sorted(
            entries.values(), key=lambda e: (e.rfp_id.split("-")[0], int(e.rfp_id.split("-")[1]))
        )
    # 3) 제안서 목차 / 평가 / 제출
    prof.proposal_toc = _proposal_toc(ordered, prof.block_kinds)
    prof.evaluation_items = _evaluation_items(ordered, prof.block_kinds)
    prof.submission_items = _submission_items(ordered, prof.block_kinds)
    if apply:
        for b in ordered:
            b.section_kind = prof.block_kinds.get(b.id)
            b.rfp_requirement_id = prof.block_rfp_ids.get(b.id)
    if not prof.sections:
        prof.warnings.append(
            "절 제목을 인식하지 못해 구조 프로파일이 비어 있습니다 (제목 번호 체계가 없는 문서)."
        )
    if req_blocks and not prof.requirement_index:
        prof.warnings.append(
            "요구사항 절은 있으나 RFP 자체 ID(예: SFR-001)를 찾지 못했습니다. 문장 단위로만 추출됩니다."
        )
    return prof


def _name_near(text: str, rid: str) -> str:
    """ID 옆(같은 줄)의 명칭을 우선 취하고, 없으면 '명칭' 라벨이 붙은 셀을 취한다. 라벨·ID는 제외."""
    # 목록 표: "PCR-001 | 기본 요구사항" 또는 "PCR-001 기본 요구사항" (같은 줄만)
    m2 = re.search(re.escape(rid) + r"[ \t]*[|]?[ \t]*(?P<name>[^|\n]{2,80})", text)
    if m2:
        cand = m2.group("name").strip()
        if cand and not RFP_ID_RE.match(cand) and not _is_label_line(cand):
            return cand[:80]
    for m in NAME_RE.finditer(text):
        name = m.group("name").strip(" |:：")
        if name and not RFP_ID_RE.fullmatch(name) and not _is_label_line(name):
            return name[:80]
    return ""


def _proposal_toc(ordered: list[ExtractedBlock], kinds: dict[str, str]) -> list[str]:
    items: list[str] = []
    for b in ordered:
        if kinds.get(b.id) != "proposal_guide" or b.block_type in (
            BlockType.HEADING,
            BlockType.TITLE,
        ):
            continue
        rows = []
        if b.table_cells:
            # 목차 표: 행의 첫 번째 비어 있지 않은 셀이 목차 항목, 나머지는 작성 내용 설명
            rows = [next((c.strip() for c in row if c and c.strip()), "") for row in b.table_cells]
        else:
            rows = b.text.splitlines()
        for line in rows:
            first = line.split(" | ")[0].strip()
            m = TOC_ROMAN_RE.match(first) or TOC_NUM_RE.match(first)
            if m:
                title = re.split(r"\s[○※]", m.group("title"))[0].strip()
                if title and title not in items:
                    items.append(title[:60])
    return items[:40]


def _evaluation_items(ordered: list[ExtractedBlock], kinds: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for b in ordered:
        if kinds.get(b.id) != "evaluation":
            continue
        rows: list[list[str]] = b.table_cells or [[ln] for ln in b.text.splitlines()]
        for row in rows:
            cells = [c.strip() for c in row if c and c.strip()]
            if len(cells) >= 2 and re.fullmatch(r"\d{1,3}", cells[-1]):
                name = (
                    cells[0]
                    if not re.fullmatch(r"\d{1,3}", cells[0])
                    else (cells[1] if len(cells) > 2 else "")
                )
                pts = int(cells[-1])
                if name and 0 < pts <= 100:
                    items.append({"name": name[:40], "points": pts})
            elif len(cells) == 1:
                m = POINTS_RE.search(cells[0])
                if m and 0 < int(m.group("pts")) <= 100 and not re.search(r"\d{4}", cells[0]):
                    items.append(
                        {"name": m.group("name").strip()[:40], "points": int(m.group("pts"))}
                    )
    # 중복 제거 (같은 이름·배점)
    seen: set[tuple[str, int]] = set()
    out = []
    for it in items:
        key = (it["name"], it["points"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out[:60]


def _submission_items(ordered: list[ExtractedBlock], kinds: dict[str, str]) -> list[str]:
    items: list[str] = []
    for b in ordered:
        if kinds.get(b.id) != "submission":
            continue
        for line in b.text.splitlines():
            m = SUBMISSION_ITEM_RE.match(line)
            if m:
                items.append(m.group("item").strip()[:100])
    return items[:60]


__all__ = [
    "RfpProfile",
    "RfpRequirementEntry",
    "SECTION_LABELS",
    "SectionSpan",
    "classify_heading",
    "clean_cells",
    "clean_text",
    "profile_blocks",
]
