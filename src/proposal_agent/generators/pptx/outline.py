"""제안서 목차 결정 (결정적).

우선순위: ① 에이전트(proposal_writer) 문안의 섹션 → ② RFP가 제시한 제안서 목차(추출 블록에서 '제안서 목차/구성/작성 지침'
제목 아래 항목) → ③ 평가 기준·과제 목적·보유 데이터로 선택한 기본 목차. 해당 과제에 필요한 항목만 넣는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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
        return [
            OutlineSection(
                key=canonical_key(str(s.get("slide_group", f"agent_{i}"))),
                title=str(s.get("title", ""))[:60],
                source="agent",
                reason="제안서 작성 에이전트 문안",
                data_refs=list(s.get("data_refs", [])),
            )
            for i, s in enumerate(sections)
        ]
    if len(rfp_toc) >= 3:
        return map_rfp_toc(rfp_toc, ctx)
    return default_outline(ctx)
