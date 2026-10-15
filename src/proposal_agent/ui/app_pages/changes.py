"""구축 단계 화면 2: 변경 요청 등록 → 분석(규칙+AI) → 후보 확인 → 영향 분석 → 승인/반려 → 반영 결과·변경관리대장."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from proposal_agent.changes.service import CHANGE_LOG_HEADERS
from proposal_agent.config.errors import PWAError
from proposal_agent.models import ChangeStatus, InputKind, ProjectMode
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

KIND_OPTIONS = {
    "자연어 입력": InputKind.NATURAL_LANGUAGE,
    "추가 (버튼)": InputKind.ADD_BUTTON,
    "수정 (요구사항 선택)": InputKind.MODIFY_BUTTON,
    "삭제 (요구사항 선택)": InputKind.DELETE_BUTTON,
    "문서 업로드": InputKind.DOCUMENT,
}
CLASS_LABELS = {
    "ADD": "추가",
    "MODIFY": "수정",
    "DELETE_REQUEST": "삭제 요청",
    "NO_CHANGE": "변경 없음",
    "AMBIGUOUS": "모호 — 확인 필요",
}
SOURCE_LABELS = {"rule": "규칙", "ai": "AI", "rule+ai": "규칙+AI", "user": "사용자"}

services = get_services()
project = current_project()
if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.stop()
if project.mode != ProjectMode.BUILD:
    st.info("이 화면은 구축 단계(BUILD) 프로젝트에서 사용합니다.", icon=":material/info:")
    st.stop()

ui.project_header(project)
reqs = services.changes.active_requirements(project)
if not project.baseline_revision_id or not reqs:
    st.error(
        "기준 데이터가 없습니다. '구축: 기준 문서' 화면에서 기존 산출물을 업로드하고 적재하십시오.",
        icon=":material/block:",
    )
    st.stop()
staffing_present = services.changes.staffing_present(project)
req_options = [f"{r.id} · {r.name}" for r in reqs if r.change_state != "deleted"]

# --- 1. 새 변경 요청 ----------------------------------------------------------------------------
st.subheader("1. 변경 요청 등록")
kind_label = st.radio("입력 방식", list(KIND_OPTIONS), horizontal=True, key="ch_kind")
kind = KIND_OPTIONS[kind_label]
selected = []
if kind in (InputKind.MODIFY_BUTTON, InputKind.DELETE_BUTTON, InputKind.NATURAL_LANGUAGE):
    picked = st.multiselect(
        "대상 요구사항 (수정·삭제는 필수, 자연어는 선택)", req_options, key="ch_selected"
    )
    selected = [p.split(" · ")[0] for p in picked]
text = st.text_area(
    "변경 내용 (자연어, 여러 항목은 줄바꿈·번호로 구분)",
    key="ch_text",
    height=120,
    placeholder="예) 1. 민원 접수 시 SMS 알림 발송 기능 추가\n2. 주요 화면 응답 시간을 2초 이내로 변경",
)
c1, c2, c3 = st.columns(3)
requester = c1.text_input("요청자", key="ch_requester", value=actor_name())
requested_on = c2.date_input("요청일", value=date.today(), key="ch_date")
title = c3.text_input("제목 (비우면 첫 항목으로)", key="ch_title")
reason = st.text_input("변경 사유", key="ch_reason")
uploads = (
    st.file_uploader(
        "변경 요청 문서 (DOCX/PDF/TXT, 선택)",
        type=["docx", "pdf", "txt", "md"],
        accept_multiple_files=True,
        key="ch_files",
    )
    if kind == InputKind.DOCUMENT
    else []
)

with st.expander("등록 전 미리보기", expanded=False):
    st.write(
        {
            "입력 방식": kind.value,
            "대상": selected,
            "요청자": requester,
            "요청일": str(requested_on),
            "사유": reason,
            "내용": text,
            "첨부": [u.name for u in uploads or []],
            "출처": "사용자 입력 (분류·영향은 등록 후 분석 시 규칙/AI가 추론)",
        }
    )
if st.button("변경 요청 등록", key="ch_create", type="primary", icon=":material/add_circle:"):
    try:
        cr = services.changes.create_request(
            project,
            input_kind=kind,
            request_text=text,
            requester=requester,
            reason=reason,
            requested_on=requested_on,
            selected_ids=selected,
            title=title,
            attachments=[(u.name, u.getvalue()) for u in uploads or []],
            actor=actor_name(),
        )
    except PWAError as exc:
        show_error(exc, context="변경 요청 등록")
    else:
        st.session_state["ch_current"] = cr.id
        st.success(f"{cr.id} 등록 완료 — 아래에서 분석을 실행하십시오.", icon=":material/check:")
        st.rerun()

# --- 2. 요청 목록 ------------------------------------------------------------------------------
st.divider()
st.subheader("2. 변경 요청 목록")
requests = services.changes.list_requests(project)
if not requests:
    st.info("등록된 변경 요청이 없습니다.", icon=":material/info:")
    st.stop()
st.dataframe(
    pd.DataFrame(
        [
            {
                "CR ID": c.id,
                "제목": c.title,
                "상태": c.status.value,
                "요청자": c.requester,
                "요청일": c.requested_on,
                "후보": len(c.candidates),
                "Revision": c.revision_id or "",
            }
            for c in requests
        ]
    ),
    width="stretch",
    hide_index=True,
)
ids = [c.id for c in requests]
default = st.session_state.get("ch_current") or ids[-1]
cr_id = st.selectbox(
    "검토할 변경 요청",
    ids,
    index=ids.index(default) if default in ids else len(ids) - 1,
    key="ch_pick",
)
cr = services.changes.get(project, cr_id)
st.markdown(
    f"**{cr.id} · {cr.title}** — 상태 `{cr.status.value}` · 요청자 {cr.requester} · {cr.requested_on} · 사유: {cr.reason or '-'}"
)
with st.expander("요청 내용", expanded=False):
    st.text(cr.request_text)
    if cr.selected_requirement_ids:
        st.caption("대상: " + ", ".join(cr.selected_requirement_ids))

# --- 3. 분석 ------------------------------------------------------------------------------------
st.subheader("3. 의미 비교 · 영향 분석")
a, b, c = st.columns([2, 1, 1])
use_agent = a.checkbox(
    "AI 의미 비교 사용 (규칙 결과에 덧붙임; 실패 시 규칙 결과만 사용)",
    value=True,
    key="ch_use_agent",
)
if b.button(
    "분석 실행",
    key="ch_analyze",
    icon=":material/compare_arrows:",
    disabled=cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED),
):
    with st.status("비교·영향 분석 중…", expanded=True) as status:
        try:
            cr = services.changes.analyze(project, cr, actor=actor_name(), use_agent=use_agent)
        except PWAError as exc:
            status.update(label="분석 실패", state="error")
            show_error(exc, context="변경 분석")
        else:
            status.update(label="분석 완료", state="complete")
            st.rerun()
if c.button(
    "요청 철회",
    key="ch_withdraw",
    icon=":material/undo:",
    disabled=cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED, ChangeStatus.WITHDRAWN),
):
    try:
        services.changes.withdraw(project, cr, actor=actor_name())
    except PWAError as exc:
        show_error(exc, context="철회")
    else:
        st.rerun()
for note in cr.unresolved:
    st.caption(f"⚠ {note}")

if cr.candidates:
    st.markdown("**변경 후보** (분류·근거는 규칙/AI 추론, 결정·수정값은 사용자 입력으로 구분 저장)")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "후보": c.id,
                    "분류": CLASS_LABELS.get(c.classification.value, c.classification.value),
                    "대상 ID": c.requirement_id or "(신규)",
                    "관련 ID": ", ".join(c.related_ids),
                    "유사도": c.similarity,
                    "신뢰도": c.confidence,
                    "출처": SOURCE_LABELS.get(c.source, c.source),
                    "확인 필요": "예" if c.needs_confirmation else "",
                    "결정": c.user_decision or "미결정",
                    "제안 명": c.proposed_name,
                    "근거": c.rationale,
                }
                for c in cr.candidates
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    locked = cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED)
    for cand in cr.candidates:
        with st.expander(
            f"{cand.id} · {CLASS_LABELS.get(cand.classification.value)} · {cand.requirement_id or '신규'} — 결정",
            expanded=cand.user_decision is None and not locked,
        ):
            if cand.before:
                st.caption("변경 전: " + str(cand.before))
            if cand.after:
                st.caption("변경 후(제안): " + str(cand.after))
            if cand.schedule_constraint:
                st.caption(f"일정 제약 표현: {cand.schedule_constraint}")
            k1, k2, k3 = st.columns(3)
            dec = k1.radio(
                "결정",
                ["미결정", "수락", "거절"],
                index={None: 0, "accept": 1, "reject": 2}[cand.user_decision],
                key=f"ch_dec_{cr.id}_{cand.id}",
                horizontal=True,
                disabled=locked,
            )
            cls_opts = ["(유지)", "ADD", "MODIFY", "DELETE_REQUEST", "NO_CHANGE"]
            cls = k2.selectbox(
                "분류 변경", cls_opts, key=f"ch_cls_{cr.id}_{cand.id}", disabled=locked
            )
            target = k3.text_input(
                "대상 요구사항 ID",
                value=cand.requirement_id or "",
                key=f"ch_tid_{cr.id}_{cand.id}",
                disabled=locked,
            )
            desc = st.text_area(
                "요구사항 내용 (수정 가능)",
                value=str(cand.user_override.get("description", cand.proposed_description)),
                key=f"ch_desc_{cr.id}_{cand.id}",
                height=80,
                disabled=locked,
            )
            e1, e2 = st.columns(2)
            effort = e1.number_input(
                "공수 확정값 (M/D, 0 = AI/규칙 추정 사용)",
                min_value=0.0,
                value=float(cand.user_override.get("effort_md", 0) or 0),
                step=0.5,
                key=f"ch_eff_{cr.id}_{cand.id}",
                disabled=locked,
            )
            role = e2.text_input(
                "담당 역할 (신규 Task, 비우면 유사 Task 역할)",
                value=str(cand.user_override.get("role", "")),
                key=f"ch_role_{cr.id}_{cand.id}",
                disabled=locked,
            )
            if not locked and st.button(
                "결정 저장", key=f"ch_save_{cr.id}_{cand.id}", icon=":material/save:"
            ):
                overrides: dict[str, object] = {}
                if desc.strip() and desc.strip() != cand.proposed_description:
                    overrides["description"] = desc.strip()
                if target.strip() and target.strip() != (cand.requirement_id or ""):
                    overrides["requirement_id"] = target.strip()
                if effort > 0:
                    overrides["effort_md"] = effort
                if role.strip():
                    overrides["role"] = role.strip()
                try:
                    services.changes.decide_candidate(
                        project,
                        cr,
                        cand.id,
                        decision={"미결정": None, "수락": "accept", "거절": "reject"}[dec],
                        overrides=overrides,
                        classification=None if cls == "(유지)" else cls,
                        actor=actor_name(),
                    )
                except PWAError as exc:
                    show_error(exc, context="후보 결정")
                else:
                    st.rerun()

imp = cr.impact
if imp is not None:
    st.markdown("**영향 분석 (코드 계산)**")
    if imp.error:
        st.error(f"계산 중단: {imp.error}", icon=":material/error:")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("변경 전 종료", str(imp.schedule_before_end or "-"))
    m2.metric(
        "변경 후 종료",
        str(imp.schedule_after_end or "-"),
        delta=f"{imp.schedule_delta_days:+d} 영업일" if imp.schedule_delta_days else None,
        delta_color="inverse",
    )
    m3.metric("공수 순증 (M/D)", f"{imp.effort.net_md:+}", help=imp.effort.basis)
    m4.metric("인력 시나리오", imp.staffing_scenario.value, help=imp.staffing_scenario.label)
    if imp.project_end_exceeded:
        st.error("과제 종료일을 초과합니다.", icon=":material/warning:")
    st.caption(f"인력: {imp.staffing_scenario.label} — {imp.staffing_explanation}")
    if not imp.staffing_plan_present:
        st.info(
            "인력 투입계획이 업로드되지 않아 인력 자동 조정은 하지 않습니다. 필요하면 투입계획을 올리거나 새 계획 작성 여부를 결정하십시오.",
            icon=":material/info:",
        )
    e = imp.effort
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "변경 전": e.before_md,
                    "추가": e.added_md,
                    "감소": e.reduced_md,
                    "순증": e.net_md,
                    "변경 후": e.after_md,
                    "상태": e.estimate_status,
                    "범위": f"{e.range_min_md}~{e.range_max_md}"
                    if e.range_min_md is not None
                    else "-",
                }
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    if imp.tasks:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "WBS": t.wbs_code,
                        "Task": t.task_name,
                        "조치": t.action,
                        "요구사항": ", ".join(t.requirement_ids),
                        "공수 전": t.effort_before_md,
                        "추가": t.effort_added_md,
                        "감소": t.effort_reduced_md,
                        "일정 전": f"{t.before_start or ''}~{t.before_end or ''}",
                        "일정 후": f"{t.after_start or ''}~{t.after_end or ''}",
                        "근거": t.basis,
                    }
                    for t in imp.tasks
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    if imp.roles:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "역할": r.role,
                        "계획에 있음": "예" if r.exists_in_plan else "아니오",
                        "전 MM": r.before_mm,
                        "후 MM": r.after_mm,
                        "증감": r.delta_mm,
                        "계획 인원": r.headcount_before,
                        "필요 인원": r.headcount_needed,
                    }
                    for r in imp.roles
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    if imp.cost_delta is not None:
        st.caption(
            f"비용 영향(단가 입력 역할): {imp.cost_before:,} → {imp.cost_after:,} ({imp.cost_delta:+,} 원)"
        )
    with st.expander("영향 상세 (날짜 변경·의존·테스트·경고)", expanded=False):
        st.write(
            {
                "영향 받는 다른 요구사항": imp.affected_requirement_ids,
                "날짜 변경": imp.changed_task_dates,
                "의존 변경": imp.dependency_changes,
                "테스트": imp.tests_added,
                "경고": imp.warnings,
                "가정": e.assumptions,
            }
        )

# --- 4. 승인 ------------------------------------------------------------------------------------
st.subheader("4. 승인 · 반영")
blockers = services.changes.approval_blockers(cr)
if cr.status == ChangeStatus.APPLIED:
    st.success(cr.result_summary, icon=":material/check_circle:")
    st.write(
        {
            "승인자": cr.approver,
            "승인 시각": str(cr.approved_at),
            "Revision": cr.revision_id,
            "변경 전 파일": cr.before_files,
            "변경 후 파일": cr.after_files,
            "적용 요구사항": cr.applied_requirement_ids,
        }
    )
elif cr.status == ChangeStatus.REJECTED:
    st.warning(cr.result_summary, icon=":material/cancel:")
elif cr.status == ChangeStatus.ERROR:
    st.error(f"반영 중 오류 — 기준 데이터는 롤백되었습니다: {cr.error}", icon=":material/error:")
else:
    for p in blockers:
        st.caption(f"⛔ {p}")
    g1, g2 = st.columns(2)
    approver = g1.text_input("승인자", value=actor_name(), key="ch_approver")
    comments = g2.text_input("승인/반려 의견", key="ch_comments")
    upd = st.checkbox(
        "인력 투입계획도 갱신",
        value=staffing_present,
        key="ch_upd_staff",
        disabled=not staffing_present,
        help="투입계획이 업로드된 경우에만 갱신합니다.",
    )
    x1, x2 = st.columns(2)
    if x1.button(
        "승인 · 기준 반영 · 문서 재생성",
        key="ch_approve",
        type="primary",
        icon=":material/verified:",
        disabled=bool(blockers),
    ):
        with st.status("반영 중…", expanded=True) as status:
            try:
                res = services.changes.approve(
                    project, cr, approver=approver, comments=comments, update_staffing=upd
                )
            except PWAError as exc:
                status.update(label="반영 실패 (롤백됨)", state="error")
                show_error(exc, context="승인·반영")
            else:
                status.update(label=res.request.result_summary, state="complete")
                st.rerun()
    if x2.button("반려", key="ch_reject", icon=":material/block:"):
        try:
            services.changes.reject(project, cr, approver=approver, comments=comments)
        except PWAError as exc:
            show_error(exc, context="반려")
        else:
            st.rerun()
if cr.status == ChangeStatus.ERROR and st.button(
    "반영 재시도", key="ch_retry", icon=":material/refresh:"
):
    try:
        services.changes.apply(project, cr, actor=actor_name())
    except PWAError as exc:
        show_error(exc, context="재시도")
    else:
        st.rerun()

# --- 5. 변경관리대장 ----------------------------------------------------------------------------
st.divider()
st.subheader("5. 변경 이력 (변경관리대장)")
rows = services.changes.change_log_rows(project)
if rows:
    st.dataframe(
        pd.DataFrame(rows, columns=list(CHANGE_LOG_HEADERS)), width="stretch", hide_index=True
    )
revs = services.ctx.repos.revisions.find(project.id, order_by="created_at")
if revs:
    st.caption("Revision: " + " → ".join(f"{r.number} ({r.label})" for r in revs))
