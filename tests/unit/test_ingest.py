"""ingest: DOCX/TXT/텍스트 PDF/스캔 PDF/표/다중 페이지/손상/암호화/미지원, Gate 0, 형식 간 일치.

모든 문서는 tests/fixtures/builders.py 가 만드는 **모의 문서**다 (실제 RFP 아님).
OCR이 필요한 테스트는 rapidocr 모델이 로드될 때만 실행되고, 아니면 skip 사유를 남긴다.
"""

from __future__ import annotations

import pytest

from fixtures import builders as bld
from proposal_agent.ingest import build_chunks, detect_format
from proposal_agent.ingest.base import looks_like_heading, looks_like_list_item
from proposal_agent.ingest.ocr import NullOcrEngine
from proposal_agent.models import (
    BlockType,
    DocumentKind,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    GateStatus,
    Project,
)
from proposal_agent.requirements.id_policy import normalize_text
from proposal_agent.services import Services


def _upload_and_extract(
    services: Services,
    project: Project,
    name: str,
    data: bytes,
    kind: DocumentKind = DocumentKind.RFP,
):
    doc = services.documents.register_upload(project, kind=kind, file_name=name, data=data)
    return services.extraction.extract_document(project, doc)


@pytest.fixture
def ocr_available(services: Services) -> bool:
    return services.extraction.ocr.available()


# --- 형식 판별 / 휴리스틱 ---------------------------------------------------------------------


def test_detect_format_and_unsupported_hints() -> None:
    assert detect_format("a.pdf", b"%PDF-1.4")[0] == FileFormat.PDF
    assert detect_format("a.docx", b"PK\x03\x04")[0] == FileFormat.DOCX
    assert detect_format("a.txt", b"hello")[0] == FileFormat.TXT
    fmt, hint = detect_format("old.doc", b"\xd0\xcf\x11\xe0")
    assert fmt == FileFormat.UNSUPPORTED and hint and ".docx" in hint
    fmt, hint = detect_format("a.hwp", b"xx")
    assert fmt == FileFormat.UNSUPPORTED and "PDF" in (hint or "")
    fmt, hint = detect_format("fake.pdf", b"not a pdf")
    assert fmt == FileFormat.PDF and hint  # 확장자만 pdf → 경고 힌트


def test_heading_and_list_heuristics() -> None:
    assert looks_like_heading("제2장 기능 요구사항")
    assert looks_like_heading("3.1 보안 요구사항")
    assert not looks_like_heading("3.1 보안 요구사항은 다음과 같다.")
    assert looks_like_list_item("- 항목")
    assert looks_like_list_item("1) 항목")
    assert not looks_like_list_item("일반 문장입니다.")


# --- 리더별 -------------------------------------------------------------------------------


def test_docx_extracts_headings_lists_tables_without_page_numbers(
    services: Services, proposal_project: Project
) -> None:
    out = _upload_and_extract(services, proposal_project, "rfp.docx", bld.build_docx())
    run, blocks = out.run, out.blocks
    assert run.status == ExtractionStatus.SUCCESS and run.file_format == FileFormat.DOCX
    assert run.page_count is None and all(
        b.location.page is None for b in blocks
    )  # 페이지 추측 금지
    types = {b.block_type for b in blocks}
    assert {
        BlockType.TITLE,
        BlockType.HEADING,
        BlockType.LIST_ITEM,
        BlockType.TABLE,
        BlockType.TOC,
    } <= types
    tables = [b for b in blocks if b.block_type == BlockType.TABLE]
    assert (
        run.table_count == 2 and tables[0].table_cells and tables[0].table_cells[1][1] == "2초 이내"
    )
    fr_a = next(b for b in blocks if "FR-A" in b.text)
    assert (
        fr_a.location.section == "제2장 기능 요구사항" and fr_a.location.paragraph_index is not None
    )
    assert any("페이지 번호를 확인할 수 없어" in w for w in run.warnings)
    assert services.ctx.repos.blocks.for_run(proposal_project.id, run.id)[0].text.startswith(
        "차세대"
    )


def test_txt_records_line_numbers(services: Services, proposal_project: Project) -> None:
    out = _upload_and_extract(services, proposal_project, "rfp.txt", bld.build_txt())
    assert out.run.status == ExtractionStatus.SUCCESS and out.run.unit_label == "line"
    fr_b = next(b for b in out.blocks if "FR-B" in b.text)
    assert fr_b.location.line_start and fr_b.location.page is None
    assert fr_b.block_type == BlockType.LIST_ITEM


