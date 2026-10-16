"""요구사항 화면: 추출·검증 실행, 목록·원본 위치·검토 결과, 사용자 수정·승인, Gate 1."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.ingest.service import GATE0_KEY
from proposal_agent.models import (
    Difficulty,
    GateStatus,
    Priority,
    RequirementCategory,
    RequirementDraft,
    RequirementType,
    ReviewStatus,
    ScopeClass,
    ValidationLevel,
)
from proposal_agent.orchestrator import StepRunner
from proposal_agent.requirements.service import GATE1_KEY
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
st.subheader("요구사항 추출·검증")
api_key_banner()
runner = StepRunner(services)
gate0 = services.gates.state(project, GATE0_KEY)
gate1 = services.gates.state(project, GATE1_KEY)

a, b, c = st.columns(3)
extract_plan = verify_plan = None
if gate0.passed:
    try:
        extract_plan = services.requirements.plan_extraction(project)
        verify_plan = services.requirements.plan_verification(project)
    except PWAError as exc:
        st.caption(f"실행 계획 산정 실패: {exc}")
    else:
        st.caption(f"추출 계획 — {extract_plan.summary()}")
        st.caption(f"검증 계획 — {verify_plan.summary()}")
        if extract_plan.over_call_limit or extract_plan.over_budget:
            st.error(
                "추출이 호출 수 또는 누적 비용 상한을 넘습니다. 설정(PWA_MAX_AGENT_CALLS_PER_STEP, PWA_MAX_BUDGET_USD_PER_PROJECT)을 조정하거나 문서를 나누십시오.",
                icon=":material/block:",
            )
extract_blocked = bool(extract_plan and (extract_plan.over_call_limit or extract_plan.over_budget))
verify_blocked = bool(verify_plan and (verify_plan.over_call_limit or verify_plan.over_budget))
if a.button(
    "요구사항 추출 (에이전트)",
    key="req_extract",
    type="primary",
    icon=":material/auto_awesome:",
    disabled=not gate0.passed or extract_blocked,
    help=None if gate0.passed else "Gate 0을 먼저 통과해야 합니다.",
):
    with st.status("요구사항을 추출하는 중… (청크별 에이전트 호출)", expanded=True) as status:
        try:
            outcome, result = runner.run_requirement_extraction(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="추출 실패", state="error")
            show_error(exc, context="요구사항 추출")
        else:
            status.update(label=outcome.summary, state="complete")
            if result.unresolved:
                st.write("미해결 항목:", result.unresolved)
            st.rerun()
if b.button(
    "독립 검증 (에이전트)",
    key="req_verify",
    icon=":material/fact_check:",
    disabled=not gate0.passed or verify_blocked,
):
    with st.status("독립 검증 중…", expanded=True) as status:
        try:
            outcome, vresult = runner.run_verification(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="검증 실패", state="error")
            show_error(exc, context="독립 검증")
        else:
            status.update(label=outcome.summary, state="complete")
            for line in vresult.summaries:
                st.write(line)
            st.rerun()
if c.button("Gate 1 재평가 (코드)", key="gate1_reeval", icon=":material/rule:"):
    gate1 = runner.reevaluate_gate1(project)
    st.rerun()

reqs = services.requirements.list_requirements(project, include_deleted=True)
findings = services.requirements.open_findings(project)
if not reqs:
    st.info("추출된 요구사항이 없습니다.")
else:
    type_filter = st.pills(
        "종류",
        options=[t.label for t in RequirementType],
        selection_mode="multi",
        key="req_type_filter",
    )
    show_deleted = st.toggle("삭제 항목 표시", key="req_show_deleted")
    rows = []
    for r in reqs:
        if type_filter and r.type.label not in type_filter:
            continue
        if not show_deleted and r.status.value == "deleted":
            continue
        n_find = sum(
            1
            for f in findings
            if f.target_id == r.id or r.id in f.detail.get("requirement_ids", [])
        )
        rows.append(
            {
                "ID": r.id,
                "종류": r.type.label,
                "요구사항명": r.name,
                "범위": r.scope_class.label,
                "필수": "예" if r.is_mandatory else "아니오",
                "중요도": r.priority.value,
                "검증": r.verification_status.value,
                "검토": r.review_status.value,
                "상태": r.status.value,
                "신뢰도": r.confidence,
                "지적": n_find,
                "원본 위치": "; ".join(ref.location_label or "" for ref in r.source_refs)
                or "(출처 없음)",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, alt="요구사항 목록")

    st.markdown("#### 요구사항 상세·수정")
    ids = [str(row["ID"]) for row in rows]
    if ids:
        sel = st.selectbox("요구사항 선택", options=ids, key="req_selected")
        req = services.requirements.get(project, sel)
        with st.container(border=True):
            st.markdown(f"**{req.id} · {req.name}**")
            st.caption(
                f"검증: {req.verification_status.value} · 검토: {req.review_status.value} · 상태: {req.status.value} · 버전 {req.version}"
            )
            if req.rfp_quote:
                st.markdown(f"> {req.rfp_quote}")
            for ref in req.source_refs:
                st.caption(f"출처: {ref.location_label}")
            if req.rationale:
                st.write("근거:", req.rationale)
            mine = [
                f
                for f in findings
                if f.target_id == req.id or req.id in f.detail.get("requirement_ids", [])
            ]
            for f in mine:
                (
                    st.error
                    if f.level == ValidationLevel.ERROR
                    else st.warning
                    if f.level == ValidationLevel.WARNING
                    else st.info
                )(
                    f"[{f.rule_id}] {f.message}"
                    + (
                        f"\n\n제안: {f.detail.get('suggested_fix')}"
                        if f.detail.get("suggested_fix")
                        else ""
                    ),
                    icon=":material/rate_review:",
                )
                if st.button("해결 처리", key=f"resolve_{f.id}"):
                    services.requirements.resolve_finding(project, f.id, actor=actor_name())
                    st.rerun()
            with st.form(f"edit_{req.id}"):
                name = st.text_input("요구사항명", value=req.name)
                description = st.text_area("상세 내용", value=req.description)
                rtype = st.selectbox(
                    "종류",
                    options=list(RequirementType),
                    index=list(RequirementType).index(req.type),
                    format_func=lambda t: t.label,
                )
                scope = st.selectbox(
                    "범위 분류",
                    options=list(ScopeClass),
                    index=list(ScopeClass).index(req.scope_class),
                    format_func=lambda s: s.label,
                )
                mandatory = st.checkbox("필수 여부", value=req.is_mandatory)
                priority = st.selectbox(
                    "중요도", options=list(Priority), index=list(Priority).index(req.priority)
                )
                approach = st.text_area(
                    "구현 방안",
                    value=req.implementation_approach or "",
                    help=f"작성 주체: {req.approach_source or '없음'} · 근거: {', '.join(req.approach_basis[:3]) or '없음'}. 직접 고치면 '사람 작성(user)'으로 바뀌어 에이전트가 덮어쓰지 않습니다.",
                )
                diff_options = [None, *list(Difficulty)]
                difficulty = st.selectbox(
                    "구현 난이도",
                    options=diff_options,
                    index=diff_options.index(req.difficulty),
                    format_func=lambda d: "(미정)" if d is None else d.label,
                    help=req.difficulty_basis or "변경 요청 영향(공수·일정) 산정의 가중치",
                )
                criteria = st.text_area("검사 기준(판정 기준)", value=req.acceptance_criteria)
                vmethod = st.text_input("검증 방법", value=req.verification_method or "")
                impact = st.text_area(
                    "비용·일정·운영 영향 (부가 제안 시)", value=req.impact_note or ""
                )
                notes = st.text_area("비고", value=req.notes)
                note = st.text_input("변경 사유")
                saved = st.form_submit_button("수정 저장", icon=":material/save:")
            if saved:
                try:
                    services.requirements.update_requirement(
                        project,
                        req.id,
                        {
                            "name": name,
                            "description": description,
                            "type": rtype,
                            "scope_class": scope,
                            "is_mandatory": mandatory,
                            "priority": priority,
                            "implementation_approach": approach or None,
                            **(
                                {"approach_source": "user"}
                                if (approach or "") != (req.implementation_approach or "")
                                else {}
                            ),
                            "difficulty": difficulty,
                            "acceptance_criteria": criteria,
                            "verification_method": vmethod or None,
                            "impact_note": impact or None,
                            "notes": notes,
                        },
                        actor=actor_name(),
                        note=note,
                    )
                except PWAError as exc:
                    show_error(exc, context="요구사항 수정")
                else:
                    st.success("저장했습니다.", icon=":material/check:")
                    st.rerun()
            r1, r2, r3 = st.columns(3)
            if r1.button("검토 승인", key=f"approve_{req.id}", icon=":material/check:"):
                services.requirements.set_review(
                    project, req.id, ReviewStatus.APPROVED, actor=actor_name()
                )
                st.rerun()
            if r2.button("검토 반려", key=f"reject_{req.id}", icon=":material/block:"):
                services.requirements.set_review(
                    project, req.id, ReviewStatus.REJECTED, actor=actor_name()
                )
                st.rerun()
            reason = r3.text_input("삭제 사유", key=f"del_reason_{req.id}")
            if r3.button("삭제 (상태 변경)", key=f"delete_{req.id}", icon=":material/delete:"):
                try:
                    services.requirements.mark_deleted(
                        project, req.id, actor=actor_name(), reason=reason
                    )
                except PWAError as exc:
                    show_error(exc, context="요구사항 삭제")
                else:
                    st.rerun()
            if req.analysis:
                with st.expander("기술 검토 14항목 (구현 방안 에이전트, 단계 3)"):
                    from proposal_agent.agents.schemas import ANALYSIS_FIELDS

                    for _k, _label in ANALYSIS_FIELDS:
                        _vals = req.analysis.get(_k) or []
                        if _vals:
                            st.markdown(f"**{_label}**: " + " / ".join(str(v) for v in _vals))
            with st.expander("변경 이력"):
                for h in req.history:
                    st.write(f"{h.at} · {h.actor} · {h.action} · {h.note} {h.changes or ''}")

with st.expander(
    "품질 검토 (코드 규칙: 중복·충돌·검증 불가·구현 방안·근거·업무 규칙·비기능·수용 기준)"
):
    from proposal_agent.requirements.quality import check_requirement_quality

    _findings = check_requirement_quality(services.requirements.list_requirements(project))
    if not _findings:
        st.write("발견된 품질 문제가 없습니다.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "규칙": f.title,
                        "수준": f.level,
                        "요구사항": ", ".join(f.requirement_ids),
                        "내용": f.message,
                        "조치": f.suggestion,
                    }
                    for f in _findings
                ]
            ),
            hide_index=True,
            alt="요구사항 품질 검토 표",
        )

with st.expander("요구사항 직접 추가 (부가 제안 등)"):
    with st.form("add_req"):
        n = st.text_input("요구사항명", key="add_name")
        d = st.text_area("상세 내용", key="add_desc")
        t = st.selectbox(
            "종류", options=list(RequirementType), format_func=lambda x: x.label, key="add_type"
        )
        s = st.selectbox(
            "범위 분류",
            options=list(ScopeClass),
            index=2,
            format_func=lambda x: x.label,
            key="add_scope",
        )
        cat = st.selectbox("분류", options=list(RequirementCategory), key="add_cat")
        imp = st.text_area("비용·일정·운영 영향 (부가 제안이면 필수)", key="add_impact")
        ok = st.form_submit_button("추가", icon=":material/add:")
    if ok:
        try:
            draft = RequirementDraft(
                name=n,
                description=d,
                type=t,
                category=cat,
                scope_class=s,
                is_mandatory=(s == ScopeClass.MANDATORY),
                impact_note=imp or None,
                rfp_quote="",
                confidence=1.0,
            )
            services.requirements.add_manual(project, draft, actor=actor_name())
        except (PWAError, ValueError) as exc:
            show_error(
                exc if isinstance(exc, PWAError) else PWAError(str(exc)), context="요구사항 추가"
            )
        else:
            st.rerun()

st.divider()
ui.gate_panel(gate1)
if (
    gate1.status == GateStatus.NEEDS_HUMAN_REVIEW
    and gate1.evaluation
    and not gate1.evaluation.approval_id
):
    comments = st.text_area("검토 의견 (필수)", key="gate1_comments")
    x, y = st.columns(2)
    if x.button(
        "검토 후 Gate 1 통과", key="gate1_approve", type="primary", icon=":material/check:"
    ):
        try:
            services.gates.approve_human_review(
                project, GATE1_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 1 승인")
        else:
            st.rerun()
    if y.button("반려", key="gate1_reject", icon=":material/block:"):
        try:
            services.gates.reject_human_review(
                project, GATE1_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 1 반려")
        else:
            st.rerun()
