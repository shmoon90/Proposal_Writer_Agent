"""에이전트·MCP 화면: 역할별 권한 표, 연결 점검, RFP 분석·기술 조사 실행, 조사 결과·출처."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.agents.roles import ROLES
from proposal_agent.config.errors import PWAError
from proposal_agent.orchestrator import StepRunner
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import (
    actor_name,
    api_key_banner,
    current_project,
    get_services,
    show_error,
)

services = get_services()
project = current_project()
if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.stop()

ui.project_header(project)
st.subheader("에이전트 역할과 도구 권한")
api_key_banner()
runner = StepRunner(services)

st.dataframe(
    pd.DataFrame(
        [
            {
                "역할": r.title,
                "key": r.key,
                "내장 도구": ", ".join(r.builtin_tools) or "-",
                "MCP": ", ".join(r.mcp_servers) or "-",
                "턴": r.max_turns,
                "예산($)": r.max_budget_usd,
                "시간(s)": r.timeout_s,
                "재시도": r.retries,
                "재사용": ", ".join(r.reuses) or "-",
            }
            for r in ROLES.values()
        ]
    ),
    hide_index=True,
    alt="에이전트 역할별 권한",
)

with st.expander("MCP·도구 연결 점검 (모델 호출 없음)"):
    role_key = st.selectbox(
        "역할", options=list(ROLES), key="conn_role", format_func=lambda k: ROLES[k].title
    )
    if st.button("연결 점검 실행", key="conn_check", icon=":material/cable:"):
        try:
            report = services.steps.check_connections(project, role_key)
        except PWAError as exc:
            show_error(exc, context="연결 점검")
        else:
            rows = [
                {"서버": k, "상태": v.get("status"), "오류": v.get("error") or ""}
                for k, v in report.servers.items()
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, alt="MCP 서버 연결 상태")
            st.write("노출된 도구:", report.tools)
            if report.error:
                st.warning(f"세션 결과 오류: {report.error}", icon=":material/warning:")

st.divider()
st.subheader("RFP 분석 · 기술 조사")
c1, c2 = st.columns(2)
if c1.button("RFP 분석 실행 (에이전트)", key="run_rfp_analysis", icon=":material/analytics:"):
    with st.status("RFP 분석 중…", expanded=True) as status:
        try:
            outcome = runner.run_rfp_analysis(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="RFP 분석")
        else:
            status.update(label=outcome.summary, state="complete")
if c2.button(
    "기술 조사 실행 (에이전트, 웹 검색)", key="run_research", icon=":material/travel_explore:"
):
    with st.status("기술 조사 중…", expanded=True) as status:
        try:
            outcome = runner.run_tech_research(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="기술 조사")
        else:
            status.update(label=outcome.summary, state="complete")

missing_approach = services.approach.missing(project)
d1, d2 = st.columns([1, 2])
if d1.button(
    "구현 방안 작성 (에이전트)",
    key="run_approach",
    icon=":material/engineering:",
    help="요구사항 정의서의 '구현방안·난이도·검증 방법·검사 기준'을 요구사항마다 짧게 씁니다. 조사·구성 요소 근거가 있는 것만 구체화하고, 빠진 항목은 규칙 초안([자동 초안])으로 채웁니다.",
):
    with st.status("요구사항별 구현 방안을 작성하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_approach_writing(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="구현 방안 작성")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
d2.caption(
    f"구현 방안이 비어 있는 요구사항 {len(missing_approach)}건"
    + (f" ({', '.join(r.id for r in missing_approach[:6])}…)" if missing_approach else "")
    + " — 산출물 생성 시 빈 항목은 규칙 초안으로 채워지고 QA-CON-09가 확인을 요구합니다."
)

e1, e2 = st.columns([1, 2])
if e1.button(
    "구현 설계 작성 (에이전트, 웹 검색)",
    key="run_design",
    icon=":material/architecture:",
    help="요구사항 묶음마다 실제 구현 방법을 설계합니다: 구현 구조(구성 요소·계층·기술), 처리 절차(담당·처리·분기), 적용 기술과 선정 이유·대안·근거, 데이터·인터페이스. 제안서 묶음 소절의 도식·표가 됩니다 (Phase 23).",
):
    with st.status("요구사항 묶음별 구현 설계를 작성하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_design_writing(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="구현 설계 작성")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
e2.caption(
    services.design.summary(project)
    if services.design.designs(project)
    else "구현 설계 없음 — 실행하지 않으면 묶음 소절은 정의서 구현방안 표와 기능 블록 도식만 싣고 QA-CON-13 이 검토를 요구합니다."
)

analysis = services.steps.prior_output(project, "rfp_analyst")
if analysis:
    with st.expander("RFP 분석 결과 (최신)"):
        st.json(analysis, expanded=False)

topics = services.research.identify_topics(project, analysis)
with st.expander(f"조사 주제 후보 (코드 식별, {len(topics)}건)"):
    st.dataframe(
        pd.DataFrame(
            [
                {"주제": t.topic, "요구사항": ", ".join(t.requirement_ids), "사유": t.reason}
                for t in topics
            ]
        ),
        hide_index=True,
        alt="조사 주제 후보",
    )

items = services.research.list_research(project)
if items:
    st.markdown("#### 기술 조사 결과")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": t.id,
                    "주제": t.topic,
                    "구현 가능성": t.feasibility.value,
                    "조사일": str(t.investigated_at),
                    "출처 수": len(t.sources),
                    "미확인": len(t.unverified_items),
                    "요구사항": ", ".join(t.related_requirement_ids),
                    "사람 확인": "예" if t.verified_by_human else "",
                }
                for t in items
            ]
        ),
        hide_index=True,
        alt="기술 조사 결과 목록",
    )
    sel = st.selectbox(
        "조사 항목",
        options=[t.id for t in items],
        key="research_sel",
        format_func=lambda i: next(t.topic for t in items if t.id == i),
    )
    rec = next(t for t in items if t.id == sel)
    st.write(rec.summary)
    st.markdown("**확인된 사실**")
    st.write(rec.confirmed_facts or "(없음)")
    st.markdown("**적용 조건**")
    st.write(rec.applicability_conditions or "(없음)")
    st.markdown("**미확인 사항**")
    st.write(rec.unverified_items or "(없음)")
    st.markdown("**출처**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "URL": s.url,
                    "문서": s.title,
                    "제품": s.product,
                    "버전": s.version,
                    "신뢰도(에이전트)": s.trust.value,
                    "신뢰도(규칙)": s.trust_by_rule.value if s.trust_by_rule else "",
                    "조사일": str(s.accessed_at.date()),
                }
                for s in rec.sources
            ]
        ),
        hide_index=True,
        alt="출처 목록",
    )
    st.caption(
        f"구현 영향: {rec.impact_on_implementation or '-'} · 제안서 영향: {rec.impact_on_proposal or '-'}"
    )
    if not rec.verified_by_human and st.button(
        "사람 확인 완료", key=f"verify_{rec.id}", icon=":material/check:"
    ):
        services.research.mark_verified(project, rec.id, actor=actor_name())
        st.rerun()

study = services.research.latest_study(project)
if study:
    with st.expander("구현 가능성 비교"):
        for c in study.comparisons:
            st.markdown(
                f"**{c.area}** — RFP 명시: {c.rfp_specified or '없음'} · 추천: {c.recommendation}"
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {"대안": a.name, **a.scores, "라이선스·비용": a.license_and_cost}
                        for a in c.alternatives
                    ]
                ),
                hide_index=True,
                alt=f"{c.area} 대안 비교",
            )
            if c.unverified_items:
                st.caption("미확인: " + "; ".join(c.unverified_items))
