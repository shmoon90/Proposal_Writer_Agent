"""프로젝트 화면: 입력 문서 업로드, 진행 상태, 미해결 이슈, 저장 위치, 승인 상태."""

from __future__ import annotations

import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import ApprovalDecision, DocumentKind, StepStatus
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

services = get_services()
project = current_project()

if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.page_link("ui/app_pages/home.py", label="시작 화면으로", icon=":material/home:")
    st.stop()

ui.project_header(project)

tab_input, tab_progress, tab_issues, tab_locations, tab_approvals = st.tabs(
    ["입력 문서", "진행 상태", "미해결 이슈", "저장 위치", "승인 상태"]
)

with tab_input:
    kinds = services.documents.kinds_for(project.mode)
    kind_labels = {f"{k.label} ({'필수' if req else '선택'})": k for k, req in kinds}
    chosen = st.selectbox("문서 종류", options=list(kind_labels), key="upload_kind")
    kind: DocumentKind = kind_labels[chosen]
    template_purpose: str | None = None
    if kind == DocumentKind.PROPOSAL_TEMPLATE:
        purpose_label = st.selectbox(
            "템플릿 용도",
            options=["자동 (세로=제출용, 가로=발표용)", "제출용 제안서", "발표용 제안서"],
            key="upload_template_purpose",
            help="고객사 양식 PPTX를 올리면 코드가 용지·머리글·글꼴·장 구성을 읽어 제안서 생성에 씁니다.",
        )
        template_purpose = {"제출용 제안서": "submission", "발표용 제안서": "presentation"}.get(
            purpose_label
        )
    uploaded = st.file_uploader("파일 선택", key="upload_file")
    if (
        st.button(
            "등록",
            key="upload_button",
            type="primary",
            icon=":material/upload:",
            disabled=uploaded is None,
        )
        and uploaded is not None
    ):
        try:
            doc = services.documents.register_upload(
                project,
                kind=kind,
                file_name=uploaded.name,
                data=uploaded.getvalue(),
                actor=actor_name(),
                template_purpose=template_purpose,
            )
        except PWAError as exc:
            show_error(exc, context="문서 등록")
        else:
            st.success(
                f"등록했습니다: {doc.file_name} → {doc.stored_path}", icon=":material/check:"
            )
    missing = services.documents.missing_required(project)
    if missing:
        st.warning(
            "필수 문서 미등록: " + ", ".join(k.label for k in missing), icon=":material/warning:"
        )
    else:
        st.success("필수 입력 문서가 모두 등록되었습니다.", icon=":material/check:")
    ui.input_status_panel(services.documents.input_status(project))

with tab_progress:
    views = services.pipeline.overview(project)
    ui.step_table(views, services.pipeline.progress(project))
    current = services.pipeline.current_step(project)
    if current:
        st.caption(f"현재 단계: {current.definition.title} ({current.status.label})")
    for view in views:
        run = view.run
        if run and run.status == StepStatus.NEEDS_REVIEW and view.definition.requires_gate:
            with st.container(border=True):
                st.markdown(f"**{view.definition.gate_title}** — {view.definition.title}")
                if run.summary:
                    st.write(run.summary)
                comments = st.text_area("의견 (반려 시 필수)", key=f"gate_comments_{run.id}")
                c1, c2 = st.columns(2)
                decision: ApprovalDecision | None = None
                if c1.button(
                    "승인", key=f"approve_{run.id}", type="primary", icon=":material/check:"
                ):
                    decision = (
                        ApprovalDecision.APPROVED_WITH_COMMENTS
                        if comments.strip()
                        else ApprovalDecision.APPROVED
                    )
                if c2.button("반려", key=f"reject_{run.id}", icon=":material/block:"):
                    decision = ApprovalDecision.REJECTED
                if decision is not None:
                    try:
                        services.pipeline.decide_gate(
                            project,
                            run,
                            decision=decision,
                            approver=actor_name(),
                            comments=comments,
                        )
                    except PWAError as exc:
                        show_error(exc, context="게이트 결정")
                    else:
                        st.success("결정을 기록했습니다.", icon=":material/check:")
                        st.rerun()

with tab_issues:
    ui.issues_panel(services.pipeline.open_issues(project))
    with st.expander("최근 오류 이벤트"):
        events = services.ctx.repos.audit.recent(project.id, limit=20, errors_only=True)
        if not events:
            st.write("오류 이벤트가 없습니다.")
        for e in events:
            err = e.error or {}
            st.markdown(
                f"- `{e.at:%Y-%m-%d %H:%M}` **{e.action}** — {err.get('message', '')}  \n"
                f"  원인: {err.get('cause', '')} · 조치: {err.get('resolution', '')}"
            )

with tab_locations:
    ui.locations_panel(services.projects.locations(project))

with tab_approvals:
    ui.approvals_panel(services.pipeline.gate_history(project))
