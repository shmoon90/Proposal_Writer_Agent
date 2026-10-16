"""구축 단계 화면 1: 기존 산출물 업로드 → 구조 분석·컬럼 매핑 확인 → 기준 데이터 적재."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from proposal_agent.changes.baseline_service import BASELINE_REQUIRED
from proposal_agent.config.errors import PWAError
from proposal_agent.models import DocumentKind, ProjectMode
from proposal_agent.services.document_service import ALLOWED_SUFFIXES
from proposal_agent.ui import components as ui
from proposal_agent.ui.state import actor_name, current_project, get_services, show_error

KIND_LABELS = {
    DocumentKind.REQUIREMENT_SPEC: "요구사항 정의서 (필수)",
    DocumentKind.TRACE_MATRIX: "요구사항 추적표 (필수)",
    DocumentKind.WBS: "WBS (필수)",
    DocumentKind.STAFFING_PLAN: "인력 투입계획 (선택)",
    DocumentKind.OTHER: "기타 — 제안서·변경요청서 등 (선택)",
}

services = get_services()
project = current_project()
if project is None:
    st.warning(
        "선택된 프로젝트가 없습니다. 시작 화면에서 프로젝트를 생성하거나 여십시오.",
        icon=":material/info:",
    )
    st.stop()
if project.mode != ProjectMode.BUILD:
    st.info(
        "이 화면은 구축 단계(BUILD) 프로젝트에서 사용합니다. 현재 프로젝트는 제안 단계입니다.",
        icon=":material/info:",
    )
    st.stop()

ui.project_header(project)
st.subheader("1. 기존 산출물 업로드")
st.caption("업로드 원본은 01_RFP_Original에 그대로 보존되며, 적재·갱신은 새 파일로만 이루어집니다.")
ui.input_status_panel(services.documents.input_status(project))

cols = st.columns(2)
for i, kind in enumerate(KIND_LABELS):
    with cols[i % 2]:
        up = st.file_uploader(
            KIND_LABELS[kind],
            type=[s.lstrip(".") for s in ALLOWED_SUFFIXES[kind]],
            key=f"bb_up_{kind.value}",
        )
        if up is not None and st.button(
            f"등록: {up.name}", key=f"bb_reg_{kind.value}", icon=":material/upload:"
        ):
            try:
                services.documents.register_upload(
                    project, kind=kind, file_name=up.name, data=up.getvalue(), actor=actor_name()
                )
            except PWAError as exc:
                show_error(exc, context="문서 등록")
            else:
                st.success(f"{up.name} 등록 완료", icon=":material/check:")
                st.rerun()

st.divider()
st.subheader("2. 문서 구조 분석 · 컬럼 매핑 확인")
docs = services.baseline.baseline_documents(project)
missing = [k for k in BASELINE_REQUIRED if k not in docs]
if missing:
    st.warning(
        "필수 문서가 없습니다: " + ", ".join(KIND_LABELS[k] for k in missing),
        icon=":material/warning:",
    )

if docs and st.button("구조 분석 실행 (매핑 제안)", key="bb_profile", icon=":material/table_view:"):
    st.session_state["bb_profiles_ready"] = True

if st.session_state.get("bb_profiles_ready") and docs:
    try:
        profiles = services.baseline.profiles(project)
    except PWAError as exc:
        show_error(exc, context="문서 구조 분석")
        profiles = {}
    for kind, prof in profiles.items():
        with st.expander(
            f"{KIND_LABELS.get(kind, kind.value)} — {prof.document.file_name}"
            + (" · 확인 필요" if prof.blocking and not prof.confirmed else " · 자동 매핑"),
            expanded=bool(prof.blocking and not prof.confirmed),
        ):
            for note in prof.profile.quality:
                st.caption(f"· {note}")
            overrides: dict[str, dict[str, int]] = {}
            for sheet in prof.profile.sheets:
                st.markdown(f"**시트 `{sheet.sheet}`** (헤더 {sheet.header_row}행)")
                headers = [
                    str(v) if v is not None else ""
                    for v in (sheet.sample_rows[0] if sheet.sample_rows else [])
                ]
                rows = []
                for c in sheet.columns:
                    rows.append(
                        {
                            "필드": c.field,
                            "제안 헤더": c.header or "—",
                            "열": (c.column_index + 1) if c.column_index is not None else None,
                            "신뢰도": c.confidence,
                            "확인 필요": "예" if c.needs_confirmation else "",
                            "근거": c.reason,
                            "출처": "사용자"
                            if c.field in prof.overrides.get(sheet.sheet, {})
                            else "규칙",
                        }
                    )
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                for w in sheet.warnings:
                    st.caption(f"⚠ {w}")
                need = [c for c in sheet.columns if c.needs_confirmation]
                if need and not prof.confirmed:
                    st.markdown("확인이 필요한 컬럼을 지정하십시오 (열 번호, 1부터; 0 = 없음):")
                    for c in need:
                        val = st.number_input(
                            f"{sheet.sheet} · {c.field}",
                            min_value=0,
                            max_value=200,
                            value=(c.column_index + 1) if c.column_index is not None else 0,
                            key=f"bb_map_{prof.document.id}_{sheet.sheet}_{c.field}",
                        )
                        if val > 0:
                            overrides.setdefault(sheet.sheet, {})[c.field] = int(val) - 1
                if sheet.sample_rows:
                    st.caption("샘플 행:")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                [str(v) if v is not None else "" for v in r]
                                for r in sheet.sample_rows[:3]
                            ]
                        ),
                        width="stretch",
                        hide_index=True,
                    )
            if prof.confirmed:
                st.success("사용자가 매핑을 확정했습니다.", icon=":material/check:")
            elif st.button(
                "이 문서의 매핑 확정", key=f"bb_confirm_{prof.document.id}", icon=":material/done:"
            ):
                try:
                    services.baseline.confirm_mapping(
                        project, prof.document, overrides, actor=actor_name()
                    )
                except PWAError as exc:
                    show_error(exc, context="매핑 확정")
                else:
                    st.rerun()

st.divider()
st.subheader("3. 기준 데이터 적재")
st.caption(
    "요구사항 ID는 그대로 유지됩니다. 적재 결과는 Revision v1.0(기준선)으로 기록되고 스냅샷이 12_Revision_History에 저장됩니다."
)
if st.button(
    "기준 데이터 적재",
    key="bb_load",
    type="primary",
    icon=":material/database:",
    disabled=bool(missing),
):
    with st.status("기준 데이터를 적재하는 중…", expanded=True) as status:
        try:
            result = services.baseline.load(project, actor=actor_name())
        except PWAError as exc:
            status.update(label="적재 실패", state="error")
            show_error(exc, context="기준 데이터 적재")
        else:
            status.update(label=f"적재 완료 — Revision {result.revision.number}", state="complete")
            st.write(
                {
                    "요구사항": result.requirements,
                    "추적 링크": result.traces,
                    "화면": result.screens,
                    "단위테스트": result.unit_tests,
                    "통합테스트": result.integration_tests,
                    "WBS": result.wbs_items,
                    "의존관계": result.dependencies,
                    "역할": result.roles,
                    "투입계획": "있음" if result.staffing_plan_present else "없음",
                    "ID 체계": result.id_scheme,
                }
            )
            for w in result.warnings:
                st.caption(f"⚠ {w}")

reqs = services.changes.active_requirements(project)
if reqs:
    st.markdown(
        f"**현재 기준 요구사항 {len(reqs)}건** · WBS {len(services.ctx.repos.wbs.tree(project.id))}건 · Revision {services.ctx.repos.revisions.get(project.baseline_revision_id).number if project.baseline_revision_id else '-'}"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": r.id,
                    "명": r.name,
                    "종류": r.type.value,
                    "변경 상태": r.change_state,
                    "추가 요청자": r.added_by or "",
                    "내용": r.description[:80],
                }
                for r in reqs
            ]
        ),
        width="stretch",
        hide_index=True,
    )

# --- 4. Revision 복원 (단계 8) -------------------------------------------------------------------------------
st.divider()
st.subheader("4. Revision 복원")
_revs = services.ctx.repos.revisions.find(project.id, order_by="created_at")
if _revs:
    _pick = st.selectbox(
        "되돌릴 Revision",
        list(reversed(_revs)),
        format_func=lambda r: f"{r.number} {r.label} ({r.created_at:%Y-%m-%d %H:%M})",
        key="bb_restore_pick",
    )
    _reason = st.text_input("복원 사유 (필수)", key="bb_restore_reason")
    if st.button(
        "이 Revision 으로 복원",
        key="bb_restore",
        icon=":material/history:",
        disabled=not _reason.strip(),
    ):
        try:
            rev = services.baseline.restore_revision(
                project, _pick.id, actor=actor_name(), reason=_reason
            )
        except PWAError as exc:
            show_error(exc, context="Revision 복원")
        else:
            st.success(
                f"복원 완료 → 새 Revision {rev.number} (복원 전 상태도 스냅샷으로 보존)",
                icon=":material/check:",
            )
            st.rerun()
else:
    st.caption("Revision 이 없습니다 (기준 데이터 적재 후 생깁니다).")
