"""Streamlit AppTest: 문서 추출 화면과 요구사항 화면 (모의 문서 + FakeAgentRunner)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import builders as bld
from proposal_agent.agents import AgentRequest, FakeAgentRunner
from proposal_agent.models import DocumentKind, GateStatus, ProjectMode
from proposal_agent.orchestrator import StepRunner
from proposal_agent.services import AppContext, Services
from proposal_agent.ui.state import PROJECT_KEY, SERVICES_KEY

APP = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "app.py"
_BLOCK_RE = re.compile(r'<block id="([^"]+)"[^>]*>\n(.*?)\n</block>', re.DOTALL)


def _extractor(request: AgentRequest) -> dict[str, Any]:
    reqs = []
    for bid, text in _BLOCK_RE.findall(request.prompt):
        if re.search(r"(?<![A-Z])FR-[A-Z]\.", text):
            reqs.append(
                {
                    "name": text.split(".", 1)[1].strip()[:40],
                    "description": text,
                    "type": "functional",
                    "rfp_quote": text,
                    "source_block_ids": [bid],
                    "confidence": 0.9,
                }
            )
    return {"requirements": reqs, "unresolved_items": [], "notes": ""}


def _verifier(request: AgentRequest) -> dict[str, Any]:
    ids = re.findall(r'"id": "([A-Z]+-\d+)"', request.prompt)
    return {
        "verdicts": [{"requirement_id": i, "verdict": "verified"} for i in ids],
        "findings": [],
        "coverage_estimate": 1.0,
    }


@pytest.fixture
def services(ctx: AppContext) -> Services:
    return Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {"requirement_extractor": _extractor, "requirement_verifier": _verifier}
        ),
    )


def _app(services: Services, project_id: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state[SERVICES_KEY] = services
    at.session_state[PROJECT_KEY] = project_id
    return at


def test_extraction_page_shows_documents_runs_extraction_and_gate0(services: Services) -> None:
    project = services.projects.create(name="UI 추출", mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        project, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    services.documents.register_upload(
        project, kind=DocumentKind.RFP_ATTACHMENT, file_name="old.doc", data=b"\xd0\xcf\x11\xe0xx"
    )
    at = _app(services, project.id).run()
    at.switch_page("ui/app_pages/extraction.py").run()
    assert not at.exception
    assert at.error  # Gate 0 아직 평가 없음 → FAIL 표시
    at.button(key="extract_all").click().run()
    assert not at.exception
    df = at.dataframe[0].value
    assert set(df["파일"]) == {"rfp.docx", "old.doc"}
    assert df.loc[df["파일"] == "rfp.docx", "추출"].iloc[0] == "success"
    assert df.loc[df["파일"] == "old.doc", "추출"].iloc[0] == "unsupported"
    # 선택 첨부 실패는 Gate 0(필수 문서 기준)에 영향 없음 → PASS
    assert services.gates.state(project, "gate0").status == GateStatus.PASS
    assert any(".docx" in e.value for e in at.error)  # 미지원 문서 변환 안내


def test_requirements_page_flow_extract_verify_edit_gate1(services: Services) -> None:
    project = services.projects.create(name="UI 요구사항", mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        project, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    at = _app(services, project.id).run()
    at.switch_page("ui/app_pages/requirements.py").run()
    assert not at.exception
    assert at.button(key="req_extract").disabled  # Gate 0 전에는 비활성
    StepRunner(services).run_extraction(project)
    at.switch_page("ui/app_pages/requirements.py").run()
    assert not at.button(key="req_extract").disabled
    at.button(key="req_extract").click().run()
    assert not at.exception
    reqs = services.requirements.list_requirements(project)
    assert len(reqs) == 4 and all(r.id.startswith("FR-") for r in reqs)
    df = at.dataframe[0].value
    assert list(df["ID"]) == [r.id for r in reqs] and all(df["원본 위치"].str.contains("rfp.docx"))

    at.button(key="req_verify").click().run()
    assert not at.exception
    assert services.gates.state(project, "gate1").status == GateStatus.PASS
    assert any("Gate 1" in s.value and "PASS" in s.value for s in at.success)

    # 사용자 수정 (폼) 후 검토 승인
    first = reqs[0].id
    at.text_input[0].set_value("수정된 요구사항명")
    at.form_submit_button[0].click().run()
    assert not at.exception
    assert services.requirements.get(project, first).name == "수정된 요구사항명"
    at.button(key=f"approve_{first}").click().run()
    assert services.requirements.get(project, first).review_status.value == "approved"


def test_requirements_page_without_project_redirects(services: Services) -> None:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state[SERVICES_KEY] = services
    at.run()
    at.switch_page("ui/app_pages/requirements.py").run()
    assert not at.exception and at.warning
