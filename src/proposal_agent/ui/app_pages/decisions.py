"""회의·결정·협상 화면 (단계 5, 지시문 §10·§11): 회의록 구조화 → 사람 확정(권한 확인) → 협상 → 변경 요청 전환."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import (
    DecisionKind,
    DecisionStatus,
    DocumentKind,
    NegotiationStatus,
    ProjectMode,
)
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

KIND_LABELS = {
    DecisionKind.CUSTOMER_REQUEST: "고객 요청",
    DecisionKind.INTERNAL_OPINION: "내부 의견",
    DecisionKind.OFFICIAL_DECISION: "공식 결정",
    DecisionKind.OPEN_QUESTION: "미결 질문",
    DecisionKind.RISK_ISSUE: "위험·이슈",
    DecisionKind.ACTION_ITEM: "조치 항목",
}
STATUS_LABELS = {
    DecisionStatus.PROPOSED: "제안(미확정)",
    DecisionStatus.APPROVED: "승인",
    DecisionStatus.REJECTED: "기각",
    DecisionStatus.DEFERRED: "보류",
    DecisionStatus.RESOLVED: "해결",
}
NEG_LABELS = {
    NegotiationStatus.PROPOSED: "제안",
    NegotiationStatus.AGREED: "합의",
    NegotiationStatus.REJECTED: "결렬",
    NegotiationStatus.APPLIED: "기준선 반영",
}

services = get_services()
project = current_project()
if project is None:
    st.info("프로젝트를 먼저 선택하십시오.", icon=":material/info:")
    st.stop()
ui.project_header(project)
st.subheader("1. 회의록·인터뷰·질의응답 구조화")
st.caption(
    "회의록을 올리고 구조화하면 결정·고객 요청·내부 의견·미결 질문·조치 항목·위험이 모두 '제안' 상태로 기록됩니다. "
    "논의되었다는 사실만으로 승인하지 않으며, **결정 권한이 확인된 공식 결정만 승인**할 수 있습니다 (지시문 §10.2)."
)
up = st.file_uploader(
    "회의록 파일 (DOCX/PDF/TXT/MD/PPTX/이미지)",
    type=["docx", "pdf", "txt", "md", "pptx", "png", "jpg", "jpeg"],
    key="dec_upload",
)
if up is not None and st.button("회의록 등록", key="dec_register", icon=":material/upload:"):
    try:
        doc = services.documents.register_upload(
            project,
            kind=DocumentKind.MEETING_NOTE,
            file_name=up.name,
            data=up.getvalue(),
            actor=actor_name(),
        )
    except PWAError as exc:
        show_error(exc, context="회의록 등록")
    else:
        st.success(f"등록: {doc.file_name}", icon=":material/check:")
        st.rerun()
meeting_docs = [
    d for d in services.ctx.repos.documents.find(project.id) if d.kind == DocumentKind.MEETING_NOTE
]
if meeting_docs:
    pick = st.selectbox(
        "구조화할 회의록", meeting_docs, format_func=lambda d: d.file_name, key="dec_doc"
    )
    use_agent = st.checkbox(
        "에이전트 구조화 사용 (규칙 추출 + meeting_analyzer)", value=True, key="dec_agent"
    )
    if st.button("구조화 실행", key="dec_structure", icon=":material/account_tree:"):
        try:
            created, warnings = services.decisions.structure_meeting(
                project, pick, actor=actor_name(), use_agent=use_agent
            )
        except PWAError as exc:
            show_error(exc, context="회의록 구조화")
        else:
            st.success(f"{len(created)}건 기록 (전부 '제안' 상태)", icon=":material/check:")
            for w in warnings:
                st.caption(f"⚠ {w}")
            st.rerun()
else:
    st.caption("등록된 회의록이 없습니다.")

# --- 2. 결정·미결·조치 항목 ----------------------------------------------------------------------
st.divider()
st.subheader("2. 결정 · 미결 · 조치 항목 (사람 확정)")
decisions = services.decisions.decisions(project)
if not decisions:
    st.caption("기록된 항목이 없습니다.")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": d.code,
                    "종류": KIND_LABELS.get(d.kind, d.kind.value),
                    "제목": d.title,
                    "상태": STATUS_LABELS.get(d.status, d.status.value),
                    "권한 확인": "예" if d.authority_confirmed else "아니오",
                    "승인자": d.approved_by,
                    "담당": d.owner,
                    "기한": str(d.due_date or ""),
                    "관련 요구": ", ".join(d.related_requirement_ids),
                    "변경 요청": ", ".join(d.related_change_request_ids),
                    "원문": d.source_excerpt[:80],
                }
                for d in decisions
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    overdue = services.decisions.overdue_items(project)
    if overdue:
        st.warning(
            "기한이 지난 미결·조치 항목: " + ", ".join(f"{d.code}({d.due_date})" for d in overdue),
            icon=":material/schedule:",
        )
    target = st.selectbox(
        "확정할 항목",
        decisions,
        format_func=lambda d: (
            f"{d.code} · {KIND_LABELS.get(d.kind, d.kind.value)} · {d.title[:40]}"
        ),
        key="dec_target",
    )
    with st.form("dec_confirm_form"):
        st.caption(f"내용: {target.content[:300]}")
        c1, c2 = st.columns(2)
        kinds = list(DecisionKind)
        new_kind = c1.selectbox(
            "종류", kinds, index=kinds.index(target.kind), format_func=lambda k: KIND_LABELS[k]
        )
        statuses = list(DecisionStatus)
        new_status = c2.selectbox(
            "상태",
            statuses,
            index=statuses.index(target.status),
            format_func=lambda s: STATUS_LABELS[s],
        )
        authority = st.checkbox(
            "결정 권한이 확인되었습니다 (권한자·근거를 의견에 적으십시오) — 미확인이면 승인 불가",
            value=target.authority_confirmed,
        )
        approver = st.text_input("승인자", value=actor_name())
        comments = st.text_input("의견·근거")
        ok = st.form_submit_button("확정", icon=":material/gavel:")
    if ok:
        try:
            d = services.decisions.confirm_decision(
                project,
                target.id,
                status=new_status,
                approver=approver,
                authority_confirmed=authority,
                comments=comments,
                kind=new_kind,
                actor=actor_name(),
            )
        except PWAError as exc:
            show_error(exc, context="결정 확정")
        else:
            st.success(
                f"{d.code} → {STATUS_LABELS.get(d.status, d.status.value)}"
                + (" (공식 결정, 기준선 반영 가능)" if d.is_binding else ""),
                icon=":material/check:",
            )
            st.rerun()
    if project.mode == ProjectMode.BUILD and target.is_binding:
        if st.button(
            f"{target.code} 를 변경 요청으로 전환 (변경 관리 절차로 반영)",
            key="dec_to_cr",
            icon=":material/published_with_changes:",
        ):
            try:
                cr = services.decisions.decision_to_change_request(
                    project, target.id, changes=services.changes, actor=actor_name()
                )
            except PWAError as exc:
                show_error(exc, context="변경 요청 전환")
            else:
                st.success(f"{cr.id} 등록 — '구축: 변경 관리'에서 분석·승인하십시오.")
    elif target.is_binding:
        st.caption("변경 요청 전환은 구축 단계(BUILD) 프로젝트에서 가능합니다.")

# --- 3. 기술 협상·계약 변경 ------------------------------------------------------------------------
st.divider()
st.subheader("3. 기술 협상 · 계약 변경 (기준선 반영 통제)")
st.caption(
    "협상 항목은 **고객 합의가 확인되고 승인자가 있을 때만** '합의'로 확정되며, 합의된 항목만 변경 요청으로 전환됩니다. "
    "'기준선 반영' 상태는 변경 요청이 반영될 때 코드가 기록합니다."
)
with st.expander("협상 항목 등록", expanded=False):
    with st.form("neg_create_form"):
        n_title = st.text_input("제목")
        n_before = st.text_area("변경 전 (요구사항·제안 기준)", height=70)
        n_after = st.text_area("변경 후", height=70)
        n_reason = st.text_input("사유")
        i1, i2, i3 = st.columns(3)
        n_contract = i1.text_input("계약 영향")
        n_schedule = i2.text_input("일정 영향")
        n_cost = i3.text_input("비용·공수 영향")
        n_reqs = st.text_input("관련 요구사항 ID (쉼표 구분)")
        n_decs = st.multiselect(
            "관련 결정", decisions, format_func=lambda d: f"{d.code} {d.title[:30]}"
        )
        neg_created = st.form_submit_button("등록", icon=":material/add:")
    if neg_created:
        try:
            n = services.decisions.create_negotiation(
                project,
                title=n_title,
                before=n_before,
                after=n_after,
                reason=n_reason,
                contract_impact=n_contract,
                schedule_impact=n_schedule,
                cost_effort_impact=n_cost,
                related_requirement_ids=[x.strip() for x in n_reqs.split(",") if x.strip()],
                related_decision_ids=[d.id for d in n_decs],
                actor=actor_name(),
            )
        except PWAError as exc:
            show_error(exc, context="협상 등록")
        else:
            st.success(f"{n.code} 등록", icon=":material/check:")
            st.rerun()
negs = services.decisions.negotiations(project)
if negs:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": n.code,
                    "제목": n.title,
                    "상태": NEG_LABELS.get(n.status, n.status.value),
                    "고객 합의": {True: "예", False: "아니오", None: "미확인"}[n.customer_agreed],
                    "승인자": n.approved_by,
                    "계약": n.contract_impact,
                    "일정": n.schedule_impact,
                    "비용·공수": n.cost_effort_impact,
                    "관련 요구": ", ".join(n.related_requirement_ids),
                }
                for n in negs
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    tn = st.selectbox(
        "처리할 협상", negs, format_func=lambda n: f"{n.code} · {n.title[:40]}", key="neg_target"
    )
    with st.form("neg_settle_form"):
        s_opts = [NegotiationStatus.PROPOSED, NegotiationStatus.AGREED, NegotiationStatus.REJECTED]
        s_status = st.selectbox(
            "상태",
            s_opts,
            index=s_opts.index(tn.status) if tn.status in s_opts else 0,
            format_func=lambda s: NEG_LABELS[s],
        )
        agreed = st.selectbox(
            "고객 합의",
            [None, True, False],
            index=[None, True, False].index(tn.customer_agreed),
            format_func=lambda v: {None: "미확인", True: "합의됨", False: "거부"}[v],
        )
        s_approver = st.text_input("승인자", value=actor_name(), key="neg_approver")
        settled = st.form_submit_button("확정", icon=":material/handshake:")
    if settled:
        try:
            n = services.decisions.settle_negotiation(
                project,
                tn.id,
                status=s_status,
                customer_agreed=agreed,
                approver=s_approver,
                actor=actor_name(),
            )
        except PWAError as exc:
            show_error(exc, context="협상 확정")
        else:
            st.success(f"{n.code} → {NEG_LABELS.get(n.status, n.status.value)}")
            st.rerun()
    if project.mode == ProjectMode.BUILD and tn.can_apply_to_baseline:
        if st.button(
            f"{tn.code} 를 변경 요청으로 전환",
            key="neg_to_cr",
            icon=":material/published_with_changes:",
        ):
            try:
                cr = services.decisions.negotiation_to_change_request(
                    project, tn.id, changes=services.changes, actor=actor_name()
                )
            except PWAError as exc:
                show_error(exc, context="변경 요청 전환")
            else:
                st.success(f"{cr.id} 등록 — '구축: 변경 관리'에서 분석·승인하십시오.")
else:
    st.caption("협상 항목이 없습니다.")

st.divider()
st.download_button(
    "결정·협상 현황 (Markdown) 내려받기",
    data=services.decisions.render_markdown(project).encode("utf-8"),
    file_name=f"결정협상현황_{project.name}.md",
    mime="text/markdown",
    icon=":material/download:",
)
