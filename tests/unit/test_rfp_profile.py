"""Phase 11: RFP 구조 프로파일 — 절 인식, RFP 자체 ID 색인, 잡음 정리, 블록 태그, 청크 경계, 목차·평가·제출, 커버리지."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from fixtures import builders as bld
from proposal_agent.agents import AgentRequest, FakeAgentRunner
from proposal_agent.config import ProjectPaths, Settings
from proposal_agent.ingest.chunker import build_chunks
from proposal_agent.ingest.rfp_profile import classify_heading, clean_text
from proposal_agent.models import BlockType, DocumentKind, Project, ProjectMode, QaResult
from proposal_agent.orchestrator import StepRunner
from proposal_agent.services import AppContext, Services

_TAGGED_RE = re.compile(r'<block id="([^"]+)"[^>]*rfp_id="([A-Z]+-\d+)"[^>]*>')


def _extract_only(ids: set[str]) -> Callable[[AgentRequest], dict[str, Any]]:
    """rfp_id 속성이 붙은 block 중 지정 ID만 요구사항으로 돌려주는 모의 추출기."""

    def handler(request: AgentRequest) -> dict[str, Any]:
        seen: dict[str, str] = {}
        for bid, rid in _TAGGED_RE.findall(request.prompt):
            if rid in ids and rid not in seen:
                seen[rid] = bid
        return {
            "requirements": [
                {
                    "name": f"{rid} 요구",
                    "description": f"{rid} 상세 요구사항",
                    "type": "functional",
                    "scope_class": "mandatory",
                    "is_mandatory": True,
                    "priority": "high",
                    "rfp_quote": f"{rid} 상세 요구사항",
                    "rfp_requirement_id": rid,
                    "source_block_ids": [bid],
                    "rationale": "원문 명시",
                    "confidence": 0.9,
                }
                for rid, bid in seen.items()
            ],
            "unresolved_items": [],
            "notes": "",
        }

    return handler


@pytest.fixture
def structured(tmp_path: Path) -> Iterator[tuple[Services, Project]]:
    ctx = AppContext.create(Settings(), paths=ProjectPaths(root=tmp_path), configure_logging=False)
    runner = FakeAgentRunner({"requirement_extractor": _extract_only({"SFR-001", "SFR-002"})})
    s = Services.from_context(ctx, runner=runner)
    p = s.projects.create(
        name="구조화 RFP",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 1),
        end_date=date(2027, 6, 30),
    )
    s.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_structured_rfp_docx()
    )
    StepRunner(s).run_extraction(p)
    yield s, p
    ctx.close()


def test_classify_heading_and_clean_text() -> None:
    assert classify_heading("Ⅲ. 요구사항") == "requirements"
    assert classify_heading("제4장 제약사항 및 연계") == "requirements"
    assert classify_heading("제6장 제출 조건") == "submission"
    assert classify_heading("5 제안서 평가방법") == "evaluation"
    assert classify_heading("4 제안서 목차 및 작성방법") == "proposal_guide"
    assert classify_heading("[별첨 1] 서식") == "appendix"
    assert classify_heading("시스템은 SSO로 인증해야 한다.") is None
    raw = "요구사항 | 고유번호 | SFR-001\n요구\n사항 | 정의 | 사건 관리\n세부 | 내용 | 1) 접수"
    text, removed = clean_text(raw)
    assert removed == 4 and "고유번호 | SFR-001" in text and "정의 | 사건 관리" in text
    assert not any(line.strip() in {"요구", "사항", "세부"} for line in text.splitlines())


def test_profile_sections_ids_and_tags(structured: tuple[Services, Project]) -> None:
    s, p = structured
    prof = s.extraction.rfp_profile(p)
    assert prof is not None
    assert prof.kinds_present() == [
        "overview",
        "scope",
        "requirements",
        "proposal_guide",
        "evaluation",
        "submission",
    ]
    top = [sec.heading for sec in prof.sections if sec.heading[:1] in "ⅠⅡⅢⅣⅤⅥ"]
    assert len(top) == 6 and top[2] == "Ⅲ. 요구사항"
    assert [e.rfp_id for e in prof.requirement_index] == bld.STRUCTURED_RFP_IDS
    names = {e.rfp_id: e.name for e in prof.requirement_index}
    assert names["SFR-001"] == "사건 접수 관리" and names["PER-001"] == "응답 시간"
    assert prof.id_prefixes == {"SFR": 2, "PER": 1, "SER": 1} and prof.id_width == 3
    assert prof.noise_lines_removed >= 4 * 4  # 상세 표 4개 × 세로 라벨(요구사항/요구/사항/세부)
    assert prof.warnings == []
    # 블록 태그: 상세 표는 각 ID로, 목록 표(여러 ID)는 태그 없음, 평가 절 블록은 evaluation
    blocks = s.extraction.current_blocks(p, required_only=True)
    tagged = {b.rfp_requirement_id for b in blocks if b.rfp_requirement_id}
    assert tagged == set(bld.STRUCTURED_RFP_IDS)
    list_table = next(
        b for b in blocks if b.block_type == BlockType.TABLE and "요구사항명" in b.text
    )
    assert list_table.rfp_requirement_id is None and list_table.section_kind == "requirements"
    detail = next(b for b in blocks if b.rfp_requirement_id == "SFR-001")
    assert "고유번호 | SFR-001" in detail.text and "요구 | " not in detail.text
    assert detail.table_cells is not None and detail.table_cells[1][0] == ""  # '요구' 라벨 셀 비움
    assert {b.section_kind for b in blocks if "배점" in b.text} == {"evaluation"}


def test_profile_toc_evaluation_submission(structured: tuple[Services, Project]) -> None:
    s, p = structured
    prof = s.extraction.rfp_profile(p)
    assert prof is not None
    assert prof.proposal_toc == bld.STRUCTURED_RFP_TOC
    assert s.extraction.rfp_proposal_toc(p) == bld.STRUCTURED_RFP_TOC
    assert prof.evaluation_items == [
        {"name": "기술 능력", "points": 90},
        {"name": "가격", "points": 10},
        {"name": "합계", "points": 100},
    ]
    assert any("제안서 7부" in item for item in prof.submission_items)
    summary = prof.summary_text()
    assert "SFR 2건" in summary and "제안 개요" in summary and "기술 능력(90)" in summary


def test_chunks_carry_tags_and_keep_signal(structured: tuple[Services, Project]) -> None:
    s, p = structured
    blocks = s.extraction.current_blocks(p, required_only=True)
    chunks = build_chunks(blocks, max_chars=700)
    rendered = "\n".join(c.text for c in chunks)
    assert 'section="requirements"' in rendered and 'rfp_id="SFR-001"' in rendered
    # RFP ID가 바뀌는 지점에서 절반 이상 찬 청크는 닫힌다: 한 청크에 두 ID 상세 표가 함께 들어가면
    # 앞 표가 들어간 시점에 청크가 절반 미만이었다는 뜻
    by_id = {b.id: b for b in blocks}
    for c in chunks:
        ids: list[str] = []
        for bid in c.block_ids:
            rid = by_id[bid].rfp_requirement_id
            if rid and rid not in ids:
                ids.append(rid)
        if len(ids) > 1:
            first_table = next(b for b in blocks if b.rfp_requirement_id == ids[0])
            assert len(first_table.text) + 120 < 700 * 0.5
    # 요구사항 절 청크는 짧아도 저신호로 건너뛰지 않는다
    plan = s.requirements.plan_extraction(p)
    assert plan.skipped == []


def test_coverage_warns_on_uncovered_rfp_ids_and_qa_rfp_07(
    structured: tuple[Services, Project],
) -> None:
    s, p = structured
    summary = s.requirements.extract(p)
    reqs = s.requirements.list_requirements(p)
    assert {r.rfp_requirement_id for r in reqs} == {"SFR-001", "SFR-002"}
    assert summary.uncovered_rfp_ids == ["PER-001", "SER-001"]
    warnings = [v for v in s.ctx.repos.validations.find(p.id) if v.rule_id == "rfp.uncovered_id"]
    assert {v.target_id for v in warnings} == {"PER-001", "SER-001"}
    assert all("연결된 추출 요구사항이 없음" in v.message for v in warnings)
    # 독립 QA: QA-RFP-07 실패로 집계
    result = s.qa.run(p, max_fix_rounds=0)
    assert result.qa_run is not None
    check = next(c for c in result.qa_run.checks if c.check_id == "QA-RFP-07")
    assert check.executed and check.result is QaResult.FAIL
    joined = " ".join(check.issues)
    assert "PER-001" in joined and "SER-001" in joined
