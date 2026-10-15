"""Streamlit AppTest: 모드별 화면 흐름 (생성 → 프로젝트 화면 → 업로드 상태 → 게이트)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from proposal_agent.models import ApprovalDecision, DocumentKind, ProjectMode, StepStatus
from proposal_agent.services import Services
from proposal_agent.ui.state import PROJECT_KEY, SERVICES_KEY

APP = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "app.py"
PROJECT_PAGE = "ui/app_pages/project.py"


def _app(services: Services) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state[SERVICES_KEY] = services
    return at


def test_home_renders_without_api_key_warning_and_no_exception(services: Services) -> None:
    at = _app(services).run()
    assert not at.exception
    assert at.title[0].value == "Proposal Writer Agent"
    assert any("ANTHROPIC_API_KEY" in w.value for w in at.warning)
    assert "sk-" not in "".join(w.value for w in at.warning)


def test_create_proposal_project_then_project_page_requires_rfp(services: Services) -> None:
    at = _app(services).run()
    at.text_input(key="new_name").set_value("UI 제안 프로젝트")
    at.form_submit_button[0].click().run()
    assert not at.exception
    assert at.success and "제안 단계" in at.success[0].value
    pid = at.session_state[PROJECT_KEY]
    project = services.projects.get(pid)
    assert project.mode == ProjectMode.PROPOSAL

    at.switch_page(PROJECT_PAGE).run()
    assert not at.exception
    assert any("RFP" in w.value for w in at.warning)  # 필수 문서 미등록
    labels = at.selectbox(key="upload_kind").options
    assert labels[0].startswith("RFP (필수)")
    assert not any("WBS" in label for label in labels)  # 제안 모드에는 구축용 문서 종류 없음


def test_build_mode_lists_build_documents(services: Services) -> None:
    at = _app(services).run()
    at.get("segmented_control")[0].set_value(ProjectMode.BUILD.label)
    at.run()
    at.text_input(key="new_name").set_value("UI 구축 프로젝트")
    at.form_submit_button[0].click().run()
    assert not at.exception
    project = services.projects.get(at.session_state[PROJECT_KEY])
    assert project.mode == ProjectMode.BUILD

    at.switch_page(PROJECT_PAGE).run()
    assert not at.exception
    labels = at.selectbox(key="upload_kind").options
    assert [label.split(" (")[0] for label in labels] == [
        DocumentKind.REQUIREMENT_SPEC.label,
        DocumentKind.TRACE_MATRIX.label,
        DocumentKind.WBS.label,
        DocumentKind.STAFFING_PLAN.label,
        DocumentKind.OTHER.label,
    ]
    assert "인력 투입계획서 (선택)" in labels
    warning_text = " ".join(w.value for w in at.warning)
    assert "요구사항 정의서" in warning_text and "WBS" in warning_text


def test_blank_name_shows_user_error_not_exception(services: Services) -> None:
    at = _app(services).run()
    at.text_input(key="new_name").set_value("   ")
    at.form_submit_button[0].click().run()
    assert not at.exception
    assert at.error and "프로젝트명" in at.error[0].value and "조치" in at.error[0].value
    assert services.projects.list_projects() == []


def test_project_page_without_selection_redirects(services: Services) -> None:
    at = _app(services).run()
    at.switch_page(PROJECT_PAGE).run()
    assert not at.exception
    assert any("선택된 프로젝트가 없습니다" in w.value for w in at.warning)


def test_open_existing_project(services: Services) -> None:
    created = services.projects.create(name="기존 프로젝트", mode=ProjectMode.BUILD)
    at = _app(services).run()
    at.selectbox(key="open_choice").select(at.selectbox(key="open_choice").options[0])
    at.button(key="open_button").click().run()
    assert not at.exception
    assert at.session_state[PROJECT_KEY] == created.id


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_gate_buttons_on_project_page(services: Services, decision: str) -> None:
    project = services.projects.create(name="게이트", mode=ProjectMode.PROPOSAL)
    run = services.pipeline.start_step(project, "req_verify")
    services.pipeline.complete_step(project, run, summary="검증 요약")
    at = _app(services)
    at.session_state[PROJECT_KEY] = project.id
    at.run()
    at.switch_page(PROJECT_PAGE).run()
    assert not at.exception
    if decision == "reject":
        at.button(key=f"reject_{run.id}").click().run()
        assert at.error and "반려 사유" in at.error[0].value  # 사유 없이 반려 불가
        at.text_area(key=f"gate_comments_{run.id}").set_value("보완 필요")
        at.button(key=f"reject_{run.id}").click().run()
        assert services.ctx.repos.step_runs.get(run.id).status == StepStatus.FAILED
    else:
        at.button(key=f"approve_{run.id}").click().run()
        assert services.ctx.repos.step_runs.get(run.id).status == StepStatus.APPROVED
        history = services.pipeline.gate_history(project)
        assert history[0][0].decision == ApprovalDecision.APPROVED
    assert not at.exception
