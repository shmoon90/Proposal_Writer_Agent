"""재사용 UI 조각. 서비스 결과(값 객체)만 받아 그린다. 비즈니스 로직 없음."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.models import GateStatus, Project, StepStatus
from proposal_agent.orchestrator.gates import GateState
from proposal_agent.services.document_service import InputStatus
from proposal_agent.services.jobs import Job
from proposal_agent.services.pipeline_service import Issue, PlanRow, StepView
from proposal_agent.services.project_service import ProjectLocations

_STATUS_ICON = {
    StepStatus.PENDING: ":material/radio_button_unchecked:",
    StepStatus.RUNNING: ":material/autorenew:",
    StepStatus.NEEDS_REVIEW: ":material/rate_review:",
    StepStatus.APPROVED: ":material/check_circle:",
    StepStatus.FAILED: ":material/error:",
    StepStatus.SKIPPED: ":material/skip_next:",
}


def project_header(project: Project) -> None:
    st.subheader(f"{project.name}")
    cols = st.columns(4)
    cols[0].metric("모드", project.mode.label)
    cols[1].metric("상태", str(project.status))
    cols[2].metric("시작일", project.start_date.isoformat() if project.start_date else "-")
    cols[3].metric("종료일", project.end_date.isoformat() if project.end_date else "-")


def step_table(views: list[StepView], progress: tuple[int, int]) -> None:
    done, total = progress
    st.progress(done / total if total else 0.0, text=f"단계 진행 {done}/{total}")
    rows = []
    for v in views:
        rows.append(
            {
                "순서": v.definition.order,
                "단계": v.definition.title,
                "상태": f"{_STATUS_ICON[v.status]} {v.status.label}",
                "게이트": v.definition.gate_title or "",
                "시도": v.run.attempt if v.run else 0,
                "요약": (v.run.summary if v.run else "") or "",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, alt="단계별 진행 상태 표")


def plan_table(rows: list[PlanRow]) -> None:
    """실행 계획 미리보기 (지시문 §16-3): 단계·상태·실행 가능 여부·차단 사유·진행률."""
    data = []
    for r in rows:
        data.append(
            {
                "순서": r.order,
                "단계": r.title,
                "상태": f"{_STATUS_ICON[r.status]} {r.status.label}",
                "실행": "가능" if r.runnable else ("선택 안 함" if not r.selected else "차단"),
                "차단 사유": "; ".join(r.blockers),
                "에이전트": r.agent_role or "코드",
                "게이트": r.gate or "",
                "시도": r.attempts,
                "진행률": f"{r.progress:.0%}" if 0 < r.progress < 1 else "",
                "현재 일": r.progress_note,
            }
        )
    st.dataframe(pd.DataFrame(data), hide_index=True, alt="실행 계획 미리보기 표")


def jobs_panel(jobs: list[Job]) -> None:
    """실행 중인 백그라운드 작업."""
    if not jobs:
        st.caption("실행 중인 백그라운드 작업 없음")
        return
    for j in jobs:
        st.markdown(
            f"- **{j.step_key}** (`{j.run_id}`) 시작 {j.started_at:%H:%M:%S} — "
            + ("중단 요청됨" if j.cancel.is_cancelled else "실행 중")
        )


def issues_panel(issues: list[Issue]) -> None:
    if not issues:
        st.success("미해결 이슈가 없습니다.", icon=":material/check:")
        return
    for issue in issues:
        body = f"**{issue.source}** — {issue.message}"
        if issue.resolution:
            body += f"\n\n조치: {issue.resolution}"
        if issue.level == "error":
            st.error(body, icon=":material/error:")
        else:
            st.warning(body, icon=":material/warning:")


def input_status_panel(statuses: list[InputStatus]) -> None:
    rows = []
    for s in statuses:
        rows.append(
            {
                "문서 종류": s.kind.label,
                "필수": "필수" if s.required else "선택",
                "등록 수": len(s.documents),
                "충족": "예" if s.satisfied else "아니오",
                "파일": ", ".join(d.file_name for d in s.documents) or "-",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, alt="입력 문서 등록 현황")


def locations_panel(loc: ProjectLocations) -> None:
    st.code(
        f"산출물 폴더: {loc.output_dir}\n작업 폴더:   {loc.workspace_dir}\nDB:          {loc.db_path}\n로그:        {loc.log_file}",
        language="text",
    )
    if loc.missing_subdirs:
        st.warning(
            f"누락된 하위 폴더: {', '.join(loc.missing_subdirs)}", icon=":material/folder_off:"
        )
    with st.expander("하위 폴더 14종"):
        st.write(list(loc.subdirs))


def approvals_panel(history: list) -> None:
    if not history:
        st.info("아직 승인 이력이 없습니다.")
        return
    rows = [
        {
            "단계": gate.step_key,
            "결정": str(gate.decision),
            "승인자": approval.approver,
            "일시": approval.decided_at.isoformat(),
            "의견": approval.comments,
        }
        for gate, approval in history
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, alt="단계별 승인 이력")


def gate_panel(gate: GateState) -> None:
    """Gate 상태(PASS/FAIL/NEEDS_HUMAN_REVIEW)와 코드가 기록한 사유를 표시한다."""
    reasons = gate.evaluation.reasons if gate.evaluation else ["아직 평가되지 않았습니다."]
    lines = [f"**{gate.title}** — {gate.status.value}", ""]
    lines.extend(f"- {r}" for r in reasons)
    if gate.approved_by:
        lines.extend(["", f"사람 검토 승인: {gate.approved_by}"])
    body = chr(10).join(lines)
    if gate.status == GateStatus.PASS:
        st.success(body, icon=":material/verified:")
    elif gate.status == GateStatus.NEEDS_HUMAN_REVIEW:
        st.warning(body, icon=":material/rate_review:")
    else:
        st.error(body, icon=":material/block:")