def test_text_pdf_multi_page_with_tables(services: Services, proposal_project: Project) -> None:
    out = _upload_and_extract(
        services, proposal_project, "rfp.pdf", bld.build_text_pdf(pad_pages=2)
    )
    run = out.run
    assert run.status == ExtractionStatus.SUCCESS and run.page_count >= 3 and run.ocr_pages == 0
    assert run.text_pages == run.page_count
    assert run.table_count == 2
    pages = {b.location.page for b in out.blocks}
    assert len(pages) >= 3 and None not in pages
    nfr_a = next(b for b in out.blocks if "NFR-A" in b.text)
    assert nfr_a.location.page == 1 and nfr_a.location.section == "제3장 비기능 요구사항"
    assert all(b.extraction_method == ExtractionMethod.TEXT for b in out.blocks)


def test_scanned_pdf_without_ocr_is_flagged_not_guessed(
    services: Services, proposal_project: Project
) -> None:
    services.extraction._ocr = NullOcrEngine("테스트: OCR 없음")  # type: ignore[attr-defined]
    out = _upload_and_extract(services, proposal_project, "scan.pdf", bld.build_scanned_pdf())
    run = out.run
    assert run.status == ExtractionStatus.PARTIAL and run.ocr_pages == 0
    assert any("OCR" in w for w in run.warnings)
    assert (
        run.low_confidence_blocks == 1
        and out.blocks[0].needs_review
        and out.blocks[0].block_type == BlockType.PAGE_TEXT
    )
    gate = services.extraction.evaluate_gate0(proposal_project)
    assert gate.status == GateStatus.NEEDS_HUMAN_REVIEW


def test_scanned_pdf_with_ocr(
    services: Services, proposal_project: Project, ocr_available: bool
) -> None:
    if not ocr_available:
        pytest.skip("rapidocr 엔진을 로드할 수 없는 환경 (모델 미다운로드 등)")
    out = _upload_and_extract(services, proposal_project, "scan.pdf", bld.build_scanned_pdf())
    run = out.run
    assert run.ocr_pages == 1 and run.text_pages == 0 and run.ocr_engine == "rapidocr"
    assert all(b.extraction_method == ExtractionMethod.OCR for b in out.blocks)
    joined = normalize_text(" ".join(b.text for b in out.blocks))
    assert normalize_text("SSO로 처리해야") in joined and normalize_text("SMS와 이메일") in joined
    assert all(b.confidence > 0.5 for b in out.blocks)


def test_mixed_pdf_marks_methods_per_page(
    services: Services, proposal_project: Project, ocr_available: bool
) -> None:
    if not ocr_available:
        pytest.skip("rapidocr 엔진을 로드할 수 없는 환경")
    out = _upload_and_extract(services, proposal_project, "mixed.pdf", bld.build_mixed_pdf())
    run = out.run
    assert run.page_count == 2 and run.text_pages == 1 and run.ocr_pages == 1
    methods = {b.location.page: b.extraction_method for b in out.blocks}
    assert methods[1] == ExtractionMethod.TEXT and methods[2] == ExtractionMethod.OCR
    doc = services.documents.list_documents(proposal_project.id)[0]
    assert doc.extraction_method == ExtractionMethod.MIXED and doc.page_count == 2


@pytest.mark.parametrize(
    ("name", "builder", "expect_in_message"),
    [
        ("enc.pdf", bld.build_encrypted_pdf, "암호"),
        ("bad.pdf", bld.build_corrupted_bytes, "열 수 없"),
        ("bad.docx", bld.build_corrupted_docx, "열 수 없"),
        ("empty.txt", lambda: b"   \n\n", "빈"),
    ],
)
def test_failures_report_cause_and_resolution(
    services: Services, proposal_project: Project, name: str, builder, expect_in_message: str
) -> None:
    out = _upload_and_extract(services, proposal_project, name, builder())
    run = out.run
    assert run.status == ExtractionStatus.FAILED and run.block_count == 0
    assert run.error and expect_in_message in run.error["message"] and run.error["resolution"]
    errors = services.ctx.repos.audit.recent(proposal_project.id, errors_only=True)
    assert errors and errors[0].action == "document.extraction_failed"
    assert services.extraction.evaluate_gate0(proposal_project).status == GateStatus.FAIL


