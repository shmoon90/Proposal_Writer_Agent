"""제출용·발표용 PPT 생성. 두 덱은 같은 GenerationContext 수치만 쓴다 (일치 검증은 validation/deliverables.py)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from proposal_agent.generators.base import GenerationContext, acceptance_label
from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.outline import (
    ChapterPlan,
    OutlineSection,
    canonical_key,
    plan_chapters,
)
from proposal_agent.generators.pptx.shapes import (
    draw_architecture,
    draw_bars,
    draw_cards,
    draw_kpis,
    draw_timeline,
    draw_two_column,
)
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
        if w.code.count(".") <= 1
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


def _render_section(
    b: Builder, ctx: GenerationContext, sec: OutlineSection, profile: str, *, compact: bool
) -> None:
    footer = _footer(ctx, profile)
    figs = key_figures(ctx)
    agent = _agent_section(ctx, sec.key, sec.agent_index)
    notes = (agent or {}).get("speaker_notes", "")
    lead = sec.lead or str((agent or {}).get("lead_message", "") or "")
    footnotes = [str(x) for x in (agent or {}).get("footnotes", []) or []]
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
        # 에이전트가 도식을 지정한 소절: 도식(편집 가능 도형) + 요점. 표가 함께 있으면 표 슬라이드도.
        b.visual_slide(
            sec.title,
            visual,
            footer,
            lead=lead,
            bullets=[
                *(["대응 요구사항: " + ", ".join(req_ids[:12])] if req_ids else []),
                *list(agent.get("bullets") or []),
            ],
            notes=notes,
        )
        _render_agent_extras(b, sec, agent, footer)
        return
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
            draw_timeline(
                slide, box, _timeline_items(ctx), ctx.period_start, ctx.period_end, style=b.style
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
        draw_bars(slide, box, _staff_bars(ctx), style=b.style)
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
    if tail_items:
        b.begin_section("부록", len(plan[-1].sections) + 1 if plan else 1)
        for title, items in tail_items:
            b.bullet_slides(title, items, footer)
    return b.to_bytes()


PRESENTATION_KEYS = {
    "purpose",
    "understanding",
    "current",
    "requirements",
    "strategy",
    "system_diagram",
    "architecture",
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
        lead=str(a.get("overview", "") or f"{ctx.project.name} 제안 요약")[:200],
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
    return b.to_bytes()
