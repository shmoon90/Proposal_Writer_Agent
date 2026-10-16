"""산출물 화면: 기간 입력, 생성·QA·최종 확정, 산출물 목록(열기 검사·QA), 사람 검토 항목, Gate 4."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import GateStatus, QaCategory
from proposal_agent.orchestrator import StepRunner
from proposal_agent.requirements.service import GATE1_KEY
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error
from proposal_agent.validation.qa_service import GATE4_KEY, GATE5_KEY
from proposal_agent.validation.render import com_available

services = get_services()
project = current_project()
if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.stop()

ui.project_header(project)
st.subheader("제안 단계 산출물")
runner = StepRunner(services)
gate1 = services.gates.state(project, GATE1_KEY)
if not gate1.passed:
    st.error(
        f"{gate1.title} 미통과 ({gate1.status.value}). 요구사항 추출·독립 검증을 완료하고 승인해야 산출물을 생성할 수 있습니다.",
        icon=":material/block:",
    )

with st.expander(
    "과제 기간 (UI 입력이 RFP 기간보다 우선)",
    expanded=not (project.start_date and project.end_date),
):
    c1, c2 = st.columns(2)
    start = c1.date_input("과제 시작일", value=project.start_date, key="dl_start")
    end = c2.date_input("과제 종료일", value=project.end_date, key="dl_end")
    if st.button("기간 저장", key="dl_save_period", icon=":material/save:"):
        try:
            project.start_date, project.end_date = start, end
            services.ctx.repos.projects.update(project)
        except Exception as exc:  # noqa: BLE001
            show_error(PWAError(str(exc)), context="기간 저장")
        else:
            st.success("저장했습니다.", icon=":material/check:")
            st.rerun()

with st.expander("제안서 템플릿 (프로젝트 화면에서 '제안서 템플릿(PPT)'로 등록)", expanded=False):
    hits = services.templates.profiles(project)
    if not hits:
        st.info(
            "등록된 템플릿이 없습니다. 코드 기본 양식(16:9)으로 생성됩니다. 고객 양식 PPTX를 등록하면 "
            "그 용지·머리글·글꼴·장 구성에 맞춰 제출용 제안서를 만듭니다."
        )
    for hit in hits:
        prof = hit.profile
        st.markdown(
            f"**{hit.document.file_name}** — 용도 `{prof.purpose}` · 용지 {prof.slide_width_cm}×{prof.slide_height_cm} cm · "
            f"머리글 {len(prof.headers)}단 · 장 {len(prof.chapters)}개 · 글꼴 {prof.fonts.get('title')}/{prof.fonts.get('body')}"
        )
        st.code(prof.summary_text(), language=None)
        if prof.warnings:
            st.warning("; ".join(prof.warnings), icon=":material/warning:")
    tree = services.extraction.rfp_proposal_toc_tree(project)
    if tree:
        st.caption("RFP 지정 제안서 목차 (장/절) — 제출용 PPT의 장·절 뼈대로 사용")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "장": f"{ch.get('numeral', '')} {ch.get('title', '')}".strip(),
                        "절": "; ".join(
                            f"{i + 1}. {s.get('title', '')}"
                            for i, s in enumerate(ch.get("sections", []))
                        ),
                    }
                    for ch in tree
                ]
            ),
            hide_index=True,
            alt="RFP 지정 목차",
        )

st.divider()
st.subheader("목차·전략 브리프 (Gate P — 승인 후 전체 제안서 작성)")
gate_p = services.strategy.gate_state(project)
brief = services.strategy.latest(project)
sb1, sb2 = st.columns([1, 2])
if sb1.button(
    "전략·목차 브리프 작성 (에이전트)",
    key="dl_strategy",
    icon=":material/map:",
    disabled=not gate1.passed,
    help="RFP 분석 요약·요구사항 대응 방향·목차 초안·전략 3~5·차별화·핵심 기술·위험·제출/발표 차이·확인 필요 사항을 정리합니다. 반려 의견이 있으면 반영해 다시 씁니다.",
):
    with st.status("브리프를 작성하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_strategy_brief(
                project,
                actor=actor_name(),
                reviewer_comments=str(st.session_state.get("gateP_comments", "") or ""),
            )
        except PWAError as exc:
            status.update(label="브리프 작성 실패", state="error")
            show_error(exc, context="전략 브리프")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
sb2.caption(
    f"{gate_p.title}: **{gate_p.status.value}**"
    + (f" · 승인자 {gate_p.approved_by}" if gate_p.approved_by else "")
    + (" · 브리프 작성됨" if brief else " · 브리프 미작성")
)
if gate_p.evaluation and gate_p.evaluation.reasons:
    st.caption("평가 사유: " + " / ".join(gate_p.evaluation.reasons[:4]))
if brief:
    with st.expander("브리프 내용 (검토용)", expanded=not gate_p.passed):
        st.markdown(services.strategy.markdown(project, brief))
if not gate_p.passed:
    st.text_area(
        "검토 의견 (승인·반려 사유, 반려 시 재작성에 반영)",
        key="gateP_comments",
        help="브리프 없이 승인하면 코드 기본 목차·데이터 기반 문안으로 작성됩니다.",
    )
    g1, g2 = st.columns(2)
    if g1.button(
        "검토 후 Gate P 승인",
        key="gateP_approve",
        type="primary",
        icon=":material/check:",
        disabled=not gate1.passed,
    ):
        try:
            services.strategy.ensure_evaluation(project, actor=actor_name())
            services.gates.approve_human_review(
                project,
                "gateP",
                approver=actor_name(),
                comments=str(st.session_state.get("gateP_comments", "") or ""),
            )
        except PWAError as exc:
            show_error(exc, context="Gate P 승인")
        else:
            st.success(
                "목차·전략을 승인했습니다. 제안 문안 작성과 최종 확정이 열립니다.",
                icon=":material/check:",
            )
            st.rerun()
    if g2.button(
        "반려 (수정 요청)", key="gateP_reject", icon=":material/undo:", disabled=not gate1.passed
    ):
        try:
            services.strategy.ensure_evaluation(project, actor=actor_name())
            services.gates.reject_human_review(
                project,
                "gateP",
                approver=actor_name(),
                comments=str(st.session_state.get("gateP_comments", "") or ""),
            )
        except PWAError as exc:
            show_error(exc, context="Gate P 반려")
        else:
            st.info(
                "반려했습니다. 의견을 반영해 브리프를 다시 작성하십시오.", icon=":material/info:"
            )
            st.rerun()

w1, w2 = st.columns([1, 2])
if w1.button(
    "제안 문안 작성 (에이전트)",
    key="dl_write",
    icon=":material/edit_note:",
    disabled=not (gate1.passed and gate_p.passed),
    help="(Gate P 승인 후) 템플릿 관행·RFP 지정 목차·기준 데이터를 넣어 proposal_writer 에이전트가 장·절·소절 문안을 작성합니다. 이후 '산출물 생성'이 이 문안을 씁니다.",
):
    with st.status("제안 문안을 작성하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_proposal_writing(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="문안 작성 실패", state="error")
            show_error(exc, context="제안 문안 작성")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
prior = services.steps.prior_output(project, "proposal_writer")
w2.caption(
    f"저장된 제안 문안: 섹션 {len(prior.get('sections', []))}개"
    if prior
    else "저장된 제안 문안 없음 (코드 기본 문안으로 생성)"
)

a, b, c = st.columns(3)
if a.button(
    "산출물 생성 (계획·구성도·Excel·PPT)",
    key="dl_generate",
    type="primary",
    icon=":material/build:",
    disabled=not gate1.passed,
):
    with st.status("산출물을 생성하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_generation(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="생성 실패", state="error")
            show_error(exc, context="산출물 생성")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
_com_ok, _com_why = com_available()
_cat_options = {
    c.label: c
    for c in (
        QaCategory.RFP_FIT,
        QaCategory.TECH_FEASIBILITY,
        QaCategory.CONSISTENCY,
        QaCategory.FILE_QUALITY,
        QaCategory.EDITABILITY,
    )
}
with st.expander("제안서 분량 (단계 4)", expanded=False):
    _ps = services.projects.settings_of(project)
    _lvl = st.radio(
        "분량 모드",
        ["detailed", "summary"],
        index=0 if _ps.proposal_detail_level != "summary" else 1,
        format_func=lambda v: (
            "상세 (절차 상세·대안 비교·데이터·비기능 표 포함)"
            if v == "detailed"
            else "요약 (구조·절차·적용 기술·구현방안 표만)"
        ),
        horizontal=True,
        key="dl_detail_level",
    )
    _cap = st.number_input(
        "묶음 소절당 제출용 장 수 상한 (0 = 제한 없음)",
        min_value=0,
        max_value=20,
        value=int(_ps.max_slides_per_group or 0),
        key="dl_group_cap",
    )
    if st.button("분량 설정 저장", key="dl_save_detail", icon=":material/save:"):
        try:
            services.projects.update_settings(
                project,
                _ps.model_copy(
                    update={
                        "proposal_detail_level": _lvl,
                        "max_slides_per_group": int(_cap) or None,
                    }
                ),
                actor=actor_name(),
            )
        except PWAError as exc:
            show_error(exc, context="분량 설정")
        else:
            st.success("저장했습니다. 다음 산출물 생성부터 적용됩니다.", icon=":material/check:")

qa_render = st.checkbox(
    f"실제 렌더링·재열기 검증 (PowerPoint COM — {_com_why})",
    value=_com_ok,
    key="dl_qa_render",
    disabled=not _com_ok,
    help="제출용·발표용 PPT를 PowerPoint로 열어 슬라이드마다 PNG(11_QA_Validation_Reports/render)로 내보내고 재열기를 확인합니다. PowerPoint가 없으면 QA-FILE-14는 '미실행'으로 기록됩니다.",
)
qa_cats = st.multiselect(
    "QA 범주 (비우면 전체; 내용·파일/디자인·편집 가능성을 나눠 실행 가능)",
    options=list(_cat_options),
    default=[],
    key="dl_qa_categories",
)
if b.button(
    "QA 실행 (열기·서식·일관성·추적성·편집 가능성)",
    key="dl_qa",
    icon=":material/fact_check:",
    disabled=not gate1.passed,
):
    with st.status("QA 검사 중…", expanded=True) as status:
        try:
            outcome = runner.run_qa(
                project,
                actor=actor_name(),
                render_check=bool(qa_render),
                categories={_cat_options[x] for x in qa_cats} or None,
            )
        except PWAError as exc:
            status.update(label="QA 실패", state="error")
            show_error(exc, context="QA")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
gate4 = services.gates.state(project, GATE4_KEY)
gate5 = services.gates.state(project, GATE5_KEY)
if c.button(
    "최종본 확정 (13_Final_Deliverables)",
    key="dl_finalize",
    icon=":material/verified:",
    disabled=not gate5.passed,
):
    try:
        outcome = runner.run_finalize(project, approver=actor_name(), comments="UI 최종 확정")
    except PWAError as exc:
        show_error(exc, context="최종 확정")
    else:
        st.success(outcome.summary, icon=":material/check:")

latest = services.generation.latest_deliverables(project)
if latest:
    st.markdown("#### 생성된 산출물 (임시본)")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "종류": d.kind.value,
                    "파일": d.file_path,
                    "버전": d.version,
                    "열기 검사": d.integrity_status.value,
                    "QA": d.qa_status.value,
                    "SHA256": d.sha256[:12],
                }
                for d in latest.values()
            ]
        ),
        hide_index=True,
        alt="산출물 목록",
    )
    for kind in ("system_diagram_png", "sw_diagram_png", "service_diagram_png"):
        for d in latest.values():
            if d.kind.value == kind:
                st.image(
                    str(services.ctx.paths.resolve_output(d.file_path)),
                    caption=d.file_path,
                    alt=d.kind.value,
                )
    with st.expander("렌더링 미리보기 (단계 4: PowerPoint 렌더링 PNG)", expanded=False):
        from proposal_agent.validation.render import render_pptx

        _render_root = (
            services.ctx.paths.resolve_output(project.output_dir)
            / "11_QA_Validation_Reports"
            / "render"
        )
        _decks = (
            sorted(p.name for p in _render_root.iterdir() if p.is_dir())
            if _render_root.exists()
            else []
        )
        _ok, _why = com_available()
        if st.button(
            "지금 렌더링 (최신 제출용·발표용)",
            key="dl_render_now",
            icon=":material/preview:",
            disabled=not _ok,
            help=_why,
        ):
            for d in latest.values():
                if d.kind.value in ("submission_pptx", "presentation_pptx"):
                    src = services.ctx.paths.resolve_output(d.file_path)
                    res = render_pptx(src, _render_root / src.stem)
                    st.write(f"{src.name}: {res.summary}")
            st.rerun()
        if not _decks:
            st.caption(
                "렌더링 결과가 없습니다. QA 에서 '실제 렌더링' 을 켜거나 위 버튼으로 렌더링하십시오."
            )
        else:
            _deck = st.selectbox("덱", _decks, key="dl_preview_deck")
            _pngs = sorted((_render_root / _deck).glob("slide_*.png"))
            if _pngs:
                _n = st.slider("슬라이드", 1, len(_pngs), 1, key="dl_preview_slide")
                st.image(
                    str(_pngs[_n - 1]),
                    caption=f"{_deck} — {_n}/{len(_pngs)}",
                    alt=f"{_deck} 슬라이드 {_n}",
                )
    with st.expander(
        "슬라이드 명세 (Phase 19: 결론형 제목·목적·독자·근거·레이아웃)", expanded=False
    ):
        import json as _json

        for sub, label in (
            ("07_Submission_Proposal_PPT", "제출용"),
            ("08_Presentation_PPT", "발표용"),
        ):
            folder = services.ctx.paths.resolve_output(project.output_dir) / sub
            files = sorted(folder.glob(f"슬라이드명세_{label}_v*.json")) if folder.exists() else []
            if not files:
                st.caption(f"{label}: 슬라이드 명세 없음 (산출물 생성 시 기록)")
                continue
            try:
                spec = _json.loads(files[-1].read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                st.caption(f"{label}: 명세 읽기 실패 — {exc}")
                continue
            summ = spec.get("summary", {})
            st.markdown(
                f"**{label}** `{files[-1].name}` · 슬라이드 {summ.get('slides', 0)} · 소절 {summ.get('sections', 0)} "
                f"(에이전트 {summ.get('agent_sections', 0)}) · 용어 {summ.get('glossary_terms', 0)} · "
                f"결론형 제목 없음 {len(summ.get('sections_without_key_message', []))} · "
                f"근거 없음 {len(summ.get('sections_without_evidence', []))}"
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "No": x["slide_no"],
                            "제목": x["title"][:40],
                            "소절": x.get("number") or x.get("section_key", ""),
                            "결론형 제목": x.get("key_message", "")[:50],
                            "목적": x.get("purpose", "")[:40],
                            "독자": x.get("audience", ""),
                            "레이아웃(계획/실제)": f"{x.get('layout_type', '') or '-'} / {x.get('rendered_layout', '')}",
                            "도식": x.get("visual_kind", ""),
                            "근거": len(x.get("evidence", [])),
                            "요구사항 ID": ", ".join(x.get("requirement_ids", [])[:6]),
                        }
                        for x in spec.get("slides", [])
                    ]
                ),
                hide_index=True,
                alt=f"{label} 슬라이드 명세",
            )
else:
    st.info("아직 생성된 산출물이 없습니다.")

st.markdown("#### 인력 단가 입력 (선택 — 입력 시 비용 계산)")
wbs, deps, roles, allocs = services.planning.current_plan(project)
if roles:
    for r in roles:
        col1, col2 = st.columns([2, 1])
        col1.write(f"{r.role_name} · 인원 {r.headcount_planned} · 등급 {r.grade or '미정'}")
        raw = col2.text_input(
            "단가(원/MM)",
            value=str(r.unit_cost_per_mm or ""),
            key=f"cost_{r.id}",
            label_visibility="collapsed",
        )
        if raw != str(r.unit_cost_per_mm or ""):
            try:
                services.planning.set_unit_cost(
                    project, r.id, Decimal(raw) if raw.strip() else None, actor=actor_name()
                )
            except (InvalidOperation, PWAError) as exc:
                show_error(
                    PWAError("단가 형식 오류", cause=str(exc), resolution="숫자만 입력하십시오."),
                    context="단가",
                )
    st.caption("단가를 바꾼 뒤 산출물을 다시 생성하면 인력투입계획 비용 합계가 채워집니다.")

st.divider()
issues = [
    v
    for v in services.ctx.repos.validations.find(project.id, resolved=False)
    if v.target_type.value == "deliverable"
]
st.markdown("#### QA 지적 사항 (미해결)")
if issues:
    st.dataframe(
        pd.DataFrame(
            [
                {"수준": v.level.value, "규칙": v.rule_id, "메시지": v.message, "위치": v.target_id}
                for v in issues
            ]
        ),
        hide_index=True,
        alt="QA 지적",
    )
else:
    st.success("미해결 QA 지적 사항이 없습니다.", icon=":material/check:")
qa_run = services.qa.latest_run(project)
if qa_run is not None:
    st.markdown("#### 통합 QA (독립 검증) 결과")
    cc = qa_run.counts
    st.caption(
        f"판정 {qa_run.verdict} · 통과 {cc.get('pass', 0)} · 실패 {cc.get('fail', 0)} · 검토 필요 {cc.get('needs_human_review', 0)} · 미실행 {cc.get('not_run', 0)} · 자동 수정 {qa_run.fix_rounds}/{qa_run.max_fix_rounds}회 · 보고서 {qa_run.report_path}"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "검증 ID": ch.check_id,
                    "대상": ch.target,
                    "결과": ch.final_result.value
                    if ch.executed
                    else f"미실행 ({ch.not_run_reason})",
                    "문제": "; ".join(ch.issues)[:160],
                    "관련 ID": ", ".join(ch.requirement_ids[:4]),
                    "수정": "-"
                    if ch.fix_applied is None
                    else ("반영" if ch.fix_applied else "보류"),
                    "재검증": ch.reverified.value if ch.reverified else "-",
                }
                for ch in qa_run.checks
            ]
        ),
        hide_index=True,
        alt="통합 QA 검증 항목",
    )
    for key in ("gate2", "gate3", "gate4"):
        ui.gate_panel(services.gates.state(project, key))
ui.gate_panel(gate5)
if (
    gate5.status == GateStatus.NEEDS_HUMAN_REVIEW
    and gate5.evaluation
    and not gate5.evaluation.approval_id
):
    comments = st.text_area("검토 의견 (필수)", key="gate5_comments")
    x, y = st.columns(2)
    if x.button(
        "검토 후 승인 (최종 확정 가능)",
        key="gate5_approve",
        type="primary",
        icon=":material/check:",
    ):
        try:
            services.gates.approve_human_review(
                project, GATE5_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 5 승인")
        else:
            st.rerun()
    if y.button("반려", key="gate5_reject", icon=":material/block:"):
        try:
            services.gates.reject_human_review(
                project, GATE5_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 4 반려")
        else:
            st.rerun()
