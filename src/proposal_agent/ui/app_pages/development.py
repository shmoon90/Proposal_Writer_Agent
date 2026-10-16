"""개발·테스트 화면 (단계 7, 지시문 §13~§16, D-22): WBS 모듈 분해 → 테스트 계획 → 코드 생성(프로토타입) → Docker JUnit →
QA 수정 루프 → 검수 기록 → 테스트 계획서·결과서·검수 결과서·운영 이관 체크리스트."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.models import TestLevel
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
dev, testing = services.development, services.testing


def _run(label: str, fn: Any, context: str) -> None:
    with st.status(label, expanded=True) as status:
        try:
            outcome = fn()
        except PWAError as exc:
            status.update(label="실패", state="error")
            show_error(exc, context=context)
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()


st.subheader("1. WBS 설계 분해 · 테스트 계획")
a1, a2 = st.columns(2)
if a1.button("WBS 를 설계 모듈까지 분해", key="dv_decompose", icon=":material/account_tree:"):
    _run("WBS 분해 중…", lambda: runner.run_wbs_decompose(project, actor=actor_name()), "WBS 분해")
if a2.button("테스트 케이스 계획 (API·화면·인수 기준)", key="dv_plan", icon=":material/checklist:"):
    _run(
        "테스트 계획 중…", lambda: runner.run_test_plan(project, actor=actor_name()), "테스트 계획"
    )

st.divider()
st.subheader("2. 코드 생성 · 격리 테스트 (Spring Boot 프로토타입, 납품 코드 아님)")
status = dev.docker_status()
(st.success if status.ready else st.warning)(f"Docker: {status.message}", icon=":material/dns:")
if (
    not status.image_present
    and status.daemon_running
    and st.button("테스트 이미지 빌드 (JDK 21 + Maven, 수 분·네트워크 필요)", key="dv_build")
):
    with st.status("이미지 빌드 중…", expanded=True) as s_:
        ok, log_ = dev.build_image()
        s_.update(label="빌드 성공" if ok else "빌드 실패", state="complete" if ok else "error")
        st.code(log_[-2000:])
batches, warnings = dev.plan(project)
st.caption(
    f"배치 계획: {len(batches)}개 — "
    + "; ".join(f"{b.label}({len(b.target_paths)}파일)" for b in batches)[:300]
    if batches
    else "배치 없음 — 상세 설계(모듈 분해)가 필요합니다."
)
for w in warnings[:5]:
    st.caption(f"⚠ {w}")
b1, b2, b3, b4 = st.columns(4)
if b1.button("템플릿 준비", key="dv_prepare", icon=":material/folder:"):
    try:
        paths = dev.prepare(project, actor=actor_name())
    except PWAError as exc:
        show_error(exc, context="템플릿 준비")
    else:
        st.success("준비: " + ", ".join(paths))
if b2.button(
    "코드 생성 (에이전트, 크레딧 필요)",
    key="dv_generate",
    icon=":material/code:",
    disabled=not batches,
):
    _run(
        "코드 생성 중…",
        lambda: runner.run_code_generation(project, actor=actor_name()),
        "코드 생성",
    )
if b3.button(
    "Docker 테스트 실행", key="dv_test", icon=":material/science:", disabled=not status.ready
):
    _run(
        "테스트 실행 중…", lambda: runner.run_code_test(project, actor=actor_name()), "테스트 실행"
    )
if b4.button(
    "QA 분석·수정 루프 (에이전트)", key="dv_fix", icon=":material/build:", disabled=not status.ready
):
    _run(
        "수정 루프 실행 중…", lambda: runner.run_code_fix(project, actor=actor_name()), "수정 루프"
    )
st.caption(dev.summary(project))
mods = dev.modules(project)
if mods:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": m.code,
                    "경로": m.path,
                    "계층": m.layer,
                    "상태": m.status,
                    "구현 위치": "; ".join(
                        f"{x.get('requirement_id')}→{','.join(x.get('symbols', []))}"
                        for x in m.implementation_map
                    )[:120],
                    "검사 메모": "; ".join(m.review_checklist)[:120],
                }
                for m in mods
            ]
        ),
        width="stretch",
        hide_index=True,
    )
results = dev.test_results(project)
if results:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "실행": r.label,
                    "결과": r.outcome.value,
                    "통과": r.passed,
                    "실패": r.failed,
                    "오류": r.errors,
                    "건너뜀": r.skipped,
                    "미실행 필수": len(r.missing_required),
                    "초": r.duration_seconds,
                }
                for r in results
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    last = results[-1]
    if last.failing_cases:
        with st.expander(f"{last.label} 실패 상세"):
            for c in last.failing_cases[:20]:
                st.code(f"{c.node_id} ({c.outcome})\n{c.message[:600]}")
    with st.expander(f"{last.label} Maven 로그 끝부분"):
        st.code(last.stdout[-3000:] or "(없음)")

st.divider()
st.subheader("3. 테스트 케이스 · 결함 · 검수")
tcs, defects = testing.test_cases(project), testing.defects(project)
if tcs:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": t.code,
                    "이름": t.name[:60],
                    "수준": t.level.value,
                    "상태": t.status.value,
                    "요구사항": ", ".join(t.related_requirement_ids),
                    "실행": t.executed_by,
                    "결과": t.actual_result[:60],
                }
                for t in tcs
            ]
        ),
        width="stretch",
        hide_index=True,
    )
else:
    st.caption(
        "테스트 케이스가 없습니다 — '테스트 케이스 계획' 또는 Docker 테스트 실행 후 생깁니다."
    )
if defects:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": d.code,
                    "제목": d.title[:60],
                    "심각도": d.severity,
                    "상태": d.status.value,
                    "원인": d.cause[:60],
                    "수정": d.fix_note[:60],
                    "재테스트": d.retest_result[:40],
                }
                for d in defects
            ]
        ),
        width="stretch",
        hide_index=True,
    )
acc = [t for t in tcs if t.level == TestLevel.ACCEPTANCE]
if acc:
    with st.form("dv_acceptance"):
        tc = st.selectbox(
            "검수할 인수 테스트",
            acc,
            format_func=lambda t: f"{t.code} {t.name[:50]} ({t.status.value})",
        )
        passed = st.radio("판정", ["합격", "불합격"], horizontal=True) == "합격"
        note = st.text_input("비고·사유 (불합격은 필수)")
        inspector = st.text_input("검수자", value=actor_name())
        ok = st.form_submit_button("검수 기록", icon=":material/verified:")
    if ok:
        try:
            t = testing.record_acceptance(
                project, tc.id, passed=passed, note=note, inspector=inspector, actor=actor_name()
            )
        except PWAError as exc:
            show_error(exc, context="검수 기록")
        else:
            st.success(f"{t.code} → {t.status.value}")
            st.rerun()

st.divider()
st.subheader("4. 문서 생성")
if st.button(
    "테스트 계획서 · 결과서 · 검수 결과서 · 운영 이관 체크리스트 (Markdown)",
    key="dv_docs",
    icon=":material/description:",
):
    try:
        paths = testing.write_documents(
            project, results, decisions=services.decisions.open_items(project), actor=actor_name()
        )
    except PWAError as exc:
        show_error(exc, context="문서 생성")
    else:
        st.success("생성: " + ", ".join(paths))
