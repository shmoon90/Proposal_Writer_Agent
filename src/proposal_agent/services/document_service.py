"""입력 문서(RFP, 구축 단계 기준 문서) 등록 서비스.

- 원본은 ``01_RFP_Original``에 복사하고 sha256·크기를 기록한다.
- 같은 프로젝트에 같은 해시의 문서가 있으면 중복으로 거부한다.
- 같은 파일명이 이미 있으면 ``name_1.ext`` 식으로 보존 저장한다.
- 모드별 필수 입력 문서 규칙(WORKFLOW_DESIGN.md)을 제공한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.config.errors import IngestError, StorageError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import ActorKind, DocumentKind, Project, ProjectMode, SourceDocument
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.files import FileStore, sha256_bytes
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.document")

ORIGINAL_SUBDIR = "01_RFP_Original"

ALLOWED_SUFFIXES: dict[DocumentKind, tuple[str, ...]] = {
    # .doc/.hwp/.hwpx는 업로드는 받되 추출 단계에서 "지원하지 않음 + 변환 방법"으로 안내한다.
    DocumentKind.RFP: (".pdf", ".docx", ".txt", ".md", ".doc", ".hwp", ".hwpx"),
    DocumentKind.RFP_ATTACHMENT: (
        ".pdf",
        ".docx",
        ".txt",
        ".md",
        ".doc",
        ".hwp",
        ".hwpx",
        ".xlsx",
        ".pptx",
        ".zip",
    ),
    DocumentKind.REQUIREMENT_SPEC: (".xlsx",),
    DocumentKind.TRACE_MATRIX: (".xlsx",),
    DocumentKind.WBS: (".xlsx",),
    DocumentKind.STAFFING_PLAN: (".xlsx",),
    DocumentKind.OTHER: (".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".hwp", ".zip"),
}

REQUIRED_KINDS: dict[ProjectMode, tuple[DocumentKind, ...]] = {
    ProjectMode.PROPOSAL: (DocumentKind.RFP,),
    ProjectMode.BUILD: (DocumentKind.REQUIREMENT_SPEC, DocumentKind.TRACE_MATRIX, DocumentKind.WBS),
}
OPTIONAL_KINDS: dict[ProjectMode, tuple[DocumentKind, ...]] = {
    ProjectMode.PROPOSAL: (DocumentKind.RFP_ATTACHMENT, DocumentKind.OTHER),
    ProjectMode.BUILD: (DocumentKind.STAFFING_PLAN, DocumentKind.OTHER),
}

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class InputStatus:
    kind: DocumentKind
    required: bool
    documents: tuple[SourceDocument, ...]

    @property
    def satisfied(self) -> bool:
        return not self.required or len(self.documents) > 0


class DocumentService:
    def __init__(self, repos: Repositories, files: FileStore, audit: AuditService) -> None:
        self._repos = repos
        self._files = files
        self._audit = audit

    @staticmethod
    def kinds_for(mode: ProjectMode) -> list[tuple[DocumentKind, bool]]:
        """모드별 (문서 종류, 필수 여부) 목록."""
        return [(k, True) for k in REQUIRED_KINDS[mode]] + [
            (k, False) for k in OPTIONAL_KINDS[mode]
        ]

    def register_upload(
        self,
        project: Project,
        *,
        kind: DocumentKind,
        file_name: str,
        data: bytes,
        actor: str = "user",
    ) -> SourceDocument:
        self._validate_upload(project, kind, file_name, data)
        digest = sha256_bytes(data)
        duplicates = self._repos.documents.find(project.id, sha256=digest)
        if duplicates:
            raise ValidationError(
                "같은 내용의 문서가 이미 등록되어 있습니다.",
                cause=f"sha256 일치: {duplicates[0].file_name}",
                resolution="다른 문서를 업로드하거나 기존 문서를 사용하십시오.",
            )
        try:
            stored = self._files.store_unique(project.output_dir, ORIGINAL_SUBDIR, file_name, data)
        except StorageError as exc:
            self._audit.record_error(
                project.id, "document.store_failed", exc, actor=actor, actor_kind=ActorKind.USER
            )
            raise
        doc = SourceDocument(
            project_id=project.id,
            kind=kind,
            file_name=file_name,
            stored_path=stored.relative_path,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            is_required_input=kind in REQUIRED_KINDS[project.mode],
            created_by=actor,
        )
        self._repos.documents.insert(doc)
        self._audit.record(
            project.id,
            "document.registered",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="SourceDocument",
            entity_id=doc.id,
            payload={
                "kind": str(kind),
                "file_name": file_name,
                "stored_path": stored.relative_path,
            },
        )
        log.info("문서 등록 %s %s → %s", project.id, kind, stored.relative_path)
        return doc

    def list_documents(
        self, project_id: str, kind: DocumentKind | None = None
    ) -> list[SourceDocument]:
        if kind is None:
            return self._repos.documents.find(project_id)
        return self._repos.documents.find(project_id, kind=str(kind))

    def input_status(self, project: Project) -> list[InputStatus]:
        docs = self.list_documents(project.id)
        by_kind: dict[DocumentKind, list[SourceDocument]] = {}
        for d in docs:
            by_kind.setdefault(d.kind, []).append(d)
        return [
            InputStatus(kind=k, required=req, documents=tuple(by_kind.get(k, [])))
            for k, req in self.kinds_for(project.mode)
        ]

    def missing_required(self, project: Project) -> list[DocumentKind]:
        return [s.kind for s in self.input_status(project) if not s.satisfied]

    # --- 내부 ------------------------------------------------------------------------
    def _validate_upload(
        self, project: Project, kind: DocumentKind, file_name: str, data: bytes
    ) -> None:
        allowed_kinds = {k for k, _ in self.kinds_for(project.mode)}
        if kind not in allowed_kinds:
            raise ValidationError(
                f"{project.mode.label}에서는 {kind.label} 문서를 받지 않습니다.",
                cause=f"mode={project.mode}, kind={kind}",
            )
        if not data:
            raise IngestError(
                "빈 파일입니다.", cause=file_name, resolution="내용이 있는 파일을 업로드하십시오."
            )
        if len(data) > MAX_UPLOAD_BYTES:
            raise IngestError(
                "파일이 너무 큽니다.",
                cause=f"{len(data)} bytes > {MAX_UPLOAD_BYTES}",
                resolution="200MB 이하 파일로 나누어 업로드하십시오.",
            )
        suffix = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if suffix not in ALLOWED_SUFFIXES[kind]:
            raise IngestError(
                f"{kind.label}에 허용되지 않는 형식입니다: {suffix or '(확장자 없음)'}",
                cause=file_name,
                resolution=f"허용 형식: {', '.join(ALLOWED_SUFFIXES[kind])}"
                + (
                    " (HWP/DOC는 PDF 또는 DOCX로 변환 후 업로드)"
                    if kind == DocumentKind.RFP
                    else ""
                ),
            )
