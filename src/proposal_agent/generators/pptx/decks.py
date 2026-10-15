"""제출용·발표용 PPT 생성. 두 덱은 같은 GenerationContext 수치만 쓴다 (일치 검증은 validation/deliverables.py)."""

from __future__ import annotations

from decimal import Decimal

from proposal_agent.generators.base import GenerationContext, acceptance_label
from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.outline import OutlineSection
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


def _agent_section(ctx: GenerationContext, key: str) -> dict | None:
    for s in (ctx.proposal_content or {}).get("sections", []) or []:
        if s.get("slide_group") == key:
            return s
    return None


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


def _render_section(
    b: DeckBuilder, ctx: GenerationContext, sec: OutlineSection, profile: str, *, compact: bool
) -> None:
    footer = _footer(ctx, profile)
    figs = key_figures(ctx)
    agent = _agent_section(ctx, sec.key)
    notes = (agent or {}).get("speaker_notes", "")
    key = sec.key
    if key in ("purpose", "understanding"):
        a = ctx.analysis or {}
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
        lead = f"{figs['requirements']} ({figs['mandatory']}) — 요구사항 정의서와 동일 데이터"
        if compact:
            counts = {
                t.label: len([r for r in ctx.requirements if r.type == t]) for t in RequirementType
            }
            b.bullet_slides(
                sec.title,
                [f"{k}: {v}건" for k, v in counts.items() if v]
                + (agent or {}).get("bullets", [])[:3],
                footer,
                lead=lead,
                notes=notes,
            )
        else:
            b.table_slides(
                sec.title,
                ("ID", "요구사항", "종류", "범위", "수용", "구현 방안"),
                _requirement_rows(ctx),
                footer,
                col_widths=(1, 3, 1, 1, 1, 3),
                notes=notes or lead,
            )
    elif key == "strategy":
        bullets = (agent or {}).get("bullets") or [
            "RFP 필수 요구사항 전수 대응 및 추적성 확보 (요구사항 정의서·추적표)",
            "기술 조사 결과에 근거한 기술 선정 (출처·미확인 사항 명시)",
            "3단계 WBS와 영업일 기준 일정으로 투명한 공정 관리",
            "독립 검증과 사람 승인 게이트를 통한 품질 관리",
        ]
        b.bullet_slides(sec.title, bullets, footer, notes=notes)
    elif key in ("system_diagram", "sw_diagram", "service_diagram"):
        kind = key.split("_")[0]
        path = ctx.diagram_paths.get(kind)
        if path:
            b.image_slide(
                sec.title, path, footer, caption="자체 작성 도형 (코드 생성)", notes=notes
            )
        else:
            b.bullet_slides(sec.title, ["구성도 생성 실패 — 검토 필요"], footer)
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
        if compact and ctx.diagram_paths.get("gantt"):
            b.image_slide(sec.title, ctx.diagram_paths["gantt"], footer, caption=lead, notes=notes)
        else:
            b.table_slides(
                sec.title,
                ("WBS", "작업", "시작", "종료", "기간(일)", "공수(M/D)"),
                _schedule_rows(ctx),
                footer,
                col_widths=(1, 3, 1.3, 1.3, 1, 1),
                notes=notes or lead,
            )
            if ctx.diagram_paths.get("gantt"):
                b.image_slide("일정 (간트)", ctx.diagram_paths["gantt"], footer, caption=lead)
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
        if ctx.diagram_paths.get("staffing"):
            b.image_slide("역할별 공수", ctx.diagram_paths["staffing"], footer, caption=lead)
    elif key == "risk":
        b.bullet_slides(
            sec.title, (agent or {}).get("bullets") or _risk_bullets(ctx), footer, notes=notes
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
        b.bullet_slides(sec.title, bullets, footer, notes=notes)


def build_submission_deck(ctx: GenerationContext, outline: list[OutlineSection]) -> bytes:
    b = DeckBuilder(max_bullets=8, max_chars=110, body_font_pt=16)
    footer = _footer(ctx, "제출용")
    b.title_slide(
        f"{ctx.project.name} 제안서",
        f"{ctx.project.client_name or ''} · {ctx.generated_on}".strip(" ·"),
        footer,
    )
    b.bullet_slides("목차", [f"{i + 1}. {s.title}" for i, s in enumerate(outline)], footer)
    for sec in outline:
        _render_section(b, ctx, sec, "제출용", compact=False)
    claims = (ctx.proposal_content or {}).get("unverified_claims") or []
    if claims:
        b.bullet_slides("사람 확인 필요 문구", claims, footer)
    return b.to_bytes()


def build_presentation_deck(ctx: GenerationContext, outline: list[OutlineSection]) -> bytes:
    b = DeckBuilder(max_bullets=5, max_chars=70, body_font_pt=20)
    footer = _footer(ctx, "발표용")
    figs = key_figures(ctx)
    b.title_slide(f"{ctx.project.name}", f"제안 발표 · {ctx.generated_on}", footer)
    messages = (ctx.proposal_content or {}).get("key_messages") or [
        f"{figs['requirements']} 전수 대응",
        f"기간 {figs['period']}",
        f"{figs['headcount']}, {figs['total_mm']}",
        "출처 기반 기술 선정과 독립 검증",
    ]
    b.key_message_slide("핵심 메시지", messages, footer)
    keep = {
        "purpose",
        "understanding",
        "requirements",
        "strategy",
        "system_diagram",
        "sw_diagram",
        "service_diagram",
        "architecture",
        "schedule",
        "organization",
        "risk",
    }
    for sec in outline:
        if sec.key in keep or sec.key.startswith(("generic", "agent")):
            _render_section(b, ctx, sec, "발표용", compact=True)
    b.bullet_slides(
        "핵심 기술과 차별점",
        [f"기술: {figs['technologies']}"]
        + [f"{t.topic[:30]}: {t.summary[:60]}" for t in ctx.research[:4]],
        footer,
    )
    return b.to_bytes()
