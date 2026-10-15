"""services.document_service: 업로드 등록, 중복, 필수 문서 규칙, 형식 검사."""

from __future__ import annotations

import pytest

from proposal_agent.config import IngestError, ValidationError
from proposal_agent.models import DocumentKind, Project
from proposal_agent.services import Services


def test_register_upload_copies_original_and_records(
    services: Services, proposal_project: Project
) -> None:
    doc = services.documents.register_upload(
        proposal_project,
        kind=DocumentKind.RFP,
        file_name="제안요청서.pdf",
        data=b"%PDF-1.4 x",
        actor="tester",
    )
    path = services.ctx.paths.resolve_output(doc.stored_path)
    assert path.parent.name == "01_RFP_Original" and path.read_bytes() == b"%PDF-1.4 x"
    assert doc.size_bytes == 10 and doc.is_required_input is True
    assert services.documents.missing_required(proposal_project) == []


def test_same_filename_is_preserved_with_suffix(
    services: Services, proposal_project: Project
) -> None:
    a = services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="rfp.pdf", data=b"%PDF 1"
    )
    b = services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP_ATTACHMENT, file_name="rfp.pdf", data=b"%PDF 2"
    )
    assert a.stored_path.endswith("/rfp.pdf") and b.stored_path.endswith("/rfp_1.pdf")
    assert services.ctx.paths.resolve_output(a.stored_path).read_bytes() == b"%PDF 1"


def test_duplicate_content_rejected(services: Services, proposal_project: Project) -> None:
    services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="a.pdf", data=b"%PDF same"
    )
    with pytest.raises(ValidationError):
        services.documents.register_upload(
            proposal_project, kind=DocumentKind.RFP, file_name="b.pdf", data=b"%PDF same"
        )


def test_required_inputs_per_mode(
    services: Services, proposal_project: Project, build_project: Project
) -> None:
    assert services.documents.missing_required(proposal_project) == [DocumentKind.RFP]
    assert services.documents.missing_required(build_project) == [
        DocumentKind.REQUIREMENT_SPEC,
        DocumentKind.TRACE_MATRIX,
        DocumentKind.WBS,
    ]
    optional = [k for k, req in services.documents.kinds_for(build_project.mode) if not req]
    assert DocumentKind.STAFFING_PLAN in optional
    for kind, name in [
        (DocumentKind.REQUIREMENT_SPEC, "req.xlsx"),
        (DocumentKind.TRACE_MATRIX, "trace.xlsx"),
        (DocumentKind.WBS, "wbs.xlsx"),
    ]:
        services.documents.register_upload(
            build_project, kind=kind, file_name=name, data=name.encode()
        )
    assert services.documents.missing_required(build_project) == []
    statuses = {s.kind: s for s in services.documents.input_status(build_project)}
    assert statuses[DocumentKind.STAFFING_PLAN].satisfied is True  # 선택 입력은 없어도 충족


def test_mode_specific_kind_rejected(
    services: Services, proposal_project: Project, build_project: Project
) -> None:
    with pytest.raises(ValidationError):
        services.documents.register_upload(
            proposal_project, kind=DocumentKind.WBS, file_name="w.xlsx", data=b"x"
        )
    with pytest.raises(ValidationError):
        services.documents.register_upload(
            build_project, kind=DocumentKind.RFP, file_name="r.pdf", data=b"x"
        )


def test_bad_format_and_empty_file(services: Services, proposal_project: Project) -> None:
    with pytest.raises(IngestError) as info:
        services.documents.register_upload(
            proposal_project, kind=DocumentKind.RFP, file_name="rfp.xyz", data=b"x"
        )
    assert "변환 후 업로드" in info.value.resolution
    # .hwp/.doc는 업로드는 받고 추출 단계에서 '지원하지 않음 + 변환 방법'을 안내한다
    doc = services.documents.register_upload(
        proposal_project, kind=DocumentKind.RFP, file_name="rfp.hwp", data=b"x"
    )
    assert doc.file_name == "rfp.hwp"
    with pytest.raises(IngestError):
        services.documents.register_upload(
            proposal_project, kind=DocumentKind.RFP, file_name="rfp.pdf", data=b""
        )
