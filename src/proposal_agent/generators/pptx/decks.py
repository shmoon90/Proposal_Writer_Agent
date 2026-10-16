"""제출용·발표용 PPT 생성. 두 덱은 같은 GenerationContext 수치만 쓴다 (일치 검증은 validation/deliverables.py)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from proposal_agent.generators.base import GenerationContext, acceptance_label
from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.charts import add_category_chart, add_gantt_chart
from proposal_agent.generators.pptx.outline import (
    ChapterPlan,
    OutlineSection,
    canonical_key,
    plan_chapters,
)
from proposal_agent.generators.pptx.req_groups import (
    FLOW_HEADERS,
    FLOW_WIDTHS,
    TECH_HEADERS,
    TECH_WIDTHS,
    RequirementGroup,
    approach_table_rows,
    design_comparison_blocks,
    design_data_lines,
    design_flow_spec,
    design_nonfunctional_rows,
    design_risk_lines,
    design_structure_spec,
    difficulty_label,
    flow_table_rows,
    function_block_spec,
    group_requirements,
    premises,
    tech_choice_rows,
)
from proposal_agent.generators.pptx.shapes import (
    draw_architecture,
    draw_bars,
    draw_cards,
    draw_kpis,
    draw_timeline,
    draw_two_column,
)
from proposal_agent.generators.pptx.slide_spec import code_entry, evidence_line, section_entry
from proposal_agent.generators.pptx.template import Box, TemplateDeckBuilder, TemplateProfile
from proposal_agent.models import RequirementType
from proposal_agent.planning.effort import md_to_mm


def _footer(ctx: GenerationContext, profile: str) -> str:
    return f"{ctx.project.name} · {profile} · {ctx.version}"


def key_figures(ctx: GenerationContext) -> dict[str, str]:
    """두 덱에 공통으로 들어가는 수치 (QA가 양쪽 텍스트에서 이 값을 찾아 비교한다)."""
    total_md = ctx.total_effort_md
    roles = ctx.roles_by_id
    role_mm: dict[str, Decimal] = {}
    for a in ctx.allocations:
        r = roles.get(a.staff_role_id)
        if r:
            role_mm[r.role_name] = role_mm.get(r.role_name, Decimal("0")) + a.effort_md
    return {
        "period": f"{ctx.period_start} ~ {ctx.period_end}"
        if ctx.period_start and ctx.period_end
        else "기간 미정",
        "total_mm": f"{float(md_to_mm(total_md)):.2f} MM",
        "total_md": f"{float(total_md):.1f} M/D",
        "requirements": f"요구사항 {len(ctx.requirements)}건",
        "mandatory": f"필수 {len([r for r in ctx.requirements if r.scope_class.value == 'mandatory'])}건",
        "headcount": f"투입 {sum(r.headcount_planned for r in ctx.roles)}명",
        "technologies": ", ".join(
            sorted(
                {
                    c.technology
                    for c in ctx.components
                    if c.technology and "미정" not in c.technology
                }
            )
        )
        or "기술 미정",
    }


def _agent_section(ctx: GenerationContext, key: str, index: int | None = None) -> dict | None:
    sections = (ctx.proposal_content or {}).get("sections", []) or []
    if index is not None and 0 <= index < len(sections):
        return sections[index]
    for s in sections:
        if canonical_key(str(s.get("slide_group", ""))) == key:
            return s
    return None


Builder = DeckBuilder | TemplateDeckBuilder


def _make_builder(
    template_profile: TemplateProfile | None,
    template_data: bytes | None,
    *,
    max_bullets: int,
    max_chars: int,
    body_font_pt: int,
) -> Builder:
    if template_profile is not None and template_data:
        return TemplateDeckBuilder(template_data, template_profile)
    return DeckBuilder(max_bullets=max_bullets, max_chars=max_chars, body_font_pt=body_font_pt)


def _render_agent_extras(
    b: Builder, sec: OutlineSection, agent: dict[str, Any], footer: str
) -> bool:
    """에이전트가 준 표·요구사항 카드 등 템플릿형 요소. 렌더링했으면 True."""
    done = False
    headers = agent.get("table_headers") or []
    rows = agent.get("table_rows") or []
    if headers and rows:
        b.table_slides(
            sec.title,
            [str(h) for h in headers],
            [[str(c) for c in r] for r in rows],
            footer,
            lead=str(agent.get("lead_message", "") or ""),
            footnotes=[str(x) for x in agent.get("footnotes", []) or []],
            notes=str(agent.get("speaker_notes", "") or ""),
        )
        done = True
    return done


def _figure_lines(figs: dict[str, str]) -> list[str]:
    """제출용·발표용 모두에 반드시 들어가는 핵심 수치 (QA가 Excel과 대조)."""
    return [
        f"기간 {figs['period']}",
        f"총 공수 {figs['total_md']} ({figs['total_mm']})",
        figs["headcount"],
    ]


def _requirement_rows(ctx: GenerationContext) -> list[list[object]]:
    return [
        [
            r.id,
            r.name[:40],
            r.type.label,
            r.scope_class.label,
            acceptance_label(r),
            (r.implementation_approach or "검토 필요")[:60],
        ]
        for r in ctx.requirements
    ]


def _schedule_rows(ctx: GenerationContext) -> list[list[object]]:
    return [
        [w.code, w.name[:36], w.planned_start, w.planned_end, w.duration_days, float(w.effort_md)]
        for w in ctx.wbs
        if w.code.count(".") <= 1
    ]


def _staff_rows(ctx: GenerationContext) -> list[list[object]]:
    roles = ctx.roles_by_id
    totals: dict[str, Decimal] = {}
    for a in ctx.allocations:
        r = roles.get(a.staff_role_id)
        if r:
            totals[r.id] = totals.get(r.id, Decimal("0")) + a.effort_md
    return [
        [
            r.role_name,
            r.grade or "미정",
            r.headcount_planned,
            r.duties[:40],
            f"{float(md_to_mm(totals.get(r.id, Decimal('0')))):.2f}",
        ]
        for r in ctx.roles
    ]


def _timeline_items(ctx: GenerationContext) -> list[tuple[str, Any, Any]]:
    return [
        (f"{w.code} {w.name[:22]}", w.planned_start, w.planned_end)
        for w in ctx.wbs
        if w.code.count(".") <= 1 and not w.milestone
    ]


def _staff_bars(ctx: GenerationContext) -> list[tuple[str, float, str]]:
    roles = ctx.roles_by_id
    totals: dict[str, Decimal] = {}
    for a in ctx.allocations:
        r = roles.get(a.staff_role_id)
        if r:
            totals[r.id] = totals.get(r.id, Decimal("0")) + a.effort_md
    return [
        (r.role_name, round(float(md_to_mm(totals.get(r.id, Decimal("0")))), 2), "MM")
        for r in ctx.roles
    ]


def _requirement_stats(ctx: GenerationContext) -> tuple[list[str], list[float], list[float]]:
    """유형별 (필수, 선택·부가) 건수. 네이티브 차트 데이터."""
    cats: list[str] = []
    mand: list[float] = []
    opt: list[float] = []
    for t in RequirementType:
        rows = [r for r in ctx.requirements if r.type == t]
        if not rows:
            continue
        cats.append(t.label)
        m = len([r for r in rows if r.scope_class.value == "mandatory"])
        mand.append(float(m))
        opt.append(float(len(rows) - m))
    return cats, mand, opt


def _find_picture(ctx: GenerationContext, ref: str) -> dict[str, Any] | None:
    key = str(ref or "").strip().lower()
    if not key:
        return None
    for pic in ctx.pictures:
        names = (str(pic.get("file_name", "")).lower(), str(pic.get("caption", "")).lower())
        if key in names or any(key in n for n in names if n):
            return pic
    return None


def _render_picture(b: Builder, title: str, pic: dict[str, Any], footer: str) -> bool:
    """등록된 참고 그림을 태그 달린 그림 슬라이드로 (Phase 20). 실패하면 False."""
    try:
        b.image_slide(
            title,
            str(pic["path"]),
            footer,
            caption=str(pic.get("caption", "") or ""),
            tag=str(pic.get("tag", "") or "reference"),
        )
    except Exception:  # noqa: BLE001  그림 파일 문제는 덱 생성을 막지 않는다 (QA가 검출)
        return False
    return True


def _first_sentence(text: str, limit: int) -> str:
    """발표용 리드 상자(한 줄 양식)에 맞게 첫 문장만, 최대 limit 자."""
    text = " ".join(text.split())
    for sep in (". ", "다. ", "함. "):
        i = text.find(sep)
        if 0 < i <= limit:
            return text[: i + 1]
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _card_title(text: str) -> str:
    head = text.split("(")[0].split(":")[0].split("—")[0].strip()
    return head[:18] if head else text[:18]


def _risk_bullets(ctx: GenerationContext) -> list[str]:
    out: list[str] = []
    for t in ctx.research:
        for r in t.risks[:2]:
            out.append(f"[{t.topic[:20]}] {r}")
        if t.feasibility.value in ("infeasible", "unknown"):
            out.append(f"[{t.topic[:20]}] 구현 가능성 {t.feasibility.value} — 사람 검토 필요")
    out.extend(f"일정: {n}" for n in ctx.review_notes if "기간" in n or "충돌" in n)
    if not out:
        out.append("식별된 기술 위험 없음 (기술 조사 결과 기준) — 검토 필요")
    return out


_DATA_KEYS = {
    "purpose",
    "understanding",
    "current",
    "requirements",
    "strategy",
    "system_diagram",
    "sw_diagram",
    "service_diagram",
    "architecture",
    "security",
    "testing",
    "operations",
    "schedule",
    "organization",
    "risk",
    "evaluation",
}


ALTERNATIVE_KIND_LABEL = {"commercial": "상용", "open_source": "공개 SW", "in_house": "자체 개발"}


def _spec_profile(compact: bool) -> str:
    return "presentation" if compact else "submission"


def _log_slides(ctx: GenerationContext, profile: str, entry: dict[str, Any]) -> None:
    ctx.slide_specs.setdefault(profile, []).append(entry)


def _notes_text(agent: dict[str, Any] | None, *, lead_used: str) -> str:
    """발표자 노트 = speaker_notes + 슬라이드 명세(목적·독자·연결·리드) (Phase 19)."""
    a = agent or {}
    lines = [str(a.get("speaker_notes", "") or "")]
    if a.get("purpose"):
        lines.append(f"[목적] {a['purpose']}")
    if a.get("audience"):
        lines.append(f"[독자] {a['audience']}")
    prev, nxt = a.get("links_prev") or [], a.get("links_next") or []
    if prev or nxt:
        lines.append(
            f"[연결] 앞 {', '.join(map(str, prev)) or '-'} → 뒤 {', '.join(map(str, nxt)) or '-'}"
        )
    lm = str(a.get("lead_message", "") or "")
    if lm and lm != lead_used:
        lines.append(f"[리드] {lm}")
    return "\n".join(x for x in lines if x)


def _evidence_footnotes(agent: dict[str, Any] | None, *, compact: bool = False) -> list[str]:
    """근거 → 하단 ※ 주석. 발표용(compact)은 주석 상자가 작아 1줄만."""
    return [
        evidence_line(e) for e in (agent or {}).get("evidence", []) or [] if isinstance(e, dict)
    ][: 1 if compact else 2]


def _render_tech_detail(
    b: Builder, sec: OutlineSection, agent: dict[str, Any], footer: str, *, compact: bool
) -> None:
    """기술 소절 템플릿: 구성·연계·데이터·운영·보안 카드 + 대안 비교(상용/공개/자체) 표 (Phase 19)."""
    td = agent.get("tech_detail") or {}
    if not isinstance(td, dict):
        return
    groups = (
        ("구성 요소", td.get("components") or []),
        ("연계·인터페이스", td.get("interfaces") or []),
        ("데이터", td.get("data") or []),
        ("운영·장애", td.get("operations") or []),
        ("보안 통제", td.get("security") or []),
    )
    items = [
        {"title": t, "text": "\n".join(f"• {str(x)[:60]}" for x in v[:5])} for t, v in groups if v
    ]
    reason = str(td.get("selection_reason", "") or "")
    visual_given = isinstance(agent.get("visual"), dict) and (
        agent["visual"].get("items") or agent["visual"].get("rows")
    )
    if (
        items and not compact and not visual_given
    ):  # 도식 소절은 복합 장표에 카드가 이미 들어감 (Phase 22)
        slide, box = b.canvas_slide(
            f"{sec.title} — 기술 상세", lead=reason, notes=str(agent.get("speaker_notes", "") or "")
        )
        draw_cards(slide, box, items, style=b.style, numbered=False, max_cols=5)
    alts = [a for a in td.get("alternatives") or [] if isinstance(a, dict)]
    if alts:
        # 발표용(compact)은 셀 글꼴이 커서 짧게: 항목 2개·30자, 비용 열 생략
        n_items, n_chars = (2, 30) if compact else (4, 60)

        def _join(xs: Any) -> str:
            return " · ".join(str(x)[:n_chars] for x in (xs or [])[:n_items])

        rows = [
            [
                ALTERNATIVE_KIND_LABEL.get(str(a.get("kind", "")), str(a.get("kind", ""))),
                str(a.get("name", ""))[: 24 if compact else 40],
                _join(a.get("pros")),
                _join(a.get("cons")),
                *([] if compact else [str(a.get("cost_note", "") or "")[:40]]),
                ("● 선정" if a.get("selected") else "")
                + (
                    f" — {str(a.get('basis', ''))[: 20 if compact else 40]}"
                    if a.get("basis")
                    else ""
                ),
            ]
            for a in alts[:6]
        ]
        headers = (
            ("구분", "대안", "장점", "단점", "선정·근거")
            if compact
            else ("구분", "대안", "장점", "단점", "비용 관점", "선정·근거")
        )
        b.table_slides(
            f"{sec.title} — 대안 비교 (상용/공개/자체)",
            headers,
            rows,
            footer,
            col_widths=(1, 2, 3.5, 3.5, 2.5) if compact else (1, 2, 3, 3, 1.5, 2.5),
            lead=reason,
            footnotes=() if compact else _evidence_footnotes(agent),
        )


def _render_section(
    b: Builder, ctx: GenerationContext, sec: OutlineSection, profile: str, *, compact: bool
) -> None:
    """소절 렌더링 + 슬라이드 범위 기록(명세) + 기술 상세·대안 비교 (Phase 19)."""
    agent = _agent_section(ctx, sec.key, sec.agent_index)
    first = len(b.prs.slides) + 1
    _render_section_body(b, ctx, sec, profile, compact=compact)
    if agent and agent.get("tech_detail"):
        _render_tech_detail(b, sec, agent, _footer(ctx, profile), compact=compact)
    pic = _find_picture(ctx, str((agent or {}).get("picture", "") or ""))
    if pic is not None:
        if _render_picture(b, f"{sec.title} — 참고 그림", pic, _footer(ctx, profile)):
            ctx.used_pictures.add(str(pic.get("file_name", "")))
    last = len(b.prs.slides)
    if compact:
        _fill_default_notes(b, sec, first, last)
    if last >= first:
        _log_slides(ctx, _spec_profile(compact), section_entry(sec, agent, first, last))


def _fill_default_notes(b: Builder, sec: OutlineSection, first: int, last: int) -> None:
    """발표용(Phase 21): 발표자 노트가 비어 있는 소절 슬라이드에 제목·리드·본문 요약을 기본 노트로 넣는다.
    에이전트 speaker_notes 가 있으면 그대로 두고, 사람이 발표 전에 다듬을 초안임을 표시한다."""
    slides = list(b.prs.slides)
    for i in range(first - 1, min(last, len(slides))):
        slide = slides[i]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            continue
        texts = [
            sh.text_frame.text.strip()
            for sh in slide.shapes
            if sh.has_text_frame and sh.text_frame.text.strip()
        ]
        body = [t for t in texts[1:] if len(t) > 1][:3]
        note = f"[발표 노트 초안] {sec.title}" + (
            ": " + " / ".join(x[:80] for x in body) if body else ""
        )
        slide.notes_slide.notes_text_frame.text = note[:600]


def _split_blocks(
    b: Builder, blocks: list[dict[str, Any]], title: str, *, has_lead: bool
) -> list[tuple[list[dict[str, Any]], str]]:
    """블록 필요 높이 합이 본문 높이를 넘으면 표(기술 상세·세부 내용)를 '(계속)' 장으로 분리한다 (Phase 22)."""
    from proposal_agent.generators.pptx.shapes import estimate_block_height

    body_h = float(getattr(b, "body_height_cm", 14.0)) - (2.0 if has_lead else 0.0) - 1.2
    body_w = float(getattr(b, "body_width_cm", 17.0))
    needs = [
        estimate_block_height(x, body_w, b.style) + (0.95 if x.get("title") else 0.0) + 0.3
        for x in blocks
    ]
    if sum(needs) <= body_h or len(blocks) < 2:
        return [(blocks, title)]
    first = [x for x in blocks if x.get("kind") != "table"]
    tables = [x for x in blocks if x.get("kind") == "table"]
    if not tables or not first:
        return [(blocks, title)]
    pages: list[tuple[list[dict[str, Any]], str]] = [(first, title)]
    for t in tables:
        pages.append(([t], f"{title} (계속)"))
    return pages


def _render_requirement_groups(
    b: Builder, ctx: GenerationContext, sec: OutlineSection, footer: str, *, compact: bool
) -> None:
    """요구사항 묶음별 구현 방안 (Phase 22·23): 묶음마다 요점 → 구현 구조 도식 → 처리 절차 도식 → 적용 기술 표 →
    데이터·인터페이스 → 정의서 구현방안 전문 표(구현 설계가 있을 때; 없으면 요점 → 기능 블록 도식 → 구현방안 표).

    블록은 추정 높이로 장에 배분하고 표는 행 단위로 '(계속)' 장에 잇는다. 발표용은 묶음마다 1~2장."""
    groups = group_requirements(ctx)
    if not groups:
        b.bullet_slides(
            sec.title,
            [
                "구현 방안이 작성된 요구사항이 없음 — '구현 방안 작성(에이전트)' 실행 또는 요구사항 화면에서 입력 필요"
            ],
            footer,
        )
        return
    for g in groups:
        _render_group(b, ctx, g, footer, compact=compact)


def _rows_per_page(
    rows: list[list[str]],
    headers: list[str],
    widths: list[float],
    width_cm: float,
    style: Any,
    avail_cm: float,
) -> int:
    """표 행을 몇 개까지 한 장에 넣을지 — 셀 줄 수 추정으로 (최소 1행)."""
    from proposal_agent.generators.pptx.shapes import estimate_block_height

    for n in range(len(rows), 0, -1):
        est = estimate_block_height(
            {"kind": "table", "headers": headers, "rows": rows[:n], "col_widths": widths},
            width_cm,
            style,
        )
        if est <= avail_cm:
            return n
    return 1


def _group_rows_per_page(
    rows: list[list[str]], width_cm: float, style: Any, avail_cm: float
) -> int:
    return _rows_per_page(rows, ["", "", "", ""], GROUP_WIDTHS, width_cm, style, avail_cm)


GROUP_HEADERS = ["요구사항", "구현 방안 (요구사항 정의서와 동일)", "난이도", "검증 방법·검사 기준"]
GROUP_WIDTHS = [2.2, 5.5, 0.8, 2.5]
_MIN_VISUAL_H = {"layers": 2.5, "procedure": 5.0, "function_blocks": 4.0}


def _block_need(blk: dict[str, Any], body_w: float, style: Any) -> float:
    from proposal_agent.generators.pptx.shapes import estimate_block_height

    need = estimate_block_height(blk, body_w, style)
    if blk.get("kind") == "visual":
        need = max(need, _MIN_VISUAL_H.get(str((blk.get("spec") or {}).get("kind", "")), 4.0))
    elif blk.get("kind") == "function_blocks":
        need = max(need, _MIN_VISUAL_H["function_blocks"])
    return need + (0.95 if blk.get("title") else 0.0) + 0.3


def _paginate_blocks(
    b: Builder, blocks: list[dict[str, Any]], *, has_lead: bool
) -> list[list[dict[str, Any]]]:
    """블록을 추정 높이로 장에 나눠 담는다 (Phase 23). 표는 행 단위로 나누고(장당 최소 2행), 도식·글머리는
    통째로 넣는다. 도식은 최소 높이까지 줄여서라도 같은 장에 두고(draw_blocks 가 축소), 요점만 있는 장에는
    크더라도 넣는다. 돌려주는 값은 장별 블록 목록."""
    body_w = float(getattr(b, "body_width_cm", 17.0))
    body_h = float(getattr(b, "body_height_cm", 14.0))
    lead_h = 2.0 if has_lead else 0.0
    pages: list[list[dict[str, Any]]] = [[]]
    used = lead_h + 0.6  # ※ 주석 여유
    for blk in blocks:
        kind = str(blk.get("kind", ""))
        if kind == "table":
            rows = list(blk.get("rows", []) or [])
            headers = [str(h) for h in blk.get("headers", []) or []]
            widths = list(blk.get("col_widths") or []) or [1.0] * max(1, len(headers))
            title = str(blk.get("title", "") or "")
            first = True
            while rows:
                avail = body_h - used - (0.95 if title else 0.0) - 0.3
                n = (
                    _rows_per_page(rows, headers, widths, body_w, b.style, avail)
                    if avail > 1.6
                    else 0
                )
                if n < min(2, len(rows)) and pages[-1]:
                    pages.append([])
                    used = 0.6
                    continue
                n = max(n, 1)
                chunk = dict(
                    blk,
                    rows=rows[:n],
                    title=title if first else (f"{title} (계속)" if title else ""),
                )
                pages[-1].append(chunk)
                used += _block_need(chunk, body_w, b.style)
                rows = rows[n:]
                first = False
                if rows:
                    pages.append([])
                    used = 0.6
            continue
        need = _block_need(blk, body_w, b.style)
        if kind in ("visual", "function_blocks"):
            spec_kind = str((blk.get("spec") or {}).get("kind", "")) if kind == "visual" else kind
            need_min = min(need, _MIN_VISUAL_H.get(spec_kind, 4.0) + 1.25)
            if spec_kind == "procedure" and need > 6.0:  # 세로 절차는 줄이면 상자가 넘치므로 통째로
                need_min = need
        else:
            need_min = need
        has_big = any(str(x.get("kind", "")) != "bullets" for x in pages[-1])
        if used + need_min > body_h and has_big:
            pages.append([])
            used = 0.6
        pages[-1].append(blk)
        used += min(need, max(body_h - used, need_min))
    return [pg for pg in pages if pg]


def _group_blocks(g: RequirementGroup, *, compact: bool) -> list[dict[str, Any]]:
    """묶음 소절 내용 블록(순서대로): 요점 → [구현 구조 → 처리 절차 → 적용 기술 → 데이터·인터페이스] 또는 [기능 구성]
    → 정의서 구현방안 표(제출용만)."""
    ids_line = "대응 요구사항: " + ", ".join(
        f"{r.id}" + (f"({r.rfp_requirement_id})" if r.rfp_requirement_id else "")
        for r in g.requirements
    )
    summary = list(g.summary) or [
        f"요구 {len(g.requirements)}건 — 난이도 상 {sum(1 for r in g.requirements if difficulty_label(r) == '상')}건, "
        f"중 {sum(1 for r in g.requirements if difficulty_label(r) == '중')}건, 하 {sum(1 for r in g.requirements if difficulty_label(r) == '하')}건",
    ]
    blocks: list[dict[str, Any]] = [
        {"kind": "bullets", "title": "", "lines": [ids_line, *summary][: 4 if compact else 5]}
    ]
    d = g.design
    if d:
        if d.get("structure"):
            blocks.append(
                {"kind": "visual", "title": "구현 구조", "spec": design_structure_spec(d)}
            )
        if d.get("flows"):
            blocks.append({"kind": "visual", "title": "처리 절차", "spec": design_flow_spec(d)})
            if not compact:  # 상자에는 단계 제목만, 처리 내용·분기는 표로 (글자 잘림 방지)
                blocks.append(
                    {
                        "kind": "table",
                        "title": "처리 절차 상세",
                        "headers": FLOW_HEADERS,
                        "rows": flow_table_rows(d),
                        "col_widths": FLOW_WIDTHS,
                    }
                )
        rows = tech_choice_rows(d)
        if rows:
            blocks.append(
                {
                    "kind": "table",
                    "title": "적용 기술·선정 이유",
                    "headers": TECH_HEADERS,
                    "rows": rows[:4] if compact else rows,
                    "col_widths": TECH_WIDTHS,
                }
            )
        if not compact:
            blocks.extend(design_comparison_blocks(d))  # 단계 3: 대안 비교
            lines = design_data_lines(d)
            risks = design_risk_lines(d)
            if lines or risks:
                blocks.append(
                    {
                        "kind": "bullets",
                        "title": "데이터·인터페이스 설계" + (" · 위험 대응" if risks else ""),
                        "lines": lines + [f"위험: {x}" for x in risks],
                    }
                )
            nf = design_nonfunctional_rows(d)  # 단계 3: 비기능 설계
            if nf:
                blocks.append(
                    {
                        "kind": "table",
                        "title": "비기능 설계 (성능·장애·운영·보안·테스트)",
                        "headers": ["구분", "설계 내용"],
                        "rows": nf,
                        "col_widths": [1.8, 8.2],
                    }
                )
    else:
        blocks.append(
            {"kind": "function_blocks", "title": "기능 구성", "spec": function_block_spec(g)}
        )
    if not compact:
        blocks.append(
            {
                "kind": "table",
                "title": "요구사항별 구현 방안",
                "headers": GROUP_HEADERS,
                "rows": approach_table_rows(g),
                "col_widths": GROUP_WIDTHS,
            }
        )
    return blocks


def _render_group(
    b: Builder, ctx: GenerationContext, g: RequirementGroup, footer: str, *, compact: bool
) -> None:
    """묶음 소절: 블록을 장에 배분해 그리고, 표가 영역 부족으로 덜 그려지면 남은 행을 다음 장에 잇는다."""
    from proposal_agent.generators.pptx.shapes import LAST_BLOCK_META

    notes_text = "\n".join(f"{r.id}: {r.implementation_approach}" for r in g.requirements)[:2000]
    blocks = _group_blocks(g, compact=compact)
    pages = _paginate_blocks(b, blocks, has_lead=bool(g.key_message))
    foot = premises(g) + list(g.notes)
    i = 0
    while i < len(pages):
        page = pages[i]
        last = i == len(pages) - 1
        kinds = b.composite_slide(
            g.title if i == 0 else f"{g.title} (계속)",
            page,
            footer,
            lead=g.key_message if i == 0 else "",
            notes=notes_text,
            footnotes=foot[:3] if last else [],
        )
        # 실제로 그린 행이 계획보다 적으면 남은 행을, 공간 부족으로 아예 못 그린 블록은 통째로 다음 장으로
        drawn = [int(m.get("rows_drawn", 0)) for m in LAST_BLOCK_META if m.get("kind") == "table"]
        tables = [blk for blk in page[: len(kinds)] if blk.get("kind") == "table"]
        leftovers: list[dict[str, Any]] = []
        undrawn = page[len(kinds) :]
        for blk, n in zip(tables, drawn, strict=False):
            rows = list(blk.get("rows", []) or [])
            if 0 < n < len(rows):
                title = str(blk.get("title", "") or "")
                leftovers.append(
                    dict(
                        blk,
                        rows=rows[n:],
                        title=title if title.endswith("(계속)") or not title else f"{title} (계속)",
                    )
                )
        leftovers.extend(undrawn)
        if leftovers:
            pages.insert(i + 1, leftovers)
        i += 1


def _glossary_rows(ctx: GenerationContext) -> list[list[object]]:
    rows: list[list[object]] = []
    for g in (ctx.proposal_content or {}).get("glossary") or []:
        if not isinstance(g, dict) or not g.get("term"):
            continue
        rows.append(
            [
                str(g.get("term", ""))[:30],
                str(g.get("full_form", "") or "")[:60],
                str(g.get("meaning", "") or "")[:140],
                str(g.get("first_section", "") or "")[:10],
            ]
        )
    return rows


def _render_glossary(b: Builder, ctx: GenerationContext, footer: str, *, compact: bool) -> None:
    rows = _glossary_rows(ctx)
    if not rows:
        return
    first = len(b.prs.slides) + 1
    b.table_slides(
        "용어 설명",
        ("용어·약어", "풀이", "설명 (비전문가용)", "첫 등장"),
        rows[: 16 if compact else 60],
        footer,
        col_widths=(1.5, 2.5, 5, 1),
        lead="본문에 쓴 약어·전문 용어의 뜻" if not compact else "",
    )
    _log_slides(
        ctx, _spec_profile(compact), code_entry("glossary", "용어 설명", first, len(b.prs.slides))
    )


def _render_section_body(
    b: Builder, ctx: GenerationContext, sec: OutlineSection, profile: str, *, compact: bool
) -> None:
    footer = _footer(ctx, profile)
    figs = key_figures(ctx)
    agent = _agent_section(ctx, sec.key, sec.agent_index)
    key_msg = str((agent or {}).get("key_message", "") or "")
    # 결론형 제목(key_message)이 있으면 리드 상자에 결론을, 원래 리드 문장은 발표자 노트에 남긴다
    lead = key_msg or sec.lead or str((agent or {}).get("lead_message", "") or "")
    notes = _notes_text(agent, lead_used=lead)
    footnotes = [str(x) for x in (agent or {}).get("footnotes", []) or []] + _evidence_footnotes(
        agent, compact=compact
    )
    req_ids = [str(x) for x in (agent or {}).get("requirement_ids", []) or []]
    key = sec.key
    if key == "placeholder":
        b.bullet_slides(
            sec.title,
            [f"RFP 작성방법: {g}" for g in sec.guide[:4]]
            + ["(RFP 지정 목차 항목 — 내용은 사람 작성 필요)"],
            footer,
            footnotes=["RFP가 요구한 절이며 기준 데이터에서 채울 내용이 없음"],
        )
        return
    visual = (agent or {}).get("visual")
    if (
        agent
        and isinstance(visual, dict)
        and visual.get("items")
        or (agent and isinstance(visual, dict) and visual.get("rows"))
    ):
        # 에이전트가 도식을 지정한 소절: 샘플 제안서처럼 한 장을 밴드로 구성 — 요점 → 도식 → (기술 상세 카드 | 표).
        # 세로로 늘어진 빈 상자를 피하려고 블록 높이는 내용 추정량으로 배분한다 (Phase 22)
        bullets = [
            *(["대응 요구사항: " + ", ".join(req_ids[:12])] if req_ids else []),
            *list(agent.get("bullets") or []),
        ]
        blocks: list[dict[str, Any]] = []
        if bullets:
            blocks.append({"kind": "bullets", "title": "", "lines": bullets[: 5 if compact else 8]})
        blocks.append(
            {"kind": "visual", "title": str(visual.get("title") or "구성·흐름"), "spec": visual}
        )
        td = agent.get("tech_detail") if isinstance(agent.get("tech_detail"), dict) else None
        headers = agent.get("table_headers") or []
        rows = agent.get("table_rows") or []
        if td and not compact:
            groups = (
                ("구성 요소", td.get("components") or []),
                ("연계·인터페이스", td.get("interfaces") or []),
                ("데이터", td.get("data") or []),
                ("운영·장애", td.get("operations") or []),
                ("보안 통제", td.get("security") or []),
            )
            rows_td = [[t, "\n".join(f"• {str(x)[:90]}" for x in v[:4])] for t, v in groups if v]
            if rows_td:
                blocks.append(
                    {
                        "kind": "table",
                        "title": "기술 상세",
                        "headers": ["구분", "내용"],
                        "rows": rows_td,
                        "col_widths": [1.6, 8.4],
                    }
                )
        elif headers and rows and len(rows) <= 6 and not compact:
            blocks.append(
                {
                    "kind": "table",
                    "title": "세부 내용",
                    "headers": [str(h) for h in headers],
                    "rows": [[str(c) for c in r] for r in rows],
                }
            )
            rows = []
        pages = _split_blocks(b, blocks, sec.title, has_lead=bool(lead))
        for i, (page_blocks, page_title) in enumerate(pages):
            b.composite_slide(
                page_title,
                page_blocks,
                footer,
                lead=lead if i == 0 else "",
                notes=notes,
                footnotes=footnotes if i == len(pages) - 1 else [],
            )
        if headers and rows:
            b.table_slides(
                sec.title,
                [str(h) for h in headers],
                [[str(c) for c in r] for r in rows],
                footer,
                lead="",
                notes=notes,
            )
        if key not in ("organization", "schedule", "requirements"):
            return
        # 일정·인력·요구사항 소절은 핵심 수치(기간·공수·인원·건수) 슬라이드가 반드시 있어야 하므로 코드 데이터 슬라이드도 이어 그린다
        agent = {**agent, "bullets": [], "visual": None}
        notes = ""
    if agent and req_ids and agent.get("bullets"):
        # 템플릿 관행: 소절 상단에 대응 요구사항 ID 카드 → 글머리 첫 줄로
        agent = {
            **agent,
            "bullets": ["대응 요구사항: " + ", ".join(req_ids[:12]), *agent["bullets"]],
        }
    if (
        agent
        and _render_agent_extras(b, sec, agent, footer)
        and not (agent.get("bullets") or agent.get("body"))
    ):
        return
    if agent and (
        key.startswith(("generic", "agent")) or sec.source == "agent" and key not in _DATA_KEYS
    ):
        bullets = list(agent.get("bullets") or [])
        if agent.get("body") and not bullets:
            bullets = [str(agent["body"])[:300]]
        if req_ids and not any(x.startswith("대응 요구사항:") for x in bullets):
            bullets.insert(0, "대응 요구사항: " + ", ".join(req_ids[:12]))
        b.bullet_slides(sec.title, bullets, footer, notes=notes, lead=lead, footnotes=footnotes)
        return
    if key in ("purpose", "understanding"):
        a = ctx.analysis or {}
        goals = [str(g) for g in a.get("client_goals", []) or [] if g][:4]
        if goals:
            # 배경·목표 시각화: 목표 카드 + 요약 (편집 가능 도형)
            b.visual_slide(
                sec.title,
                {
                    "kind": "cards",
                    "items": [{"title": f"목표 {i + 1}", "text": g} for i, g in enumerate(goals)],
                },
                footer,
                lead=lead or str(a.get("overview", ""))[:200],
                bullets=list((agent or {}).get("bullets") or [])[:3],
                notes=notes,
            )
            if not compact and (agent or {}).get("bullets"):
                return
            if compact:
                return
        bullets = (
            [a.get("overview", "")]
            + list(a.get("client_goals", []))
            + list(a.get("scope_summary", "") and [a["scope_summary"]] or [])
        )
        bullets = (agent or {}).get("bullets") or [x for x in bullets if x]
        b.bullet_slides(
            sec.title,
            bullets or [f"{ctx.project.name} 사업의 목적 (RFP 분석 결과 없음 — 검토 필요)"],
            footer,
            notes=notes,
            lead=lead,
            footnotes=footnotes,
        )
    elif key == "current":
        a = ctx.analysis or {}
        b.bullet_slides(
            sec.title,
            (agent or {}).get("bullets")
            or list(a.get("constraints", [])) + list(a.get("uncertainties", [])),
            footer,
            notes=notes,
        )
    elif key == "requirements":
        lead_default = (
            f"{figs['requirements']} ({figs['mandatory']}) — 요구사항 정의서와 동일 데이터"
        )
        if compact:
            counts = {
                t.label: len([r for r in ctx.requirements if r.type == t]) for t in RequirementType
            }
            slide, box = b.canvas_slide(sec.title, lead=lead or lead_default, notes=notes)
            kpi_h = min(4.0, box.height * 0.4)
            draw_kpis(
                slide,
                Box(left=box.left, top=box.top, width=box.width, height=kpi_h),
                [(k, f"{v}건") for k, v in counts.items() if v][:5],
                style=b.style,
            )
            approaches = [
                f"{r.id} {r.name[:24]}: {r.implementation_approach[:60]}"
                for r in ctx.mandatory_requirements()
                if r.implementation_approach
            ][:6]
            draw_two_column(
                slide,
                Box(
                    left=box.left,
                    top=box.top + kpi_h + 0.4,
                    width=box.width,
                    height=max(box.height - kpi_h - 0.4, 3.0),
                ),
                "필수 요구사항",
                [f"{r.id} {r.name[:40]}" for r in ctx.mandatory_requirements()][:8],
                "구현 방안 (조사 근거)",
                approaches or ["구현 방안 미작성 — 기술 조사·제안 문안 작성 필요"],
                style=b.style,
            )
        else:
            b.table_slides(
                sec.title,
                ("ID", "요구사항", "종류", "범위", "수용", "구현 방안"),
                _requirement_rows(ctx),
                footer,
                col_widths=(1, 3, 1, 1, 1, 3),
                notes=notes or lead_default,
                lead=lead or f"{figs['requirements']} ({figs['mandatory']}) 전수 대응",
                footnotes=footnotes,
            )
            # 요구사항 통계: 유형별 필수/선택 건수 (네이티브 누적 차트, Phase 20)
            cats, mand, opt = _requirement_stats(ctx)
            if cats:
                slide, box = b.canvas_slide("요구사항 통계", lead=lead_default)
                add_category_chart(
                    slide,
                    box,
                    cats,
                    [("필수", mand), ("선택·부가", opt)],
                    style=b.style,
                    chart_type="stacked_column",
                    title="유형별 요구사항 건수",
                    number_format="0",
                )
    elif key == "req_groups":
        _render_requirement_groups(b, ctx, sec, footer, compact=compact)
    elif key == "strategy" and ctx.strategies:
        # 단계 3: 전략 STR 엔티티 — 발주처 문제 → 구현 방법·기술 → 차별성·기대 효과·근거 표 + 카드
        srows = [
            [
                f"{s.code}\n{s.title}",
                s.client_problem or "-",
                (s.approach or "")
                + ("\n기술: " + ", ".join(s.technologies[:4]) if s.technologies else ""),
                s.differentiator or "-",
                "\n".join(f"• {x}" for x in s.expected_effects[:3]) or "-",
                "\n".join(f"• {x}" for x in s.evidence[:3]) or "-",
            ]
            for s in ctx.strategies[:6]
        ]
        spages = _paginate_blocks(
            b,
            [
                {
                    "kind": "cards",
                    "title": "핵심 전략",
                    "items": [
                        {"title": f"{s.code} {_card_title(s.title)}", "text": s.title}
                        for s in ctx.strategies[:4]
                    ],
                },
                {
                    "kind": "table",
                    "title": "전략별 발주처 문제 → 구현 방법 → 차별성·기대 효과·근거",
                    "headers": [
                        "전략",
                        "발주처 문제·목표",
                        "구현 방법·기술",
                        "차별성",
                        "기대 효과",
                        "근거",
                    ],
                    "rows": srows,
                    "col_widths": [2.0, 2.2, 3.0, 2.0, 2.2, 2.0],
                },
            ],
            has_lead=bool(lead),
        )
        for i, page in enumerate(spages):
            b.composite_slide(
                sec.title if i == 0 else f"{sec.title} (계속)",
                page,
                footer,
                lead=(lead or "핵심 전략") if i == 0 else "",
                notes=notes,
                footnotes=[
                    f"미확인 주장(사람 확인 필요): {x}"
                    for s in ctx.strategies
                    for x in s.unverified_claims[:1]
                ][:2]
                if i == len(spages) - 1
                else [],
            )
    elif key == "strategy":
        bullets = (agent or {}).get("bullets") or [
            "RFP 필수 요구사항 전수 대응 및 추적성 확보 (요구사항 정의서·추적표)",
            "기술 조사 결과에 근거한 기술 선정 (출처·미확인 사항 명시)",
            "3단계 WBS와 영업일 기준 일정으로 투명한 공정 관리",
            "독립 검증과 사람 승인 게이트를 통한 품질 관리",
        ]
        slide, box = b.canvas_slide(sec.title, lead=lead or "핵심 전략", notes=notes)
        draw_cards(
            slide,
            box,
            [{"title": _card_title(x), "text": x} for x in bullets[:4]],
            style=b.style,
        )
    elif key in ("system_diagram", "sw_diagram", "service_diagram"):
        kind = key.split("_")[0]
        comps = [c for c in ctx.components if not c.diagram_kinds or kind in c.diagram_kinds]
        slide, box = b.canvas_slide(
            sec.title,
            lead=lead or f"{sec.title} — 구성 요소 {len(comps)}개 (편집 가능 도형)",
            notes=notes,
        )
        draw_architecture(slide, box, comps, style=b.style)
    elif key == "architecture":
        rows = [
            [c.id, c.layer, c.name, c.technology or "미정", c.description[:50]]
            for c in ctx.components
        ]
        b.table_slides(
            sec.title,
            ("코드", "레이어", "구성 요소", "기술", "설명"),
            rows,
            footer,
            col_widths=(1, 1, 2, 2, 3),
            notes=notes,
        )
        if not compact:
            b.bullet_slides(
                "구현 방안",
                (agent or {}).get("bullets")
                or [
                    f"{r.id}: {r.implementation_approach}"
                    for r in ctx.requirements
                    if r.implementation_approach
                ][:16]
                or ["구현 방안 미작성 — 검토 필요"],
                footer,
            )
    elif key == "security":
        sec_reqs = [
            r
            for r in ctx.requirements
            if r.category.value == "security" or "보안" in r.name or "암호" in r.name
        ]
        b.bullet_slides(
            sec.title,
            (agent or {}).get("bullets")
            or [f"{r.id} {r.name}: {r.implementation_approach or '검토 필요'}" for r in sec_reqs],
            footer,
            notes=notes,
        )
    elif key == "testing":
        b.bullet_slides(
            sec.title,
            (agent or {}).get("bullets")
            or [
                "단위·통합 테스트 ID는 설계 단계에서 확정 (추적표 '미정'으로 관리)",
                "테스트 결과는 실제 수행 전까지 '미실행'",
                f"요구사항 {len(ctx.requirements)}건 전수 추적 (요구사항 추적표)",
            ],
            footer,
            notes=notes,
        )
    elif key == "operations":
        ops = [
            r
            for r in ctx.requirements
            if r.category.value in ("availability", "operability")
            or any(k in r.name for k in ("운영", "유지보수", "가용", "백업"))
        ]
        b.bullet_slides(
            sec.title,
            (agent or {}).get("bullets") or [f"{r.id} {r.name}" for r in ops],
            footer,
            notes=notes,
        )
    elif key == "schedule":
        lead = f"기간 {figs['period']} · 총 공수 {figs['total_md']} ({figs['total_mm']})"
        if compact:
            slide, box = b.canvas_slide(sec.title, lead=lead, notes=notes)
            draw_timeline(
                slide, box, _timeline_items(ctx), ctx.period_start, ctx.period_end, style=b.style
            )
        else:
            b.table_slides(
                sec.title,
                ("WBS", "작업", "시작", "종료", "기간(일)", "공수(M/D)"),
                _schedule_rows(ctx),
                footer,
                col_widths=(1, 3, 1.3, 1.3, 1, 1),
                notes=notes or lead,
            )
            slide, box = b.canvas_slide("일정 (간트)", lead=lead)
            if (
                add_gantt_chart(
                    slide,
                    box,
                    _timeline_items(ctx),
                    ctx.period_start,
                    ctx.period_end,
                    style=b.style,
                    title="단계별 일정 (착수일 기준 경과 일수)",
                )
                is None
            ):
                draw_timeline(
                    slide,
                    box,
                    _timeline_items(ctx),
                    ctx.period_start,
                    ctx.period_end,
                    style=b.style,
                )
    elif key == "organization":
        lead = f"{figs['headcount']} · 총 {figs['total_mm']}"
        b.table_slides(
            sec.title,
            ("역할", "등급", "인원", "담당 업무", "공수(MM)"),
            _staff_rows(ctx),
            footer,
            col_widths=(1.5, 1, 1, 3, 1),
            notes=notes or lead,
        )
        slide, box = b.canvas_slide("역할별 공수", lead=lead)
        bars = _staff_bars(ctx)
        if (
            add_category_chart(
                slide,
                box,
                [n for n, _v, _u in bars],
                [("공수(MM)", [v for _n, v, _u in bars])],
                style=b.style,
                chart_type="bar",
                title="역할별 공수 (MM)",
            )
            is None
        ):
            draw_bars(slide, box, bars, style=b.style)
    elif key == "risk":
        risk_lines = list((agent or {}).get("bullets") or _risk_bullets(ctx))
        if compact:
            slide, box = b.canvas_slide(sec.title, lead=lead or "위험과 대응", notes=notes)
            pairs = [
                x.split("→", 1) if "→" in x else [x, "대응 방안 수립 필요"] for x in risk_lines[:6]
            ]
            draw_two_column(
                slide,
                box,
                "위험",
                [p[0].strip() for p in pairs],
                "대응",
                [p[1].strip() for p in pairs],
                style=b.style,
            )
        else:
            b.bullet_slides(
                sec.title, risk_lines, footer, notes=notes, lead=lead, footnotes=footnotes
            )
    elif key == "evaluation":
        a = ctx.analysis or {}
        b.bullet_slides(
            sec.title,
            (agent or {}).get("bullets")
            or list(a.get("evaluation_criteria", []))
            or [
                f"{r.id} {r.name}" for r in ctx.requirements if r.type == RequirementType.EVALUATION
            ],
            footer,
            notes=notes,
        )
    else:
        bullets = (agent or {}).get("bullets") or [
            f"RFP 목차 항목 '{sec.title}' — 내용은 사람 작성 필요"
        ]
        b.bullet_slides(sec.title, bullets, footer, notes=notes, lead=lead, footnotes=footnotes)


def build_submission_deck(
    ctx: GenerationContext,
    outline: list[OutlineSection],
    *,
    template_profile: TemplateProfile | None = None,
    template_data: bytes | None = None,
    toc_tree: list[dict[str, Any]] | None = None,
    chapters: list[ChapterPlan] | None = None,
) -> bytes:
    """제출용 PPT. 템플릿이 있으면 그 마스터·레이아웃 위에 장/절/소절 구조로, 없으면 기본 16:9 양식으로."""
    b = _make_builder(
        template_profile, template_data, max_bullets=8, max_chars=110, body_font_pt=16
    )
    footer = _footer(ctx, "제출용")
    plan = (
        chapters
        if chapters is not None
        else plan_chapters(
            outline, toc_tree, template_profile.chapters if template_profile else None
        )
    )
    ctx.slide_specs["submission"] = []
    ctx.used_pictures = set()
    b.title_slide(
        f"{ctx.project.name} 제안서",
        f"{ctx.project.client_name or ''} · {ctx.generated_on}".strip(" ·"),
        footer,
    )
    toc_lines: list[str] = []
    for ch in plan:
        head = f"{ch.numeral}. {ch.title}" if ch.numeral else ch.title
        toc_lines.append(head)
        toc_lines.extend(f"   {s.number}. {s.title}" for s in ch.sections)
    b.begin_section("목차", 0)
    b.bullet_slides("목차", toc_lines, footer)
    for ch in plan:
        b.begin_chapter(ch.numeral, ch.title, [s.title for s in ch.sections])
        for sp in ch.sections:
            b.begin_section(sp.title, sp.number)
            for sub in sp.subsections:
                _render_section(b, ctx, sub, "제출용", compact=False)
    figs = key_figures(ctx)
    keys = {sub.key for ch in plan for sp in ch.sections for sub in sp.subsections}
    tail_items: list[tuple[str, list[str]]] = []
    if not {"schedule", "organization"} <= keys:
        tail_items.append(("사업 기간·공수·투입 인력 요약", _figure_lines(figs)))
    claims = (ctx.proposal_content or {}).get("unverified_claims") or []
    if claims:
        tail_items.append(("사람 확인 필요 문구", list(claims)))
    glossary = _glossary_rows(ctx)
    if tail_items or glossary:
        b.begin_section("부록", len(plan[-1].sections) + 1 if plan else 1)
        for title, items in tail_items:
            first = len(b.prs.slides) + 1
            b.bullet_slides(title, items, footer)
            _log_slides(ctx, "submission", code_entry("appendix", title, first, len(b.prs.slides)))
        _render_glossary(b, ctx, footer, compact=False)
    rest = [p for p in ctx.pictures if str(p.get("file_name", "")) not in ctx.used_pictures]
    if rest:
        if not (tail_items or glossary):
            b.begin_section("부록", len(plan[-1].sections) + 1 if plan else 1)
        for pic in rest[:12]:
            first = len(b.prs.slides) + 1
            if _render_picture(b, "참고 그림", pic, footer):
                _log_slides(
                    ctx,
                    "submission",
                    code_entry("picture", str(pic.get("caption", "")), first, len(b.prs.slides)),
                )
    return b.to_bytes()


PRESENTATION_KEYS = {
    "purpose",
    "understanding",
    "current",
    "requirements",
    "strategy",
    "system_diagram",
    "architecture",
    "req_groups",
    "security",
    "testing",
    "schedule",
    "organization",
    "risk",
}

PRESENTATION_DEFAULT_CHAPTERS: list[dict[str, Any]] = [
    {
        "numeral": "Ⅰ",
        "title": "사업의 이해",
        "sections": [
            {"number": "1", "title": "제안 배경 및 목적", "guide": []},
            {"number": "2", "title": "사업 범위 및 현황", "guide": []},
            {"number": "3", "title": "사업 수행 전략", "guide": []},
        ],
    },
    {
        "numeral": "Ⅱ",
        "title": "사업 수행 방안",
        "sections": [
            {"number": "1", "title": "목표 시스템 구성", "guide": []},
            {"number": "2", "title": "요구사항 구현 방안", "guide": []},
            {"number": "3", "title": "서비스·연계 구성", "guide": []},
        ],
    },
    {
        "numeral": "Ⅲ",
        "title": "성능 및 품질",
        "sections": [
            {"number": "1", "title": "보안·성능 확보 방안", "guide": []},
            {"number": "2", "title": "테스트 및 품질 보증", "guide": []},
        ],
    },
    {
        "numeral": "Ⅳ",
        "title": "사업 관리 및 지원",
        "sections": [
            {"number": "1", "title": "추진 일정", "guide": []},
            {"number": "2", "title": "수행 조직 및 인력", "guide": []},
            {"number": "3", "title": "위험 관리", "guide": []},
            {"number": "4", "title": "교육·운영 지원", "guide": []},
        ],
    },
]


def build_presentation_deck(
    ctx: GenerationContext,
    outline: list[OutlineSection],
    *,
    template_profile: TemplateProfile | None = None,
    template_data: bytes | None = None,
    toc_tree: list[dict[str, Any]] | None = None,
) -> bytes:
    """발표용 PPT: 표지 → 사업 필요성(카드) → CONTENTS → 장마다 CHAPTER 구분·절(리드 + 도식 + 요점) → 핵심 메시지 → 마무리.

    장 뼈대는 발표용 템플릿 샘플의 장 → RFP 지정 목차 → 기본 4장 순. 도식은 모두 편집 가능한 도형이다.
    """
    b = _make_builder(template_profile, template_data, max_bullets=5, max_chars=70, body_font_pt=20)
    footer = _footer(ctx, "발표용")
    figs = key_figures(ctx)
    a = ctx.analysis or {}
    template_chapters = template_profile.chapters if template_profile else None
    skeleton = toc_tree if (toc_tree and not template_chapters) else None
    if not template_chapters and not skeleton:
        skeleton = PRESENTATION_DEFAULT_CHAPTERS
    pres_outline = [
        o for o in outline if o.key in PRESENTATION_KEYS or o.key.startswith(("generic", "agent"))
    ]
    plan = plan_chapters(pres_outline, skeleton, template_chapters)
    ctx.slide_specs["presentation"] = []
    ctx.used_pictures = set()
    b.title_slide(f"{ctx.project.name}", f"제안 발표 · {ctx.generated_on}", footer)
    # 사업 필요성·목표 (카드)
    goals = [str(g) for g in a.get("client_goals", []) or [] if g][:3]
    need_items = (
        [{"title": f"목표 {i + 1}", "text": g} for i, g in enumerate(goals)]
        if goals
        else [
            {
                "title": "요구사항",
                "text": f"{figs['requirements']} ({figs['mandatory']}) 전수 대응",
            },
            {"title": "기간", "text": figs["period"]},
            {"title": "투입", "text": f"{figs['headcount']} · {figs['total_mm']}"},
        ]
    )
    b.begin_section("제안 개요", 0)
    b.visual_slide(
        "제안 발표에 앞서 — 사업의 필요성",
        {"kind": "cards", "items": need_items},
        footer,
        lead=_first_sentence(str(a.get("overview", "") or f"{ctx.project.name} 제안 요약"), 110),
    )
    b.bullet_slides(
        "CONTENTS",
        [f"{ch.numeral}. {ch.title}" if ch.numeral else ch.title for ch in plan],
        footer,
    )
    for ch in plan:
        filled = [
            sp for sp in ch.sections if any(sub.key != "placeholder" for sub in sp.subsections)
        ]
        if not filled:
            continue  # 발표용은 내용 없는 장은 CHAPTER 슬라이드도 만들지 않는다 (CONTENTS에는 남김)
        b.begin_chapter(ch.numeral, ch.title, [sp.title for sp in filled])
        for sp in filled:
            b.begin_section(sp.title, sp.number)
            for sub in sp.subsections:
                if sub.key == "placeholder":
                    continue  # 발표용은 데이터 없는 절의 슬라이드는 만들지 않는다
                _render_section(b, ctx, sub, "발표용", compact=True)
    agent_messages = list((ctx.proposal_content or {}).get("key_messages") or [])
    figure_line = f"{figs['headcount']}, {figs['total_mm']}, 기간 {figs['period']}"
    messages = (
        (agent_messages[:3] + [figure_line])
        if agent_messages
        else [
            f"{figs['requirements']} 전수 대응",
            f"기간 {figs['period']}",
            f"{figs['headcount']}, {figs['total_mm']}",
            "출처 기반 기술 선정과 독립 검증",
        ]
    )
    b.begin_section("마무리", len(plan) + 1)
    b.key_message_slide("핵심 메시지", messages[:5], footer)
    b.bullet_slides(
        "핵심 기술과 차별점",
        [f"기술: {figs['technologies']}"]
        + [f"{t.topic[:30]}: {t.summary[:60]}" for t in ctx.research[:4]],
        footer,
    )
    claims = (ctx.proposal_content or {}).get("unverified_claims") or []
    if claims:
        b.bullet_slides("사람 확인 필요 문구", list(claims), footer)
    _render_glossary(b, ctx, footer, compact=True)
    return b.to_bytes()
