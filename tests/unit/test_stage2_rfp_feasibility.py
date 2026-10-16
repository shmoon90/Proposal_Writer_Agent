"""통합 개발 지시문 단계 2 — RFP 분석·사업성 평가.

입력 형식 확장(PPTX·이미지 OCR·회의록 종류), 요구사항 품질 검사(§5.3), 사업성 평가(§6: 13항목·권고·비용 산정 불가 표시·
참여 결정 기록), 파이프라인 단계·디스패처."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from pptx import Presentation
from pptx.util import Inches

from proposal_agent.config.errors import ValidationError
from proposal_agent.feasibility.service import (
    AssessmentInputs,
    assess_from_data,
    parse_krw,
    recommend,
)
from proposal_agent.ingest.image_reader import read_image
from proposal_agent.ingest.ocr import OcrLine, OcrResult
from proposal_agent.ingest.pptx_reader import read_pptx
from proposal_agent.ingest.service import detect_format
from proposal_agent.models import (
    AcceptanceStatus,
    BidRecommendation,
    BlockType,
    DecisionKind,
    DocumentKind,
    ExtractionStatus,
    FeasibilityItem,
    FeasibilityRating,
    FileFormat,
    Project,
    ProjectMode,
    ProjectSettings,
    Requirement,
    RequirementCategory,
    RequirementType,
    SourceRef,
    TechStack,
)
from proposal_agent.models.feasibility import ITEM_KEYS
from proposal_agent.orchestrator.runner import StepRunner
from proposal_agent.requirements.quality import check_requirement_quality, quality_summary
from proposal_agent.services import Services
from proposal_agent.services.pipeline_service import PROPOSAL_STEPS


def _pptx_bytes() -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])  # 제목+내용
    slide.shapes.title.text = "1. 사업 개요"
    slide.placeholders[
        1
    ].text_frame.text = (
        "본 사업은 민원 접수 시스템을 구축한다.\n시스템은 접수 화면을 제공하여야 한다."
    )
    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    slide2.shapes.title.text = "2. 요구사항 목록"
    rows, cols = 2, 2
    tbl = slide2.shapes.add_table(rows, cols, Inches(1), Inches(2), Inches(6), Inches(1)).table
    tbl.cell(0, 0).text, tbl.cell(0, 1).text = "ID", "내용"
    tbl.cell(1, 0).text, tbl.cell(1, 1).text = "SFR-001", "접수 등록"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --- 입력 형식 ----------------------------------------------------------------------------------
def test_pptx_reader_blocks_and_format_detection() -> None:
    data = _pptx_bytes()
    assert detect_format("rfp.pptx", data) == (FileFormat.PPTX, None)
    assert detect_format("scan.png", b"\x89PNG\r\n")[0] == FileFormat.IMAGE
    assert detect_format("scan.jpg", b"\xff\xd8\xff")[0] == FileFormat.IMAGE
    res = read_pptx(data, project_id="p", document_id="d", file_name="rfp.pptx")
    assert (
        res.status == ExtractionStatus.SUCCESS and res.page_count == 2 and res.unit_label == "slide"
    )
    types = [b.block_type for b in res.blocks]
    assert BlockType.TABLE in types and any(b.text.startswith("1. 사업 개요") for b in res.blocks)
    assert any("접수 화면" in b.text for b in res.blocks)
    table = next(b for b in res.blocks if b.block_type == BlockType.TABLE)
    assert table.table_cells and table.table_cells[1][0] == "SFR-001" and table.location.page == 2


@dataclass
class _FakeOcr:
    lines: list[OcrLine]
    ok: bool = True

    def available(self) -> bool:
        return self.ok

    def recognize(self, image):  # type: ignore[no-untyped-def]
        return OcrResult(lines=self.lines)


def _png_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (40, 20), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_reader_uses_ocr_or_fails_honestly() -> None:
    ocr = _FakeOcr(
        [
            OcrLine(text="요구사항: 접수 화면 제공", confidence=0.95),
            OcrLine(text="성능 3초", confidence=0.5),
        ]
    )
    res = read_image(
        _png_bytes(),
        ocr=ocr,
        ocr_review_threshold=0.8,
        project_id="p",
        document_id="d",
        file_name="scan.png",
    )
    assert res.status == ExtractionStatus.SUCCESS and len(res.blocks) == 2 and res.ocr_pages == 1
    assert res.blocks[0].extraction_method.value == "ocr" and res.blocks[1].needs_review
    none = read_image(
        _png_bytes(),
        ocr=None,
        ocr_review_threshold=0.8,
        project_id="p",
        document_id="d",
        file_name="scan.png",
    )
    assert none.status == ExtractionStatus.FAILED and "OCR" in none.error["message"]
    off = read_image(
        _png_bytes(),
        ocr=_FakeOcr([], ok=False),
        ocr_review_threshold=0.8,
        project_id="p",
        document_id="d",
        file_name="s.png",
    )
    assert off.status == ExtractionStatus.FAILED


def test_upload_rules_accept_pptx_image_and_meeting_notes(
    services: Services, proposal_project: Project
) -> None:
    kinds = dict(services.documents.kinds_for(ProjectMode.PROPOSAL))
    assert DocumentKind.MEETING_NOTE in kinds and kinds[DocumentKind.MEETING_NOTE] is False
    doc = services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="rfp.pptx", data=_pptx_bytes(), actor="t"
    )
    outcome = services.extraction.extract_document(proposal_project, doc, actor="t")
    assert outcome.run.status == ExtractionStatus.SUCCESS and outcome.run.block_count >= 3
    services.documents.register_upload(
        proposal_project,
        kind=DocumentKind.MEETING_NOTE,
        file_name="회의록.txt",
        data="결정: 알림 채널은 알림톡".encode(),
        actor="t",
    )
    services.documents.register_upload(
        proposal_project,
        kind=DocumentKind.RFP_ATTACHMENT,
        file_name="scan.png",
        data=_png_bytes(),
        actor="t",
    )


# --- 요구사항 품질 ----------------------------------------------------------------------------------
def _req(pid: str, rid: str, name: str, desc: str, **kw) -> Requirement:  # type: ignore[no-untyped-def]
    base = dict(
        id=rid,
        project_id=pid,
        name=name,
        description=desc,
        type=RequirementType.FUNCTIONAL,
        category=RequirementCategory.BUSINESS,
        created_by="agent",
        acceptance_status=AcceptanceStatus.ACCEPTED,
        source_refs=[SourceRef(document_id="doc", block_id="blk")],
        implementation_approach="- 접수 화면 구현",
        acceptance_criteria="접수 후 상태가 '접수' 로 바뀌면 통과",
    )
    base.update(kw)
    return Requirement(**base)


def test_requirement_quality_rules() -> None:
    pid = "prj"
    reqs = [
        _req(
            pid,
            "FR-001",
            "민원 접수 화면",
            "민원인이 접수 화면에서 민원을 등록하면 접수 번호를 발급한다",
        ),
        _req(
            pid,
            "FR-002",
            "민원 접수 화면",
            "민원인이 접수 화면에서 민원을 등록하면 접수 번호를 발급한다",
        ),  # 중복
        _req(
            pid,
            "FR-003",
            "조회 응답 성능 A",
            "민원 조회 응답 시간은 3초 이내여야 한다",
            type=RequirementType.NON_FUNCTIONAL,
            category=RequirementCategory.PERFORMANCE,
        ),
        _req(
            pid,
            "FR-004",
            "조회 응답 성능 B",
            "민원 조회 응답 시간은 5초 이내여야 한다",
            type=RequirementType.NON_FUNCTIONAL,
            category=RequirementCategory.PERFORMANCE,
        ),  # 충돌
        _req(
            pid,
            "FR-005",
            "사용성",
            "화면은 사용자 친화적이고 편리하게 구성한다",
            acceptance_criteria="편리하면 통과",
        ),  # 검증 불가·수용 기준
        _req(
            pid,
            "FR-006",
            "통계",
            "월별 통계를 제공한다",
            implementation_approach="",
            source_refs=[],
            acceptance_criteria="",
        ),  # 방안·근거·수용 기준 없음
    ]
    findings = check_requirement_quality(reqs)
    rules = quality_summary(findings)
    assert rules.get("Q-DUP") == 1 and {"FR-001", "FR-002"} == set(
        next(f for f in findings if f.rule == "Q-DUP").requirement_ids
    )
    assert (
        rules.get("Q-CONFLICT") == 1
        and "3초" in next(f for f in findings if f.rule == "Q-CONFLICT").message
    )
    assert any(f.rule == "Q-VAGUE" and f.requirement_ids == ["FR-005"] for f in findings)
    assert any(f.rule == "Q-ACCEPT" and f.requirement_ids == ["FR-005"] for f in findings)
    assert any(
        f.rule == "Q-APPROACH" and f.requirement_ids == ["FR-006"] and f.level == "warning"
        for f in findings
    )
    assert any(f.rule == "Q-NOSRC" and f.requirement_ids == ["FR-006"] for f in findings)
    assert any(f.rule == "Q-NFR" and "보안" in f.message for f in findings)
    assert any(f.rule == "Q-RULES" and f.requirement_ids == ["FR-006"] for f in findings)


# --- 사업성 평가 ----------------------------------------------------------------------------------
def test_parse_krw_and_recommend_rules() -> None:
    assert parse_krw("약 4.5억 원") == Decimal("450000000")
    assert parse_krw("450,000,000원 (부가세 포함)") == Decimal("450000000")
    assert parse_krw("3천만원") == Decimal("30000000")
    assert parse_krw("5개월") is None
    items = [FeasibilityItem(key=k, title=t) for k, t in ITEM_KEYS]  # 전부 unknown
    assert recommend(items)[0] == BidRecommendation.NEEDS_REVIEW
    for it in items:
        it.rating = FeasibilityRating.GOOD
    assert recommend(items)[0] == BidRecommendation.RECOMMENDED
    items[2].rating = FeasibilityRating.RISK
    assert recommend(items)[0] == BidRecommendation.CONDITIONAL
    items[4].user_rating = FeasibilityRating.RISK  # 사용자 판정이 코드 판정을 덮어씀
    rec, basis = recommend(items)
    assert rec == BidRecommendation.NOT_RECOMMENDED and any("위험 항목 2개" in b for b in basis)


def test_assessment_from_data_marks_unknowns_and_never_invents_cost(
    proposal_project: Project,
) -> None:
    settings = ProjectSettings(
        budget_amount=Decimal("450000000"), tech_stack=TechStack(language="Java")
    )
    reqs = [_req(proposal_project.id, "FR-001", "접수", "접수 화면에서 등록하면 번호를 발급한다")]
    inp = AssessmentInputs(
        project=proposal_project,
        settings=settings,
        analysis={
            "evaluation_criteria": ["기술 90", "가격 10"],
            "integration_targets": ["기존 포털"],
            "uncertainties": ["OTP 채널"],
        },
        requirements=reqs,
        research=[],
        wbs=[],
        roles=[],
        allocations=[],
        quality=[],
    )
    a = assess_from_data(inp)
    assert len(a.items) == 13 and [i.key for i in a.items] == [k for k, _ in ITEM_KEYS]
    prof = a.item("profitability")
    assert (
        prof is not None
        and prof.rating == FeasibilityRating.UNKNOWN
        and a.cost_estimate["status"] == "unavailable"
    )
    assert any("원가 산정 불가" in b for b in prof.code_basis) and prof.needs_input
    assert a.item("legacy").rating == FeasibilityRating.CAUTION  # type: ignore[union-attr]
    assert a.item("effort").rating == FeasibilityRating.UNKNOWN  # type: ignore[union-attr]
    assert a.recommendation == BidRecommendation.NEEDS_REVIEW and a.open_questions


def test_feasibility_service_assess_decide_and_pipeline(
    services: Services, proposal_project: Project
) -> None:
    keys = [s.key for s in PROPOSAL_STEPS]
    assert keys.index("bid_assessment") == keys.index("req_verify") + 1
    services.projects.update_settings(
        proposal_project,
        ProjectSettings(
            budget_amount=Decimal("100000000"), cost_rates={"개발자": Decimal("8000000")}
        ),
    )
    runner = StepRunner(services)
    outcome = runner.run_step(proposal_project, "bid_assessment", actor="tester")
    assert "권고" in outcome.summary and outcome.run.status.value == "approved"
    a = services.feasibility.latest(proposal_project)
    assert a is not None and a.version == 1 and a.report_path.endswith(".md")
    report = services.ctx.paths.resolve_output(a.report_path)
    assert report.exists() and "사업 참여 타당성 평가서" in report.read_text(encoding="utf-8")
    assert report.with_suffix(".json").exists()
    # 사용자 판정으로 재평가 → 버전 2, 권고 재계산
    a2 = services.feasibility.assess(
        proposal_project, actor="tester", user_ratings={"strategic_fit": ("good", "핵심 고객")}
    )
    assert a2.version == 2 and a2.item("strategic_fit").user_rating == FeasibilityRating.GOOD  # type: ignore[union-attr]
    # 결정: 근거 없으면 거부, 권한 미확인이면 제안, 확인이면 공식 결정
    with pytest.raises(ValidationError):
        services.feasibility.record_decision(
            proposal_project,
            a2,
            choice=BidRecommendation.CONDITIONAL,
            rationale=" ",
            decider="PM",
            authority_confirmed=True,
        )
    d = services.feasibility.record_decision(
        proposal_project,
        a2,
        choice=BidRecommendation.CONDITIONAL,
        rationale="단가 확정 후 참여",
        decider="영업",
        authority_confirmed=False,
    )
    assert d.code == "DEC-001" and not d.is_binding and d.kind == DecisionKind.OFFICIAL_DECISION
    d2 = services.feasibility.record_decision(
        proposal_project,
        a2,
        choice=BidRecommendation.RECOMMENDED,
        rationale="사업부장 승인",
        decider="사업부장",
        authority_confirmed=True,
    )
    assert d2.code == "DEC-002" and d2.is_binding
    assert services.feasibility.latest(proposal_project).status == "decided"  # type: ignore[union-attr]


def test_assessment_date_helper() -> None:
    assert date.today().year >= 2026
