"""문서 추출 화면: 업로드 문서·형식·페이지 수·추출 결과·OCR 페이지·경고·재처리, Gate 0 상태."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.config.errors import PWAError
from proposal_agent.ingest.service import GATE0_KEY
from proposal_agent.models import ExtractionMethod, GateStatus
from proposal_agent.orchestrator import StepRunner
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

services = get_services()
project = current_project()
if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.stop()

ui.project_header(project)
st.subheader("문서 추출")
runner = StepRunner(services)

c1, c2 = st.columns([1, 1])
if c1.button(
    "전체 문서 추출 실행", key="extract_all", type="primary", icon=":material/document_scanner:"
):
    with st.status("문서를 추출하는 중…", expanded=True) as status:
        try:
            outcome = runner.run_extraction(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="추출 실패", state="error")
            show_error(exc, context="문서 추출")
        else:
            status.update(label=outcome.summary, state="complete")
            st.rerun()
if c2.button("미추출·실패 문서만 재처리", key="extract_missing", icon=":material/refresh:"):
    try:
        outcome = runner.run_extraction(project, actor=actor_name(), only_missing=True)
    except PWAError as exc:
        show_error(exc, context="문서 재처리")
    else:
        st.success(outcome.summary, icon=":material/check:")
        st.rerun()

ocr = services.extraction.ocr
st.caption(
    f"OCR 엔진: {ocr.name} ({'사용 가능' if ocr.available() else '사용 불가 — 스캔 페이지는 검토 필요로 표시됨'})"
)

docs = services.documents.list_documents(project.id)
runs = services.extraction.latest_runs(project)
if not docs:
    st.info("등록된 문서가 없습니다. 프로젝트 화면의 입력 문서 탭에서 업로드하십시오.")
else:
    rows = []
    for d in docs:
        run = runs.get(d.id)
        rows.append(
            {
                "파일": d.file_name,
                "종류": d.kind.label,
                "형식": (run.file_format.value if run else d.file_name.rsplit(".", 1)[-1]).upper(),
                "단위": f"{run.page_count or '-'} {run.unit_label}" if run else "-",
                "추출": run.status.value if run else "미실행",
                "OCR 페이지": run.ocr_pages if run else 0,
                "블록": run.block_count if run else 0,
                "검토 필요 블록": run.low_confidence_blocks if run else 0,
                "경고": len(run.warnings) if run else 0,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, alt="문서별 추출 결과")

    for d in docs:
        run = runs.get(d.id)
        if run is None:
            continue
        with st.expander(
            f"{d.file_name} — {run.status.value}",
            expanded=run.status.value in ("failed", "unsupported", "partial"),
        ):
            if run.error:
                st.error(
                    f"{run.error.get('message')}\n\n원인: {run.error.get('cause')}\n\n조치: {run.error.get('resolution')}",
                    icon=":material/error:",
                )
            for w in run.warnings:
                st.warning(w, icon=":material/warning:")
            if run.page_stats and run.unit_label == "page":
                ps = [
                    {
                        "페이지": p.page,
                        "방식": "OCR" if p.method == ExtractionMethod.OCR else "텍스트",
                        "글자 수": p.char_count,
                        "신뢰도": p.confidence,
                        "경고": p.warning or "",
                    }
                    for p in run.page_stats
                ]
                st.dataframe(
                    pd.DataFrame(ps), hide_index=True, alt=f"{d.file_name} 페이지별 추출 통계"
                )
            if run.ok and st.toggle("추출 블록 보기", key=f"blocks_{run.id}"):
                blocks = services.ctx.repos.blocks.for_run(project.id, run.id)
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "순서": b.order,
                                "종류": b.block_type.value,
                                "위치": b.location.label(),
                                "방식": b.extraction_method.value,
                                "신뢰도": b.confidence,
                                "검토": "예" if b.needs_review else "",
                                "내용": b.text[:200],
                            }
                            for b in blocks
                        ]
                    ),
                    hide_index=True,
                    alt=f"{d.file_name} 추출 블록",
                )

st.divider()
gate = services.gates.state(project, GATE0_KEY)
ui.gate_panel(gate)
if (
    gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    and gate.evaluation
    and not gate.evaluation.approval_id
):
    comments = st.text_area("검토 의견 (필수)", key="gate0_comments")
    a, b = st.columns(2)
    if a.button("검토 후 통과", key="gate0_approve", type="primary", icon=":material/check:"):
        try:
            services.gates.approve_human_review(
                project, GATE0_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 0 승인")
        else:
            st.rerun()
    if b.button("반려 (재처리 필요)", key="gate0_reject", icon=":material/block:"):
        try:
            services.gates.reject_human_review(
                project, GATE0_KEY, approver=actor_name(), comments=comments
            )
        except PWAError as exc:
            show_error(exc, context="Gate 0 반려")
        else:
            st.rerun()
