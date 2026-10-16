"""사업성 평가·참여 의사결정 화면 (지시문 §6, 단계 2)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import BidRecommendation, FeasibilityRating, ProjectMode
from proposal_agent.orchestrator.runner import StepRunner
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

services = get_services()
project = current_project()

if project is None:
    st.warning("선택된 프로젝트가 없습니다.", icon=":material/info:")
    st.stop()
if project.mode != ProjectMode.PROPOSAL:
    st.info("사업성 평가는 제안 단계 프로젝트에서 수행합니다.", icon=":material/info:")
    st.stop()

ui.project_header(project)
st.subheader("사업 참여 타당성 평가")
st.caption(
    "코드가 RFP 분석·요구사항(품질 검토 포함)·기술 조사·프로젝트 설정·계획으로 13개 항목을 판정하고 권고를 **제안**합니다. "
    "데이터가 없는 항목은 '미확인' 이며 사용자 판정으로 덮어쓸 수 있습니다. 최종 참여 여부는 사용자가 결정해 기록합니다."
)
runner = StepRunner(services)
latest = services.feasibility.latest(project)

rating_options: list[FeasibilityRating | None] = [None, *list(FeasibilityRating)]
rating_label: dict[FeasibilityRating | None, str] = {None: "(코드 판정 사용)"}
rating_label.update({r: r.label for r in FeasibilityRating})

with st.form("feasibility_form"):
    st.markdown("**항목별 사용자 판정·메모** (비워 두면 코드 판정 사용)")
    user_inputs: dict[str, tuple[str | None, str]] = {}
    items = latest.items if latest else []
    for it in items:
        c1, c2, c3 = st.columns([2, 1, 3])
        c1.markdown(
            f"**{it.title}**  \n코드 판정: {it.rating.label}"
            + (" · 입력 필요" if it.needs_input else "")
        )
        choice = c2.selectbox(
            "판정",
            rating_options,
            index=rating_options.index(it.user_rating) if it.user_rating in rating_options else 0,
            format_func=lambda r: rating_label[r],
            key=f"fr_{it.key}",
            label_visibility="collapsed",
        )
        note = c3.text_input(
            "메모", value=it.user_note, key=f"fn_{it.key}", label_visibility="collapsed"
        )
        user_inputs[it.key] = (choice.value if choice else None, note)
    run = st.form_submit_button("평가 실행·갱신", type="primary", icon=":material/calculate:")
if run:
    try:
        outcome = runner.run_bid_assessment(
            project, actor=actor_name(), user_ratings=user_inputs or None
        )
    except PWAError as exc:
        show_error(exc, context="사업성 평가")
    else:
        st.success(outcome.summary, icon=":material/check:")
        st.rerun()

if latest is None:
    st.info(
        "아직 평가가 없습니다. '평가 실행·갱신' 을 누르십시오 (요구사항 기준선 승인 뒤 권장).",
        icon=":material/info:",
    )
    st.stop()

st.markdown(
    f"### 권고(제안): **{latest.recommendation.label}**  · 버전 {latest.version} · 상태 {latest.status}"
)
for b in latest.recommendation_basis:
    st.markdown(f"- {b}")
rows = [
    {
        "항목": it.title,
        "코드 판정": it.rating.label,
        "사용자 판정": it.user_rating.label if it.user_rating else "",
        "최종": it.final_rating.label,
        "근거": " / ".join(it.code_basis),
        "가정·확인": " / ".join(it.assumptions) + (" (입력 필요)" if it.needs_input else ""),
        "에이전트 의견": it.agent_comment,
    }
    for it in latest.items
]
st.dataframe(pd.DataFrame(rows), hide_index=True, alt="사업성 평가 항목 표")
ce = latest.cost_estimate or {}
if ce.get("status") == "estimated":
    st.markdown(
        f"**비용 산정**: 매출 {int(float(ce['revenue'])):,} 원 · 원가 {int(float(ce['cost'])):,} 원 · 마진율 {float(ce['margin_ratio']):.1%}"
    )
else:
    st.markdown(
        "**비용 산정 불가**: "
        + "; ".join(ce.get("assumptions", []))
        + " — 프로젝트 화면 '설정' 탭에서 예산·역할별 단가를 입력하면 산정됩니다."
    )
with st.expander("주요 위험·추가 확인 사항"):
    for x in latest.key_risks:
        st.markdown(f"- 위험: {x}")
    for x in latest.open_questions:
        st.markdown(f"- 확인: {x}")
if latest.report_path:
    st.caption(f"평가서: {services.ctx.paths.resolve_output(latest.report_path)}")

c1, c2 = st.columns(2)
if c1.button(
    "에이전트 검토 의견 받기",
    key="bid_review",
    icon=":material/smart_toy:",
    help="bid_reviewer 에이전트가 항목별 의견·위험·질문을 덧붙입니다 (API 키 필요, 판정은 바꾸지 않음).",
):
    with st.status("에이전트 검토 중…", expanded=True) as status:
        try:
            services.feasibility.review_with_agent(project, latest, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="에이전트 검토")
        else:
            status.update(label="완료", state="complete")
            st.rerun()
if latest.agent_review:
    with st.expander("에이전트 검토 의견", expanded=False):
        st.write(latest.agent_review.get("overall", ""))

st.markdown("### 참여 결정 기록")
if latest.decision_id:
    st.success(
        f"결정됨: {BidRecommendation(latest.decision_choice).label} (Decision {latest.decision_id})",
        icon=":material/gavel:",
    )
with st.form("bid_decision_form"):
    choices = list(BidRecommendation)
    decision_choice = st.selectbox(
        "결정", choices, index=choices.index(latest.recommendation), format_func=lambda c: c.label
    )
    rationale = st.text_area("결정 근거 (필수)", height=80)
    authority = st.checkbox("결정 권한이 확인된 결정입니다 (미확인이면 '제안' 상태로 기록)")
    decided = st.form_submit_button("결정 기록", icon=":material/gavel:")
if decided:
    try:
        d = services.feasibility.record_decision(
            project,
            latest,
            choice=decision_choice,
            rationale=rationale,
            decider=actor_name(),
            authority_confirmed=authority,
        )
    except PWAError as exc:
        show_error(exc, context="참여 결정 기록")
    else:
        st.success(
            f"{d.code} 기록 ({'공식 결정' if d.is_binding else '제안 — 권한 확인 필요'})",
            icon=":material/check:",
        )
        st.rerun()
