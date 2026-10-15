"""제안서 목차 결정 (결정적).

우선순위: ① 에이전트(proposal_writer) 문안의 섹션 → ② RFP가 제시한 제안서 목차(추출 블록에서 '제안서 목차/구성/작성 지침'
제목 아래 항목) → ③ 평가 기준·과제 목적·보유 데이터로 선택한 기본 목차. 해당 과제에 필요한 항목만 넣는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from proposal_agent.generators.base import GenerationContext
from proposal_agent.models import BlockType, ExtractedBlock, RequirementType

_TOC_HEADING = re.compile(r"제안서\s*(목차|구성|작성\s*(지침|방법|요령)|양식)", re.IGNORECASE)
_TOC_ITEM = re.compile(r"^\s*(\d+(\.\d+)*\.?|[가-힣]\.|[IVX]+\.|[-•·▪])\s*(.+)$")


@dataclass
class OutlineSection:
    key: str
    title: str
    source: str  # agent | rfp_toc | default
    reason: str = ""
    data_refs: list[str] = field(default_factory=list)
    chapter: str = ""  # 에이전트가 지정한 장 (예: "Ⅲ. 사업수행 부문")
    section: str = ""  # 에이전트가 지정한 절 (예: "2. 제안 시스템 주요 기능")
    number: str = ""  # 에이전트가 지정한 소절 번호 (예: "2.1")
    lead: str = ""  # 리드 메시지
    agent_index: int | None = None  # proposal_content.sections 의 인덱스
    guide: list[str] = field(default_factory=list)  # RFP 작성방법 (빈 절 자리표시용)


@dataclass
class SectionPlan:
    number: int
    title: str
    guide: list[str] = field(default_factory=list)
    subsections: list[OutlineSection] = field(default_factory=list)


@dataclass
class ChapterPlan:
    numeral: str
    title: str
    sections: list[SectionPlan] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "numeral": self.numeral,
            "title": self.title,
            "sections": [
                {
                    "number": s.number,
                    "title": s.title,
                    "subsections": [
                        {"key": o.key, "title": o.title, "source": o.source} for o in s.subsections
                    ],
                }
                for s in self.sections
            ],
        }


def rfp_toc_from_blocks(blocks: list[ExtractedBlock]) -> list[str]:
    """RFP 추출 블록에서 제안서 목차 항목을 찾는다. 없으면 []."""
    items: list[str] = []
    capture = False
    for b in sorted(blocks, key=lambda x: x.order):
        if b.block_type in (BlockType.HEADING, BlockType.TITLE):
            if _TOC_HEADING.search(b.text):
                capture = True
                continue
            if capture:
                break
        elif capture and b.block_type in (
            BlockType.LIST_ITEM,
            BlockType.PARAGRAPH,
            BlockType.TABLE,
        ):
            if b.block_type == BlockType.TABLE and b.table_cells:
                for row in b.table_cells:
                    text = " ".join(c for c in row if c).strip()
                    if text:
                        items.append(text[:60])
                continue
            for line in b.text.splitlines():
                m = _TOC_ITEM.match(line)
                if m:
                    items.append(m.group(3).strip()[:60])
    return [i for i in items if i][:30]


DEFAULT_KEYS: tuple[tuple[str, str], ...] = (
    ("purpose", "사업 목적 및 이해"),
    ("current", "현황 및 문제점"),
    ("requirements", "요구사항 대응"),
    ("strategy", "추진 전략"),
    ("system_diagram", "시스템 구성도"),
    ("sw_diagram", "SW 구성도"),
    ("service_diagram", "서비스 구성도"),
    ("architecture", "기술 아키텍처 및 구현 방안"),
    ("security", "보안"),
    ("testing", "테스트 및 품질 보증"),
    ("operations", "운영 및 유지보수"),
    ("schedule", "추진 일정"),
    ("organization", "추진 조직 및 인력"),
    ("risk", "위험 관리"),
    ("evaluation", "평가 기준 대응"),
)


ESSENTIAL_KEYS = ("requirements", "system_diagram", "schedule", "organization")


def default_outline(ctx: GenerationContext) -> list[OutlineSection]:
    reqs = ctx.requirements
    nonf = [r for r in reqs if r.type == RequirementType.NON_FUNCTIONAL]
    has_security = any(
        r.category.value == "security" or "보안" in r.name or "암호" in r.name for r in reqs
    )
    has_ops = any(
        r.category.value in ("availability", "operability")
        or any(k in r.name for k in ("운영", "유지보수", "가용", "백업"))
        for r in nonf
    )
    has_eval = bool((ctx.analysis or {}).get("evaluation_criteria")) or any(
        r.type == RequirementType.EVALUATION for r in reqs
    )
    has_current = bool((ctx.analysis or {}).get("client_goals")) or bool(
        (ctx.analysis or {}).get("overview")
    )
    out: list[OutlineSection] = []
    for key, title in DEFAULT_KEYS:
        include, reason = True, "기본 목차"
        if key == "current":
            include, reason = has_current, "RFP 분석의 사업 개요·목표가 있을 때"
        elif key == "security":
            include, reason = has_security, "보안 요구사항이 있을 때"
        elif key == "operations":
            include, reason = has_ops, "운영·가용성 요구사항이 있을 때"
        elif key == "evaluation":
            include, reason = has_eval, "RFP 평가 기준이 있을 때"
        if include:
            out.append(OutlineSection(key=key, title=title, source="default", reason=reason))
    return out


def map_rfp_toc(items: list[str], ctx: GenerationContext) -> list[OutlineSection]:
    """RFP 목차 문구를 내부 섹션 키에 매핑한다. 매핑되지 않는 항목은 generic으로 둔다."""
    keyword_map = (
        ("purpose", ("목적", "이해", "개요", "배경")),
        ("current", ("현황", "문제점", "분석")),
        ("requirements", ("요구사항", "요구 사항", "대응")),
        ("strategy", ("전략", "방향", "방안")),
        ("system_diagram", ("시스템 구성", "하드웨어", "HW")),
        ("sw_diagram", ("SW", "소프트웨어", "S/W")),
        ("service_diagram", ("서비스 구성", "서비스")),
        ("architecture", ("아키텍처", "기술", "구현")),
        ("security", ("보안",)),
        ("testing", ("시험", "테스트", "품질")),
        ("operations", ("운영", "유지보수", "교육", "이관")),
        ("schedule", ("일정", "공정")),
        ("organization", ("조직", "인력", "수행 인력")),
        ("risk", ("위험", "리스크")),
        ("evaluation", ("평가",)),
    )
    out: list[OutlineSection] = []
    used: set[str] = set()
    for i, text in enumerate(items):
        key = next(
            (
                k
                for k, kws in keyword_map
                if any(kw.lower() in text.lower() for kw in kws) and k not in used
            ),
            None,
        )
        if key:
            used.add(key)
            out.append(
                OutlineSection(key=key, title=text, source="rfp_toc", reason="RFP 제안서 목차")
            )
        else:
            out.append(
                OutlineSection(
                    key=f"generic_{i}",
                    title=text,
                    source="rfp_toc",
                    reason="RFP 목차 항목 (내용은 사람 작성 필요)",
                )
            )
    for key in ("system_diagram", "sw_diagram", "service_diagram"):
        if key not in used:
            out.append(
                OutlineSection(
                    key=key, title=dict(DEFAULT_KEYS)[key], source="default", reason="필수 구성도"
                )
            )
    return out


# 에이전트 스키마(ProposalSection.slide_group)의 이름을 생성기 슬라이드 키로 맞춘다.
SLIDE_GROUP_ALIAS: dict[str, str] = {
    "staffing": "organization",
    "quality": "testing",
    "cover": "purpose",
    "toc": "purpose",
}


def canonical_key(slide_group: str) -> str:
    return SLIDE_GROUP_ALIAS.get(slide_group, slide_group)


def decide_outline(ctx: GenerationContext, rfp_toc: list[str]) -> list[OutlineSection]:
    content = ctx.proposal_content or {}
    sections = content.get("sections") or []
    if sections:
        agent_sections = [
            OutlineSection(
                key=canonical_key(str(s.get("slide_group", f"agent_{i}"))),
                title=str(s.get("title", ""))[:60],
                source="agent",
                reason="제안서 작성 에이전트 문안",
                data_refs=list(s.get("data_refs", [])),
                chapter=str(s.get("chapter", "") or ""),
                section=str(s.get("section", "") or ""),
                number=str(s.get("number", "") or ""),
                lead=str(s.get("lead_message", "") or ""),
                agent_index=i,
            )
            for i, s in enumerate(sections)
        ]
        # 에이전트 문안이 다루지 않은 데이터 기반 필수 섹션(요구사항 표·구성도·일정·인력)은 코드가 보강한다
        have = {sec.key for sec in agent_sections}
        for key in ESSENTIAL_KEYS:
            if key not in have:
                agent_sections.append(
                    OutlineSection(
                        key=key,
                        title=dict(DEFAULT_KEYS)[key],
                        source="default",
                        reason="필수 섹션 보강 (기준 데이터)",
                    )
                )
        return agent_sections
    if len(rfp_toc) >= 3:
        return map_rfp_toc(rfp_toc, ctx)
    return default_outline(ctx)


# --- 장 계획 (Phase 12): RFP 지정 목차 → 템플릿 샘플 목차 → 단일 장 ----------------------------------

SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "purpose": ("배경", "목적", "이해", "개요"),
    "understanding": ("배경", "목적", "이해", "개요"),
    "current": ("현황", "문제"),
    "requirements": ("요구사항", "요구 사항", "범위"),
    "strategy": ("전략", "특장점", "특징", "장점"),
    "system_diagram": ("시스템 구성", "장비", "하드웨어", "HW", "H/W"),
    "sw_diagram": ("소프트웨어", "SW", "S/W"),
    "service_diagram": ("서비스 구성", "서비스"),
    "architecture": ("아키텍처", "기술", "구현", "주요 기능", "기능"),
    "security": ("보안",),
    "testing": ("품질", "테스트", "시험"),
    "operations": ("유지보수", "교육", "운영", "안정화", "지원", "인수"),
    "schedule": ("일정", "공정"),
    "organization": ("조직", "인력"),
    "risk": ("위험", "리스크"),
    "evaluation": ("평가",),
}
CHAPTER_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("purpose", "understanding", "current", "strategy", "evaluation"), ("개요", "배경", "이해")),
    (("testing", "security"), ("품질", "성능", "보안")),
    (
        (
            "requirements",
            "system_diagram",
            "sw_diagram",
            "service_diagram",
            "architecture",
            "security",
            "testing",
        ),
        ("수행", "기술", "시스템", "구현"),
    ),
    (("schedule", "organization", "risk"), ("관리", "조직", "일정")),
    (("operations",), ("지원", "운영", "유지보수", "교육")),
)


def _norm(text: str) -> str:
    return re.sub(r"[\s.．·,()\[\]/]", "", text).lower()


def _strip_number(title: str) -> str:
    return re.sub(r"^\s*(\d+(\.\d+)*\.?|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.?|[IVX]+\.)\s*", "", title).strip()


def _chapter_matches(sec: OutlineSection, ch: ChapterPlan) -> bool:
    if not sec.chapter:
        return False
    want = sec.chapter.strip()
    numeral = re.match(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)", want)
    if numeral and ch.numeral and numeral.group(1) == ch.numeral:
        return True
    a, b = _norm(_strip_number(want)), _norm(ch.title)
    return bool(a and b and (a in b or b in a))


def _locate(
    sec: OutlineSection, chapters: list[ChapterPlan]
) -> tuple[ChapterPlan, SectionPlan] | None:
    # 1) 에이전트가 장·절 번호를 지정한 경우
    ch = next((c for c in chapters if _chapter_matches(sec, c)), None)
    if ch is not None:
        no = sec.number.split(".")[0] if sec.number else ""
        target = next((s for s in ch.sections if no and str(s.number) == no), None)
        if target is None and sec.section:
            want = _norm(_strip_number(sec.section))
            target = next((s for s in ch.sections if want and want in _norm(s.title)), None)
        if target is None:
            title = _strip_number(sec.section) if sec.section else sec.title
            target = SectionPlan(number=len(ch.sections) + 1, title=title)
            ch.sections.append(target)
        return ch, target
    # 2) 절 제목 키워드
    kws = SECTION_KEYWORDS.get(sec.key, ())
    title_words = (
        ()
        if not sec.key.startswith(("generic", "agent"))
        else tuple(w for w in re.split(r"\s+", _strip_number(sec.title)) if len(w) >= 2)
    )
    best: tuple[int, ChapterPlan, SectionPlan] | None = None
    for c in chapters:
        for sp in c.sections:
            score = sum(1 for k in kws if k.lower() in sp.title.lower()) * 2 + sum(
                1 for w in title_words if w in sp.title
            )
            if score and (best is None or score > best[0]):
                best = (score, c, sp)
    if best:
        return best[1], best[2]
    # 3) 장 제목 힌트 → 그 장에 새 절
    for keys, hints in CHAPTER_HINTS:
        if sec.key in keys:
            cand = next((x for x in chapters if any(h in x.title for h in hints)), None)
            if cand is not None:
                new_sp = SectionPlan(number=len(cand.sections) + 1, title=sec.title)
                cand.sections.append(new_sp)
                return cand, new_sp
    return None


def plan_chapters(
    outline: list[OutlineSection],
    toc_tree: list[dict[str, Any]] | None,
    template_chapters: list[Any] | None = None,
) -> list[ChapterPlan]:
    """목차 항목(outline)을 장/절 아래 소절로 배치한다.

    장·절의 뼈대는 ① RFP 지정 목차 트리 ② 템플릿 샘플의 장·절 ③ 단일 장 순으로 정한다. 내용이 없는
    RFP 지정 절은 비우지 않고 "사람 작성 필요" 자리표시 소절을 넣어 목차가 RFP와 같게 유지된다.
    """
    chapters: list[ChapterPlan] = []
    for ch in toc_tree or []:
        chapters.append(
            ChapterPlan(
                numeral=str(ch.get("numeral", "")),
                title=str(ch.get("title", "")),
                sections=[
                    SectionPlan(
                        number=i + 1,
                        title=_strip_number(str(sec.get("title", ""))),
                        guide=list(sec.get("guide", [])),
                    )
                    for i, sec in enumerate(ch.get("sections", []))
                ],
            )
        )
    if not chapters:
        for tc in template_chapters or []:
            if not (getattr(tc, "sections", None) or getattr(tc, "title", "")):
                continue
            # 템플릿 샘플에서는 장(로마숫자·제목)만 가져온다. 샘플의 절 목록은 그 고객 과제의 내용이므로
            # 새 제안에 복사하지 않고, 절은 기준 데이터(outline)에서 장 제목 힌트로 만든다.
            chapters.append(
                ChapterPlan(
                    numeral=str(getattr(tc, "numeral", "")),
                    title=str(getattr(tc, "title", "")),
                )
            )
    if not chapters:
        single = ChapterPlan(numeral="", title="제안서")
        for i, sec in enumerate(outline):
            single.sections.append(SectionPlan(number=i + 1, title=sec.title, subsections=[sec]))
        return [single]
    for sec in outline:
        hit = _locate(sec, chapters)
        if hit is None:
            # 맞는 장이 없으면 마지막 장에 새 절
            last = chapters[-1]
            sp = SectionPlan(number=len(last.sections) + 1, title=sec.title)
            last.sections.append(sp)
            hit = (last, sp)
        hit[1].subsections.append(sec)
    for cp in chapters:
        for sp in cp.sections:
            if not sp.subsections:
                sp.subsections.append(
                    OutlineSection(
                        key="placeholder",
                        title=sp.title,
                        source="rfp_toc",
                        reason="RFP 지정 목차 항목 — 내용은 사람 작성 필요",
                        guide=list(sp.guide),
                    )
                )
    return chapters
