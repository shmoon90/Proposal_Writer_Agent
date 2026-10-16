"""설계 화면 (단계 6, 지시문 §12): 상세 설계 실행 → 화면·DB·API·모듈·업무 규칙 → 추적·모순 검사 → 설계서·코드 생성 패키지."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.orchestrator import StepRunner
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

services = get_services()
project = current_project()
if project is None:
    st.info("프로젝트를 먼저 선택하십시오.", icon=":material/info:")
    st.stop()
ui.project_header(project)
runner = StepRunner(services)
dd = services.detail_design

st.subheader("1. 상세 설계 (화면·DB·API·모듈)")
st.caption(
    "요구사항·구현 방안·묶음별 구현 설계·아키텍처와 **발주처 업무 문맥**(현행 문제점·연계 대상·제약)을 입력으로 "
    "detail_designer 에이전트가 화면 항목·검증 규칙·테이블 컬럼·API 입출력·오류 코드·코드 모듈까지 설계합니다. "
    "결과는 설계서(Excel/MD)와 코드 생성 입력 패키지(D-22)가 됩니다."
)
c1, c2 = st.columns([1, 2])
if c1.button(
    "상세 설계 실행 (에이전트)", key="dd_run", icon=":material/design_services:", type="primary"
):
    with st.status("상세 설계 중…", expanded=True) as status:
        try:
            outcome = runner.run_detail_design(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context="상세 설계")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
c2.caption(
    dd.summary(project)
    if dd.has_design(project)
    else "상세 설계 없음 — 실행하면 설계 객체가 생기고 추적표의 '미정' 열이 채워집니다."
)

screens, tables, apis, modules, rules = (
    dd.screens(project),
    dd.tables(project),
    dd.apis(project),
    dd.modules(project),
    dd.rules(project),
)
tab_s, tab_t, tab_a, tab_m, tab_r = st.tabs(["화면", "DB 테이블", "API", "모듈", "업무 규칙"])
with tab_s:
    if screens:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": s.code or s.id,
                        "화면명": s.name,
                        "유형": s.screen_type,
                        "목적": getattr(s, "purpose", "") or s.description,
                        "항목": len(getattr(s, "fields", []) or []),
                        "동작": len(getattr(s, "actions", []) or []),
                        "기능": len(getattr(s, "functions", []) or []),
                        "상태": len(getattr(s, "states", []) or []),
                        "요구사항": ", ".join(getattr(s, "related_requirement_ids", []) or []),
                        "출처": getattr(s, "source", ""),
                    }
                    for s in screens
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        pick = st.selectbox(
            "화면 상세",
            screens,
            format_func=lambda s: f"{s.code or s.id} {s.name}",
            key="dd_screen",
        )
        if getattr(pick, "fields", None):
            st.dataframe(pd.DataFrame(pick.fields), width="stretch", hide_index=True)
        if getattr(pick, "functions", None):
            st.dataframe(pd.DataFrame(pick.functions), width="stretch", hide_index=True)
        if getattr(pick, "states", None):
            st.write({x.get("state"): x.get("message") for x in pick.states})
    else:
        st.caption("화면 설계 없음")
with tab_t:
    if tables:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": t.code,
                        "물리명": t.name,
                        "논리명": t.logical_name,
                        "DB": t.db_engine,
                        "컬럼": len(t.columns),
                        "개인정보": ", ".join(c.name for c in t.columns if c.is_personal_data),
                        "보존 정책": t.retention_policy,
                        "요구사항": ", ".join(t.related_requirement_ids),
                    }
                    for t in tables
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        tp = st.selectbox(
            "테이블 상세", tables, format_func=lambda t: f"{t.code} {t.name}", key="dd_table"
        )
        st.dataframe(
            pd.DataFrame([c.model_dump() for c in tp.columns]), width="stretch", hide_index=True
        )
    else:
        st.caption("DB 설계 없음")
with tab_a:
    if apis:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": a.code,
                        "이름": a.name,
                        "메서드": a.method,
                        "경로": a.path,
                        "인증": a.auth,
                        "오류 코드": "; ".join(a.error_codes),
                        "멱등성": a.idempotency,
                        "화면": ", ".join(a.related_screen_ids),
                        "테이블": ", ".join(a.related_table_ids),
                        "요구사항": ", ".join(a.related_requirement_ids),
                    }
                    for a in apis
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("API 명세 없음")
with tab_m:
    if modules:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": m.code,
                        "경로": m.path,
                        "계층": m.layer,
                        "책임": m.description,
                        "의존": "; ".join(getattr(m, "depends_on", []) or []),
                        "요구사항": ", ".join(m.related_requirement_ids),
                        "상태": m.status,
                    }
                    for m in modules
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("모듈 분해 없음")
with tab_r:
    if rules:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "규칙": d.name,
                        "내용": d.description,
                        "적용": "; ".join(d.decisions),
                        "요구사항": ", ".join(d.related_requirement_ids),
                    }
                    for d in rules
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("업무 규칙 없음")

st.divider()
st.subheader("2. 추적 · 누락 · 모순 · DB 호환성 검사")
if dd.has_design(project):
    fails, revs = dd.consistency(project)
    if fails:
        st.error("모순·누락 " + str(len(fails)) + "건", icon=":material/error:")
        for x in fails:
            st.caption(f"✖ {x}")
    else:
        st.success("모순·누락 없음", icon=":material/check_circle:")
    for x in revs:
        st.caption(f"⚠ {x}")
else:
    st.caption("상세 설계가 없어 검사할 수 없습니다.")

st.divider()
st.subheader("3. 설계서 · 코드 생성 입력 패키지")
d1, d2 = st.columns(2)
if d1.button(
    "설계서 생성 (Excel · Markdown)",
    key="dd_docs",
    icon=":material/description:",
    disabled=not dd.has_design(project),
):
    try:
        paths = services.generation.generate_design_docs(project, actor=actor_name())
    except PWAError as exc:
        show_error(exc, context="설계서 생성")
    else:
        st.success("생성: " + ", ".join(paths), icon=":material/check:")
if d2.button(
    "코드 생성 입력 패키지 내보내기 (JSON, D-22)",
    key="dd_pkg",
    icon=":material/data_object:",
    disabled=not dd.has_design(project),
):
    try:
        rel = dd.export_codegen_package(project, actor=actor_name())
    except PWAError as exc:
        show_error(exc, context="패키지 내보내기")
    else:
        st.success(f"저장: {rel}", icon=":material/check:")
        st.caption(
            "단계 7 에서 RFP_JAVA 발췌 개발 에이전트의 입력(requirements · ui_design · architecture)으로 쓰입니다."
        )