def test_unsupported_legacy_doc_reports_conversion_hint(
    services: Services, proposal_project: Project
) -> None:
    out = _upload_and_extract(
        services, proposal_project, "old.doc", b"\xd0\xcf\x11\xe0" + b"x" * 64
    )
    assert out.run.status == ExtractionStatus.UNSUPPORTED
    assert ".docx" in out.run.error["resolution"]
    assert services.extraction.evaluate_gate0(proposal_project).status == GateStatus.FAIL


def test_extract_all_only_missing_and_reruns_keep_old_blocks(
    services: Services, proposal_project: Project
) -> None:
    doc = services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="a.txt", data=bld.build_txt()
    )
    first = services.extraction.extract_all(proposal_project)
    assert len(first) == 1
    assert services.extraction.extract_all(proposal_project, only_missing=True) == []
    second = services.extraction.extract_all(proposal_project)
    assert second[0].run.id != first[0].run.id
    assert (
        services.ctx.repos.blocks.count(proposal_project.id) == first[0].run.block_count * 2
    )  # 이전 블록 보존
    assert (
        services.extraction.current_blocks(proposal_project)[0].extraction_run_id
        == second[0].run.id
    )
    assert services.ctx.repos.documents.get(doc.id).extracted_text_path.endswith(".json")


# --- Gate 0 ----------------------------------------------------------------------------


def test_gate0_pass_and_requires_required_docs(
    services: Services, proposal_project: Project
) -> None:
    assert services.extraction.evaluate_gate0(proposal_project).status == GateStatus.FAIL
    _upload_and_extract(services, proposal_project, "rfp.docx", bld.build_docx())
    gate = services.extraction.evaluate_gate0(proposal_project)
    assert gate.status == GateStatus.PASS and gate.evaluated_by.startswith("code:")
    assert services.ctx.repos.gate_evaluations.latest(proposal_project.id, "gate0").id == gate.id


def test_gate0_not_yet_extracted_is_fail(services: Services, proposal_project: Project) -> None:
    services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    gate = services.extraction.evaluate_gate0(proposal_project)
    assert gate.status == GateStatus.FAIL and "추출하지 않았습니다" in gate.reasons[0]


# --- 형식 간 일치 / 청크 --------------------------------------------------------------------


def test_docx_and_pdf_yield_matching_requirement_lines(
    services: Services, proposal_project: Project
) -> None:
    """같은 내용을 DOCX와 PDF로 주면 주요 요구사항 문장이 합리적으로 일치해야 한다 (추출 계층, LLM 아님)."""
    docx_out = _upload_and_extract(services, proposal_project, "same.docx", bld.build_docx())
    pdf_out = _upload_and_extract(
        services,
        proposal_project,
        "same.pdf",
        bld.build_text_pdf(),
        kind=DocumentKind.RFP_ATTACHMENT,
    )

    def keyed(blocks):
        found = {}
        for b in blocks:
            for key in bld.SAMPLE_REQUIREMENT_KEYS:
                if key + "." in b.text:
                    found[key] = normalize_text(b.text.split(key + ".", 1)[1])
        return found

    d, p = keyed(docx_out.blocks), keyed(pdf_out.blocks)
    assert set(d) == set(bld.SAMPLE_REQUIREMENT_KEYS) and set(p) == set(bld.SAMPLE_REQUIREMENT_KEYS)
    assert sum(1 for k in d if d[k] == p[k]) >= len(d) - 1  # 줄바꿈 차이 허용


def test_chunks_respect_size_skip_toc_and_tag_blocks(
    services: Services, proposal_project: Project
) -> None:
    out = _upload_and_extract(services, proposal_project, "rfp.docx", bld.build_docx())
    chunks = build_chunks(out.blocks, max_chars=900)
    assert len(chunks) > 1 and all(c.char_count <= 900 + 600 for c in chunks)
    all_ids = [bid for c in chunks for bid in c.block_ids]
    assert len(all_ids) == len(set(all_ids))
    toc_ids = {b.id for b in out.blocks if b.block_type == BlockType.TOC}
    assert not toc_ids & set(all_ids)
    assert '<block id="' in chunks[0].text and 'type="' in chunks[0].text
