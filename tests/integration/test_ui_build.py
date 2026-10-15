"""Streamlit AppTest: 구축 단계 화면 (기준 문서 적재 → 변경 요청 등록 → 분석 → 결정 → 승인 → 변경관리대장)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import excel_builders as xb
from proposal_agent.agents import FakeAgentRunner
from proposal_agent.models import ChangeStatus, DocumentKind, ProjectMode
from proposal_agent.services import AppContext, Services
from proposal_agent.ui.state import PROJECT_KEY, SERVICES_KEY

APP = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "app.py"
BASELINE_PAGE = "ui/app_pages/build_baseline.py"
CHANGES_PAGE = "ui/app_pages/changes.py"


@pytest.fixture
def services(ctx: AppContext) -> Services:
    return Services.from_context(ctx, runner=FakeAgentRunner({}))


def _app(services: Services, project_id: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state[SERVICES_KEY] = services
    at.session_state[PROJECT_KEY] = project_id
    return at


def test_build_pages_flow(services: Services) -> None:
    project = services.projects.create(name="UI 구축", mode=ProjectMode.BUILD)
    at = _app(services, project.id).run()
    at.switch_page(BASELINE_PAGE).run()
    assert not at.exception
    assert at.button(key="bb_load").disabled and any(
        "필수 문서가 없습니다" in w.value for w in at.warning
    )

    services.documents.register_upload(
        project,
        kind=DocumentKind.REQUIREMENT_SPEC,
        file_name="spec.xlsx",
        data=xb.build_requirement_spec(),
    )
    services.documents.register_upload(
        project,
        kind=DocumentKind.TRACE_MATRIX,
        file_name="trace.xlsx",
        data=xb.build_trace_matrix(),
    )
    services.documents.register_upload(
        project, kind=DocumentKind.WBS, file_name="wbs.xlsx", data=xb.build_wbs()
    )
    at.switch_page(BASELINE_PAGE).run()
    at.button(key="bb_profile").click().run()
    assert not at.exception and any("자동 매핑" in e.label for e in at.expander)
    at.button(key="bb_load").click().run()
    assert not at.exception
    assert (
        any("적재 완료" in s.label for s in at.status)
        or services.ctx.repos.requirements.count(project.id) == 6
    )

    # 변경 관리 화면
    at.switch_page(CHANGES_PAGE).run()
    assert not at.exception
    at.text_area(key="ch_text").set_value("팩스 접수 기능은 더 이상 필요 없으니 삭제해 주세요.")
    at.text_input(key="ch_requester").set_value("홍길동")
    at.text_input(key="ch_reason").set_value("범위 축소")
    at.button(key="ch_create").click().run()
    assert not at.exception
    crs = services.changes.list_requests(project)
    assert len(crs) == 1 and crs[0].status == ChangeStatus.REQUESTED
    at.checkbox(key="ch_use_agent").set_value(False)
    at.button(key="ch_analyze").click().run()
    assert not at.exception
    cr = services.changes.get(project, crs[0].id)
    assert (
        cr.status == ChangeStatus.ANALYZED
        and cr.candidates[0].classification.value == "DELETE_REQUEST"
    )
    assert at.button(key="ch_approve").disabled  # 미결정 후보
    at.radio(key=f"ch_dec_{cr.id}_C01").set_value("수락")
    at.button(key=f"ch_save_{cr.id}_C01").click().run()
    assert not at.exception
    assert not at.button(key="ch_approve").disabled
    at.text_input(key="ch_comments").set_value("승인")
    at.button(key="ch_approve").click().run()
    assert not at.exception
    cr = services.changes.get(project, cr.id)
    assert cr.status == ChangeStatus.APPLIED and len(cr.after_files) == 3
    assert any("변경관리대장" in s.value for s in at.subheader)
