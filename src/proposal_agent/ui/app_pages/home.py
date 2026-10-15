"""시작 화면: 모드 선택, 신규 프로젝트 생성, 기존 프로젝트 열기."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import ProjectMode
from proposal_agent.ui.state import (
    ACTOR_KEY,
    actor_name,
    api_key_banner,
    get_services,
    select_project,
    show_error,
)

st.title("Proposal Writer Agent")
st.caption("SI 제안 단계와 구축 단계를 지원하는 멀티 에이전트 작업 공간")

services = get_services()
api_key_banner()

with st.sidebar:
    st.text_input(
        "작업자 이름", key=ACTOR_KEY, value=actor_name(), help="승인·감사 이력에 기록됩니다."
    )

tab_new, tab_open = st.tabs(["신규 프로젝트 생성", "기존 프로젝트 열기"])

with tab_new:
    mode_label = st.segmented_control(
        "프로젝트 모드",
        options=[m.label for m in ProjectMode],
        default=ProjectMode.PROPOSAL.label,
        key="new_mode",
    )
    mode = (
        next(m for m in ProjectMode if m.label == mode_label)
        if mode_label
        else ProjectMode.PROPOSAL
    )
    if mode == ProjectMode.PROPOSAL:
        st.info("제안 단계: RFP 업로드가 필수입니다.", icon=":material/upload_file:")
    else:
        st.info(
            "구축 단계: 요구사항 정의서·요구사항 추적표·WBS가 필수, 인력 투입계획서는 선택입니다.",
            icon=":material/upload_file:",
        )

    with st.form("new_project_form", clear_on_submit=False):
        name = st.text_input("프로젝트명", key="new_name", max_chars=200)
        client = st.text_input("발주처 (선택)", key="new_client")
        c1, c2 = st.columns(2)
        start = c1.date_input("과제 시작일", value=date.today(), key="new_start")
        end = c2.date_input("과제 종료일", value=date.today() + timedelta(days=180), key="new_end")
        submitted = st.form_submit_button("프로젝트 생성", type="primary", icon=":material/add:")

    if submitted:
        try:
            project = services.projects.create(
                name=name,
                mode=mode,
                start_date=start,
                end_date=end,
                client_name=client,
                created_by=actor_name(),
            )
        except PWAError as exc:
            show_error(exc, context="프로젝트 생성")
        else:
            select_project(project.id)
            st.success(
                f"프로젝트를 생성했습니다: {project.name} ({project.mode.label})",
                icon=":material/check:",
            )
            st.page_link(
                "ui/app_pages/project.py",
                label="프로젝트 화면으로 이동",
                icon=":material/arrow_forward:",
            )

with tab_open:
    filter_label = st.segmented_control(
        "모드 필터",
        options=["전체", *[m.label for m in ProjectMode]],
        default="전체",
        key="open_filter",
    )
    mode_filter = next((m for m in ProjectMode if m.label == filter_label), None)
    try:
        projects = services.projects.list_projects(mode_filter)
    except PWAError as exc:
        show_error(exc, context="프로젝트 목록")
        projects = []

    if not projects:
        st.info("등록된 프로젝트가 없습니다.")
    else:
        options = {
            f"{p.name} · {p.mode.label} · {p.created_at:%Y-%m-%d} · {p.output_dir}": p.id
            for p in projects
        }
        choice = st.selectbox("프로젝트 선택", options=list(options), key="open_choice")
        if st.button("열기", key="open_button", icon=":material/folder_open:"):
            try:
                project = services.projects.open(options[choice], actor=actor_name())
            except PWAError as exc:
                show_error(exc, context="프로젝트 열기")
            else:
                select_project(project.id)
                st.success(f"프로젝트를 열었습니다: {project.name}", icon=":material/check:")
                st.page_link(
                    "ui/app_pages/project.py",
                    label="프로젝트 화면으로 이동",
                    icon=":material/arrow_forward:",
                )
