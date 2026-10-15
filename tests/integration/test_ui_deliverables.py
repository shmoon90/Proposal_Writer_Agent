"""Streamlit AppTest: 산출물 화면 (Gate 1 전 비활성 → 생성 → QA → Gate 4 승인 → 최종 확정)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import builders as bld
from proposal_agent.agents import FakeAgentRunner
from proposal_agent.models import DocumentKind, ProjectMode
from proposal_agent.orchestrator import StepRunner
from proposal_agent.services import AppContext, Services
from proposal_agent.ui.state import PROJECT_KEY, SERVICES_KEY
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok

APP = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "app.py"
PAGE = "ui/app_pages/deliverables.py"


@pytest.fixture
def services(ctx: AppContext) -> Services:
    return Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
        ),
    )


def _app(services: Services, project_id: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state[SERVICES_KEY] = services
    at.session_state[PROJECT_KEY] = project_id
    return at


def test_deliverables_page_flow(services: Services) -> None:
    project = services.projects.create(
        name="UI 산출물",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 6, 30),
    )
    at = _app(services, project.id).run()
    at.switch_page(PAGE).run()
    assert not at.exception
    assert at.button(key="dl_generate").disabled and any("Gate 1" in e.value for e in at.error)

    services.documents.register_upload(
        project, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    r = StepRunner(services)
    r.run_extraction(project)
    r.run_requirement_extraction(project)
    r.run_verification(project)
    at.switch_page(PAGE).run()
    assert not at.button(key="dl_generate").disabled
    at.button(key="dl_generate").click().run()
    assert not at.exception
    assert len(services.generation.latest_deliverables(project)) == 9
    assert len(at.dataframe) >= 1 and at.image  # 산출물 표와 구성도 미리보기

    at.button(key="dl_qa").click().run()
    assert not at.exception
    assert services.gates.state(project, "gate4").status.value == "NEEDS_HUMAN_REVIEW"
    assert at.button(key="dl_finalize").disabled
    at.text_area(key="gate4_comments").set_value("검토 완료")
    at.button(key="gate4_approve").click().run()
    assert not at.exception
    assert services.gates.state(project, "gate4").passed
    at.button(key="dl_finalize").click().run()
    assert not at.exception
    final = services.ctx.paths.project_output_dir(project.output_dir) / "13_Final_Deliverables"
    assert final.exists() and len(list(final.iterdir())) == 9
