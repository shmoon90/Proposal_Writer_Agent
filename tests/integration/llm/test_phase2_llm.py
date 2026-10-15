"""실제 Claude Agent SDK 호출 계약 테스트 (``-m llm``, API 키 필요, 비용 발생).

기본 실행(``pytest``)에서는 제외되며 ``pytest -m llm tests/integration/llm -v`` 로만 실행한다.
모의 RFP(DOCX)로 추출 → 독립 검증 → Gate 1을 수행하고 스키마·출처·형식 간 일치를 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fixtures import builders as bld
from proposal_agent.config import ProjectPaths, load_settings
from proposal_agent.models import DocumentKind, GateStatus, ProjectMode, RequirementType
from proposal_agent.orchestrator import StepRunner
from proposal_agent.requirements.id_policy import normalize_text
from proposal_agent.services import AppContext, Services

pytestmark = pytest.mark.llm

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_DIR = ROOT / "tests" / "fixtures" / "llm_snapshots"


@pytest.fixture(scope="module")
def llm_services(tmp_path_factory: pytest.TempPathFactory) -> Services:
    settings = load_settings(ROOT / ".env")
    if not settings.has_api_key:
        pytest.skip("ANTHROPIC_API_KEY 없음 — LLM 계약 테스트 실행하지 않음")
    ctx = AppContext.create(
        settings, paths=ProjectPaths(tmp_path_factory.mktemp("llm")), configure_logging=False
    )
    return Services.from_context(ctx)


def _run(services: Services, name: str, file_name: str, data: bytes):
    project = services.projects.create(name=name, mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        project, kind=DocumentKind.RFP, file_name=file_name, data=data
    )
    runner = StepRunner(services)
    runner.run_extraction(project)
    _, ex = runner.run_requirement_extraction(project)
    vo, vr = runner.run_verification(project)
    return project, ex, vo, vr


def test_docx_extraction_and_verification_contract(llm_services: Services) -> None:
    project, ex, vo, vr = _run(llm_services, "LLM 계약 DOCX", "rfp.docx", bld.build_docx())
    reqs = llm_services.requirements.list_requirements(project)
    assert len(reqs) >= 8, [r.name for r in reqs]
    types = {r.type for r in reqs}
    assert RequirementType.FUNCTIONAL in types and RequirementType.NON_FUNCTIONAL in types
    assert all(r.source_refs and r.rfp_quote for r in reqs)  # 출처·인용 필수
    assert ex.dropped_missing_source == []
    assert vr.verdicts >= len(reqs)
    assert vo.gate is not None and vo.gate.status in (
        GateStatus.PASS,
        GateStatus.NEEDS_HUMAN_REVIEW,
    )
    assert ex.cost_usd + vr.cost_usd < 5.0
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_DIR / "phase2_docx.json").write_text(
        json.dumps(
            {
                "requirements": [r.model_dump(mode="json") for r in reqs],
                "cost": ex.cost_usd + vr.cost_usd,
            },
            ensure_ascii=False,
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )


def test_docx_and_pdf_extractions_reasonably_agree(llm_services: Services) -> None:
    p1, *_ = _run(llm_services, "LLM 일치 DOCX", "rfp.docx", bld.build_docx())
    p2, *_ = _run(llm_services, "LLM 일치 PDF", "rfp.pdf", bld.build_text_pdf())
    a = llm_services.requirements.list_requirements(p1)
    b = llm_services.requirements.list_requirements(p2)
    assert abs(len(a) - len(b)) <= max(3, len(a) // 3)
    key_phrases = [
        "sso",
        "20mb",
        "sms",
        "excel",
        "2초",
        "99.9",
        "암호화",
        "표준프레임워크",
        "100쪽",
    ]
    text_a = normalize_text(" ".join(r.name + r.description for r in a))
    text_b = normalize_text(" ".join(r.name + r.description for r in b))
    hits_a = sum(1 for k in key_phrases if normalize_text(k) in text_a)
    hits_b = sum(1 for k in key_phrases if normalize_text(k) in text_b)
    assert hits_a >= 7 and hits_b >= 7, (hits_a, hits_b)
