"""슬라이드 디자인 명세 (Phase 19).

덱을 만드는 동안 소절마다 기록한 범위(``GenerationContext.slide_specs``)와 실제 PPTX를 합쳐
슬라이드별 명세 JSON을 만든다: 결론형 제목(key_message)·목적·독자·근거·앞뒤 연결·계획 레이아웃·실제 렌더링 요소.
파일 기준이 우선이므로 요구사항 ID·표·도형 수는 덱에서 다시 읽는다.
"""

from __future__ import annotations

import io
from collections import Counter
from typing import Any

from pptx import Presentation

from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.pptx.outline import OutlineSection
from proposal_agent.generators.pptx.pagemap import ID_RE, _texts

EVIDENCE_KIND_LABEL = {
    "rfp": "RFP",
    "requirement": "요구사항",
    "research": "기술 조사",
    "architecture": "구성 요소",
    "wbs": "WBS",
    "staffing": "인력",
    "reference_doc": "참고 문서",
    "assumption": "전제(확인 필요)",
}
AUDIENCE_LABEL = {
    "evaluator": "평가위원",
    "business": "현업",
    "technical": "기술 심사",
    "executive": "경영진",
}


def evidence_line(e: dict[str, Any]) -> str:
    kind = EVIDENCE_KIND_LABEL.get(str(e.get("kind", "")), str(e.get("kind", "")))
    ref = str(e.get("ref", "") or "")
    text = str(e.get("text", "") or "")
    head = " ".join(x for x in (kind, ref) if x)
    return f"근거: {head}" + (f" — {text}" if text else "")


def section_entry(
    sec: OutlineSection, agent: dict[str, Any] | None, first: int, last: int
) -> dict[str, Any]:
    """소절 하나의 명세 항목. first/last 는 1부터 시작하는 슬라이드 번호(포함)."""
    a = agent or {}
    visual = a.get("visual") if isinstance(a.get("visual"), dict) else {}
    return {
        "key": sec.key,
        "title": sec.title,
        "source": sec.source,
        "chapter": a.get("chapter") or sec.chapter,
        "section": a.get("section") or sec.section,
        "number": a.get("number") or sec.number,
        "slide_from": first,
        "slide_to": last,
        "key_message": str(a.get("key_message", "") or ""),
        "lead_message": str(a.get("lead_message", "") or sec.lead or ""),
        "purpose": str(a.get("purpose", "") or ""),
        "audience": str(a.get("audience", "") or ""),
        "layout_type": str(a.get("layout_type", "") or ""),
        "visual_kind": str(visual.get("kind", "") or "") if visual else "",
        "evidence": [dict(e) for e in a.get("evidence", []) or []],
        "data_refs": [str(x) for x in (a.get("data_refs") or sec.data_refs or [])],
        "requirement_ids": [str(x) for x in a.get("requirement_ids", []) or []],
        "links_prev": [str(x) for x in a.get("links_prev", []) or []],
        "links_next": [str(x) for x in a.get("links_next", []) or []],
        "terms": [str(x) for x in a.get("terms", []) or []],
        "has_tech_detail": bool(a.get("tech_detail")),
        "feasibility_basis": [str(x) for x in a.get("feasibility_basis", []) or []],
    }


def code_entry(key: str, title: str, first: int, last: int) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "source": "code",
        "chapter": "",
        "section": "",
        "number": "",
        "slide_from": first,
        "slide_to": last,
        "key_message": "",
        "lead_message": "",
        "purpose": "",
        "audience": "",
        "layout_type": "",
        "visual_kind": "",
        "evidence": [],
        "data_refs": [],
        "requirement_ids": [],
        "links_prev": [],
        "links_next": [],
        "terms": [],
        "has_tech_detail": False,
        "feasibility_basis": [],
    }


def _slide_title(slide: Any, hint: str = "") -> str:
    """슬라이드 제목 텍스트. 템플릿 머리글이 2단(장 제목 + 소절 제목)이면 소절 제목(hint)이 든 상자를 고른다."""
    try:
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            t = slide.shapes.title.text_frame.text.strip()
            if t:
                return t
    except (AttributeError, KeyError):
        pass
    cands = [
        (int(getattr(sh, "top", 0) or 0), sh.text_frame.text.strip())
        for sh in slide.shapes
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip()
    ]
    cands.sort(key=lambda x: x[0])
    key = hint.strip()[:12]
    if key:
        for _top, text in cands:
            if key in text:
                return text.split("\n")[0].strip()[:80]
    # 위에서부터, 장 번호 라벨("Ⅱ", "01")처럼 2자 이하인 상자는 건너뛴다
    for _top, text in cands:
        first = text.split("\n")[0].strip()
        if len(first) > 2:
            return first[:80]
    return cands[0][1].split("\n")[0][:80] if cands else ""


