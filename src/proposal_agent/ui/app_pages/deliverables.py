"""산출물 화면: 기간 입력, 생성·QA·최종 확정, 산출물 목록(열기 검사·QA), 사람 검토 항목, Gate 4."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import GateStatus
from proposal_agent.orchestrator import StepRunner
from proposal_agent.requirements.service import GATE1_KEY
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error
from proposal_agent.validation.qa_service import GATE4_KEY

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
if b.button(
    "QA 실행 (열기·서식·일관성·추적성)",
    key="dl_qa",
    icon=":material/fact_check:",
    disabled=not gate1.passed,
):
    with st.status("QA 검사 중…", expanded=True) as status:
        try:
            outcome = runner.run_qa(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="QA 실패", state="error")
            show_error(exc, context="QA")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
gate4 = services.gates.state(project, GATE4_KEY)
if c.button(
    "최종본 확정 (13_Final_Deliverables)",
    key="dl_finalize",
    icon=":material/verified:",
    disabled=not gate4.passed,
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
ui.gate_panel(gate4)
if (
    gate4.status == GateStatus.NEEDS_HUMAN_REVIEW
    and gate4.evaluation
    and not gate4.evaluation.approval_id
):
    comments = st.text_area("검토 의견 (필수)", key="gate4_comments")
    x, y = st.columns(2)
    if x.button(
        "검토 후 승인 (최종 확정 가능)",
        key="gate4_approve",
        type="primary",
        icon=":material/check:",
    ):
        try:
            services.gates.approve_human_review(
                project, GATE4_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 4 승인")
        else:
            st.rerun()
    if y.button("반려", key="gate4_reject", icon=":material/block:"):
        try:
            services.gates.reject_human_review(
                project, GATE4_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 4 반려")
        else:
            st.rerun()
