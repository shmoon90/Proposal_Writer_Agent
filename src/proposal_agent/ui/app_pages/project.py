"""프로젝트 화면: 입력 문서 업로드, 진행 상태, 미해결 이슈, 저장 위치, 승인 상태."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import (
    ApprovalDecision,
    DeliverableKind,
    DocumentKind,
    ProjectSettings,
    StepStatus,
    TechSelectionMode,
    TechStack,
)
from proposal_agent.models.settings import TECH_AREAS
from proposal_agent.orchestrator.runner import StepRunner
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

tab_input, tab_settings, tab_plan, tab_progress, tab_issues, tab_locations, tab_approvals = st.tabs(
    ["입력 문서", "설정", "실행 계획", "진행 상태", "미해결 이슈", "저장 위치", "승인 상태"]
)


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def _decimal(value: str) -> Decimal | None:
    value = (value or "").replace(",", "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"숫자가 아닙니다: {value}") from exc


with tab_settings:
    cur = services.projects.settings_of(project)
    st.caption(
        "착수 설정 (지시문 §3). 비워 두면 '미정'으로 다루며, RFP 명시 기술이 있는 사업에서 기술 선택 모드를 바꾸려면 사유가 필요합니다."
    )
    with st.form("project_settings_form"):
        description = st.text_area("사업 설명", value=cur.description, key="ps_desc")
        c1, c2, c3 = st.columns(3)
        budget = c1.text_input(
            "예산 (원)", value=str(cur.budget_amount) if cur.budget_amount is not None else ""
        )
        budget_note = c2.text_input("예산 비고", value=cur.budget_note)
        effort = c3.text_input(
            "공수 상한 (M/M)",
            value=str(cur.effort_limit_mm) if cur.effort_limit_mm is not None else "",
        )
        sched = st.text_area(
            "일정 제약 (줄마다 하나)", value="\n".join(cur.schedule_constraints), height=80
        )
        e1, e2 = st.columns([1, 2])
        existing_label = e1.selectbox(
            "기존 시스템",
            ["미확인", "있음", "없음"],
            index={None: 0, True: 1, False: 2}[cur.has_existing_system],
        )
        existing_note = e2.text_input("기존 시스템 설명", value=cur.existing_system_note)
        modes = list(TechSelectionMode)
        mode = st.selectbox(
            "기술 선택 모드",
            modes,
            index=modes.index(cur.tech_selection_mode),
            format_func=lambda m: m.label,
        )
        mode_reason = st.text_input(
            "기술 선택·변경 사유 (RFP 명시 기술을 바꿀 때 필수)", value=cur.tech_selection_reason
        )
        rfp_tech = st.text_area(
            "RFP 명시 기술 (줄마다 하나)", value="\n".join(cur.rfp_specified_tech), height=70
        )
        st.markdown("**기술 스택** (제품·버전, 미정이면 비움)")
        stack_values: dict[str, str] = {}
        cols = st.columns(2)
        for i, (key, label) in enumerate(TECH_AREAS):
            stack_values[key] = cols[i % 2].text_input(
                label, value=getattr(cur.tech_stack, key), key=f"ps_stack_{key}"
            )
        sec = st.text_area(
            "보안·개인정보 요구 (줄마다 하나)",
            value="\n".join(cur.security_privacy_requirements),
            height=70,
        )
        s1, s2 = st.columns(2)
        ext = s1.text_area(
            "외부 솔루션 (줄마다 하나)", value="\n".join(cur.external_solutions), height=70
        )
        integ = s2.text_area(
            "연계 시스템 (줄마다 하나)", value="\n".join(cur.integration_systems), height=70
        )
        kind_options = [k.value for k in DeliverableKind]
        chosen_kinds = st.multiselect(
            "산출물 종류",
            options=sorted(set(kind_options) | set(cur.deliverable_kinds)),
            default=cur.deliverable_kinds,
        )
        formats = st.text_input("제출 형식 (쉼표 구분)", value=", ".join(cur.deliverable_formats))
        rates = st.text_area(
            "역할별 단가 (원/M/M, '역할=금액' 줄마다 하나 — 사업성 평가·비용 산정용, 없으면 산정하지 않음)",
            value="\n".join(f"{k}={v}" for k, v in cur.cost_rates.items()),
            height=80,
        )
        overhead = st.text_input(
            "간접비율 (예: 0.2)",
            value=str(cur.overhead_ratio) if cur.overhead_ratio is not None else "",
        )
        notes = st.text_area("비고", value=cur.notes, height=60)
        saved = st.form_submit_button("설정 저장", type="primary", icon=":material/save:")
    if saved:
        try:
            cost_rates: dict[str, Decimal] = {}
            for line in _lines(rates):
                if "=" not in line:
                    raise ValueError(f"'역할=금액' 형식이 아닙니다: {line}")
                rate_key, rate_val = line.split("=", 1)
                rate = _decimal(rate_val)
                if rate is None:
                    raise ValueError(f"금액이 비었습니다: {line}")
                cost_rates[rate_key.strip()] = rate
            new_settings = ProjectSettings(
                description=description,
                schedule_constraints=_lines(sched),
                budget_amount=_decimal(budget),
                budget_note=budget_note,
                effort_limit_mm=_decimal(effort),
                has_existing_system={"미확인": None, "있음": True, "없음": False}[existing_label],
                existing_system_note=existing_note,
                tech_selection_mode=mode,
                tech_selection_reason=mode_reason,
                tech_stack=TechStack(**{k: v.strip() for k, v in stack_values.items()}),
                rfp_specified_tech=_lines(rfp_tech),
                security_privacy_requirements=_lines(sec),
                external_solutions=_lines(ext),
                integration_systems=_lines(integ),
                deliverable_kinds=list(chosen_kinds),
                deliverable_formats=[x.strip() for x in formats.split(",") if x.strip()],
                cost_rates=cost_rates,
                overhead_ratio=_decimal(overhead),
                notes=notes,
            )
            services.projects.update_settings(project, new_settings, actor=actor_name())
        except (PWAError, ValueError) as exc:
            show_error(exc, context="프로젝트 설정 저장")
        else:
            st.success("설정을 저장했습니다.", icon=":material/check:")
            st.rerun()
    with st.expander("현재 설정 요약", expanded=False):
        for line in cur.summary_lines():
            st.markdown(f"- {line}")

with tab_plan:
    st.caption(
        "실행 계획 미리보기 (지시문 §16): 선택한 단계만, 실패한 단계만, 또는 백그라운드로 실행합니다. 게이트가 있는 단계는 승인 뒤 다음 단계로 넘어갑니다."
    )
    runner = StepRunner(services)
    defs = services.pipeline.definitions(project.mode)
    options = [d.key for d in defs if d.key in StepRunner.DISPATCHABLE]
    titles = {d.key: d.title for d in defs}
    selected = st.multiselect(
        "실행할 단계",
        options=options,
        format_func=lambda k: f"{titles[k]} ({k})",
        key="plan_selected",
    )
    rows = services.pipeline.plan_preview(project, selected or None)
    ui.plan_table(rows)
    runnable = [r.key for r in rows if r.runnable]
    bg = st.checkbox(
        "백그라운드로 실행 (화면을 떠나도 계속, 진행률은 '진행 상태' 탭에서 확인)", key="plan_bg"
    )
    b1, b2, b3 = st.columns(3)
    if b1.button(
        "선택 단계 실행",
        key="plan_run",
        type="primary",
        icon=":material/play_arrow:",
        disabled=not runnable,
    ):
        if bg:
            bg_project = project
            bg_actor = actor_name()
            services.jobs.submit(
                project,
                None,
                lambda cancel: runner.run_steps(
                    bg_project, runnable, actor=bg_actor, cancel=cancel
                ),
            )
            st.info("백그라운드 작업을 시작했습니다.", icon=":material/schedule:")
        else:
            with st.status("선택 단계 실행 중…", expanded=True) as status:
                results = runner.run_steps(project, runnable, actor=actor_name())
                for key, _outcome, msg in results:
                    st.write(f"{titles.get(key, key)}: {msg}")
                status.update(label="완료", state="complete")
            st.rerun()
    failed = services.pipeline.failed_steps(project)
    if b2.button(
        f"실패한 단계만 재실행 ({len(failed)}건)",
        key="plan_rerun_failed",
        icon=":material/replay:",
        disabled=not failed,
    ):
        with st.status("실패 단계 재실행 중…", expanded=True) as status:
            for key, _outcome, msg in runner.rerun_failed(project, actor=actor_name()):
                st.write(f"{titles.get(key, key)}: {msg}")
            status.update(label="완료", state="complete")
        st.rerun()
    stale = services.jobs.stale_runs(project)
    if b3.button(
        f"끊긴 작업 정리 ({len(stale)}건)",
        key="plan_stale",
        icon=":material/cleaning_services:",
        disabled=not stale,
        help="프로세스 종료·응답 없음으로 '실행 중' 에 멈춘 작업을 실패로 정리해 재실행할 수 있게 합니다.",
    ):
        for stale_run in stale:
            services.jobs.mark_interrupted(project, stale_run, actor=actor_name())
        st.rerun()
    st.markdown("**백그라운드 작업**")
    jobs = services.jobs.running(project.id)
    ui.jobs_panel(jobs)
    for j in jobs:
        if st.button(f"중단 요청: {j.step_key}", key=f"cancel_{j.run_id}", icon=":material/stop:"):
            j.cancel.cancel()
            for running_view in services.pipeline.overview(project):
                if running_view.run and running_view.run.status == StepStatus.RUNNING:
                    services.jobs.request_cancel(running_view.run, actor=actor_name())
            st.rerun()

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
    picture_tag_sel: str | None = None
    picture_caption = ""
    if kind == DocumentKind.PICTURE:
        tag_labels = {
            "사진 (photo)": "photo",
            "일러스트 (illustration)": "illustration",
            "장식·배경 (decoration)": "decoration",
            "참고 이미지 (reference)": "reference",
        }
        picture_tag_sel = tag_labels[
            st.selectbox(
                "그림 종류 (허용 태그)",
                options=list(tag_labels),
                key="upload_picture_tag",
                help="사진·일러스트·장식·참고 이미지만 그림으로 넣습니다. 표·구조도·차트·화면은 이미지가 아니라 편집 가능한 도형으로 생성됩니다(QA-FILE-12).",
            )
        ]
        picture_caption = st.text_input(
            "그림 설명 (캡션, 제안 문안의 picture 참조 이름)", key="upload_picture_caption"
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
            file_name = uploaded.name
            if picture_tag_sel and "__" not in file_name:
                stem, _dot, ext = file_name.rpartition(".")
                file_name = f"{picture_tag_sel}__{picture_caption.strip() or stem}.{ext}"
            doc = services.documents.register_upload(
                project,
                kind=kind,
                file_name=file_name,
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