def _shape_counts(shapes: Any, depth: int = 0) -> Counter[str]:
    c: Counter[str] = Counter()
    for sh in shapes:
        st = str(getattr(sh, "shape_type", "") or "")
        if getattr(sh, "has_table", False) and sh.has_table:
            c["table"] += 1
        elif "PICTURE" in st:
            c["picture"] += 1
        elif "GROUP" in st:
            c["group"] += 1
            if depth < 4:
                c.update(_shape_counts(sh.shapes, depth + 1))
        elif "LINE" in st or "CONNECTOR" in st:
            c["connector"] += 1
        elif "AUTO_SHAPE" in st or "FREEFORM" in st:
            c["shape"] += 1
        elif "TEXT_BOX" in st or "PLACEHOLDER" in st:
            c["text"] += 1
        else:
            c["other"] += 1
    return c


def _rendered_layout(c: Counter[str]) -> str:
    if c.get("picture"):
        return "picture"
    if c.get("table") and (c.get("shape", 0) + c.get("connector", 0)) >= 3:
        return "visual_table"
    if c.get("table"):
        return "table"
    if c.get("shape", 0) + c.get("connector", 0) >= 3:
        return "visual"
    return "text"


def build_slide_spec(data: bytes, ctx: GenerationContext, profile: str) -> dict[str, Any]:
    """덱 바이트 + 생성 중 기록 → 슬라이드별 명세. profile = submission | presentation."""
    entries = list(ctx.slide_specs.get(profile, []))
    by_slide: dict[int, dict[str, Any]] = {}
    for e in entries:
        for n in range(int(e["slide_from"]), int(e["slide_to"]) + 1):
            by_slide.setdefault(n, e)
    prs = Presentation(io.BytesIO(data))
    slides: list[dict[str, Any]] = []
    for idx, slide in enumerate(prs.slides, start=1):
        texts = _texts(slide.shapes)
        joined = "\n".join(texts)
        counts = _shape_counts(slide.shapes)
        e = by_slide.get(idx, {})
        slides.append(
            {
                "slide_no": idx,
                "title": _slide_title(slide, str(e.get("title", "") or "")),
                "section_key": e.get("key", ""),
                "section_title": e.get("title", ""),
                "chapter": e.get("chapter", ""),
                "section": e.get("section", ""),
                "number": e.get("number", ""),
                "source": e.get("source", "code"),
                "key_message": e.get("key_message", ""),
                "purpose": e.get("purpose", ""),
                "audience": AUDIENCE_LABEL.get(str(e.get("audience", "")), e.get("audience", "")),
                "layout_type": e.get("layout_type", ""),
                "rendered_layout": _rendered_layout(counts),
                "visual_kind": e.get("visual_kind", ""),
                "evidence": e.get("evidence", []),
                "data_refs": e.get("data_refs", []),
                "requirement_ids": sorted(set(ID_RE.findall(joined))),
                "links_prev": e.get("links_prev", []),
                "links_next": e.get("links_next", []),
                "terms": e.get("terms", []),
                "shapes": dict(counts),
                "text_chars": len(joined),
                "has_notes": bool(
                    slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
                ),
            }
        )
    agent_entries = [e for e in entries if e.get("source") == "agent"]
    glossary = list((ctx.proposal_content or {}).get("glossary") or [])
    summary = {
        "slides": len(slides),
        "sections": len(entries),
        "agent_sections": len(agent_entries),
        "sections_without_key_message": [
            e.get("number") or e.get("title") for e in agent_entries if not e.get("key_message")
        ],
        "sections_without_evidence": [
            e.get("number") or e.get("title")
            for e in agent_entries
            if not e.get("evidence") and not e.get("data_refs")
        ],
        "sections_without_purpose": [
            e.get("number") or e.get("title") for e in agent_entries if not e.get("purpose")
        ],
        "visual_kinds": dict(Counter(e["visual_kind"] for e in entries if e.get("visual_kind"))),
        "rendered_layouts": dict(Counter(x["rendered_layout"] for x in slides)),
        "glossary_terms": len(glossary),
        "pictures": sum(x["shapes"].get("picture", 0) for x in slides),
    }
    return {
        "profile": profile,
        "project": ctx.project.name,
        "version": ctx.version,
        "generated_on": str(ctx.generated_on),
        "summary": summary,
        "glossary": glossary,
        "sections": entries,
        "slides": slides,
    }


__all__ = [
    "AUDIENCE_LABEL",
    "EVIDENCE_KIND_LABEL",
    "build_slide_spec",
    "code_entry",
    "evidence_line",
    "section_entry",
]
