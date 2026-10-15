"""문서 추출 서비스와 Gate 0(문서 추출 품질) 판정.

흐름: SourceDocument → 원본 바이트 로드 → 형식 판별 → 리더 실행 → 블록·실행 기록 저장(DB + workspace JSON)
→ Gate 0 평가(코드). 재실행은 새 ExtractionRun을 만들고 이전 블록은 보존한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from proposal_agent.config.errors import IngestError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.ingest.base import ReaderResult
from proposal_agent.ingest.docx_reader import read_docx
from proposal_agent.ingest.ocr import OcrEngine, build_ocr_engine
from proposal_agent.ingest.pdf_reader import read_pdf
from proposal_agent.ingest.txt_reader import read_txt
from proposal_agent.models import (
    ActorKind,
    ExtractedBlock,
    ExtractionMethod,
    ExtractionRun,
    ExtractionStatus,
    FileFormat,
    GateEvaluation,
    GateStatus,
    Project,
    SourceDocument,
)
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("ingest.service")

GATE0_KEY = "gate0"

_UNSUPPORTED_HINTS: dict[str, str] = {
    ".doc": "구형 Word(.doc) 형식은 직접 지원하지 않습니다. Word에서 .docx 또는 PDF로 저장한 뒤 업로드하십시오.",
    ".hwp": "한글(.hwp) 형식은 직접 지원하지 않습니다. 한글에서 PDF로 저장한 뒤 업로드하십시오.",
    ".hwpx": "한글(.hwpx) 형식은 직접 지원하지 않습니다. 한글에서 PDF로 저장한 뒤 업로드하십시오.",
    ".rtf": "RTF 형식은 직접 지원하지 않습니다. Word에서 .docx로 저장한 뒤 업로드하십시오.",
    ".xlsx": "Excel 문서는 RFP 본문 추출 대상이 아닙니다 (구축 단계 기준 문서는 별도 파서).",
    ".pptx": "PowerPoint 문서는 직접 지원하지 않습니다. PDF로 저장한 뒤 업로드하십시오.",
    ".zip": "압축 파일은 직접 지원하지 않습니다. 압축을 풀고 개별 문서를 업로드하십시오.",
}


def detect_format(file_name: str, data: bytes) -> tuple[FileFormat, str | None]:
    """확장자와 매직 바이트로 형식을 판별한다. 지원하지 않으면 (UNSUPPORTED, 안내문)."""
    suffix = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    head = data[:8]
    if suffix == ".pdf" or head.startswith(b"%PDF"):
        if not head.startswith(b"%PDF"):
            return (
                FileFormat.PDF,
                "PDF 시그니처가 없습니다. 손상되었거나 확장자만 .pdf일 수 있습니다.",
            )
        return FileFormat.PDF, None
    if suffix == ".docx":
        if not head.startswith(b"PK"):
            return (
                FileFormat.DOCX,
                "DOCX(zip) 시그니처가 없습니다. 손상되었거나 .doc를 이름만 바꾼 파일일 수 있습니다.",
            )
        return FileFormat.DOCX, None
    if suffix in (".txt", ".md", ""):
        return FileFormat.TXT, None
    hint = _UNSUPPORTED_HINTS.get(
        suffix, f"지원하지 않는 형식({suffix})입니다. PDF, DOCX, TXT로 변환해 업로드하십시오."
    )
    return FileFormat.UNSUPPORTED, hint


@dataclass(frozen=True)
class ExtractionOutcome:
    run: ExtractionRun
    blocks: list[ExtractedBlock]


class ExtractionService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        settings: Settings,
        audit: AuditService,
        ocr: OcrEngine | None = None,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._ocr = (
            ocr if ocr is not None else build_ocr_engine(settings.ocr_engine, settings.ocr_lang)
        )

    @property
    def ocr(self) -> OcrEngine:
        return self._ocr

    # --- 추출 ------------------------------------------------------------------------
    def extract_document(
        self, project: Project, document: SourceDocument, *, actor: str = "system"
    ) -> ExtractionOutcome:
        path = self._paths.resolve_output(document.stored_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise IngestError(
                "원본 파일을 읽을 수 없습니다.",
                cause=f"{path}: {exc}",
                resolution="01_RFP_Original 폴더의 파일이 이동·삭제되지 않았는지 확인하십시오.",
            ) from exc

        fmt, hint = detect_format(document.file_name, data)
        if fmt == FileFormat.UNSUPPORTED:
            result = ReaderResult(
                file_format=FileFormat.UNSUPPORTED,
                status=ExtractionStatus.UNSUPPORTED,
                error={
                    "message": "지원하지 않는 문서 형식입니다.",
                    "cause": document.file_name,
                    "resolution": hint or "",
                },
            )
        else:
            result = self._read(fmt, data, project, document)
            if hint and result.status in (ExtractionStatus.FAILED, ExtractionStatus.PARTIAL):
                result.warnings.insert(0, hint)

        run = ExtractionRun(
            project_id=project.id,
            source_document_id=document.id,
            file_name=document.file_name,
            file_format=result.file_format,
            status=result.status,
            page_count=result.page_count,
            unit_label=result.unit_label,
            text_pages=result.text_pages,
            ocr_pages=result.ocr_pages,
            empty_pages=result.empty_pages,
            block_count=len(result.blocks),
            table_count=sum(1 for b in result.blocks if b.block_type.value == "table"),
            low_confidence_blocks=sum(1 for b in result.blocks if b.needs_review),
            warnings=list(result.warnings),
            error=dict(result.error) if result.error else None,
            page_stats=list(result.page_stats),
            ocr_engine=result.ocr_engine,
            created_by=actor,
        )
        for b in result.blocks:
            b.extraction_run_id = run.id
        run.blocks_path = self._write_blocks_json(project, run, result.blocks)
        self._repos.extraction_runs.insert(run)
        if result.blocks:
            self._repos.blocks.insert_many(result.blocks)

        # 문서 메타 갱신
        document.page_count = result.page_count
        if result.ocr_pages and result.text_pages:
            document.extraction_method = ExtractionMethod.MIXED
        elif result.ocr_pages:
            document.extraction_method = ExtractionMethod.OCR
        elif result.status != ExtractionStatus.UNSUPPORTED:
            document.extraction_method = ExtractionMethod.TEXT
        document.extracted_text_path = run.blocks_path
        self._repos.documents.update(document)

        payload = {
            "run_id": run.id,
            "status": str(run.status),
            "blocks": run.block_count,
            "ocr_pages": run.ocr_pages,
            "warnings": len(run.warnings),
        }
        if run.status in (ExtractionStatus.FAILED, ExtractionStatus.UNSUPPORTED):
            err = run.error or {}
            self._audit.record_error(
                project.id,
                "document.extraction_failed",
                IngestError(
                    err.get("message", "추출 실패"),
                    cause=err.get("cause"),
                    resolution=err.get("resolution"),
                ),
                actor=actor,
                entity_type="SourceDocument",
                entity_id=document.id,
                payload=payload,
            )
        else:
            self._audit.record(
                project.id,
                "document.extracted",
                actor=actor,
                actor_kind=ActorKind.SYSTEM,
                entity_type="SourceDocument",
                entity_id=document.id,
                payload=payload,
            )
        log.info(
            "추출 %s %s → %s (%d blocks, ocr=%d)",
            document.id,
            document.file_name,
            run.status,
            run.block_count,
            run.ocr_pages,
        )
        return ExtractionOutcome(run=run, blocks=result.blocks)

    def extract_all(
        self, project: Project, *, actor: str = "system", only_missing: bool = False
    ) -> list[ExtractionOutcome]:
        outcomes: list[ExtractionOutcome] = []
        latest = self._repos.extraction_runs.latest_by_document(project.id)
        for doc in self._repos.documents.find(project.id):
            if only_missing and doc.id in latest and latest[doc.id].ok:
                continue
            outcomes.append(self.extract_document(project, doc, actor=actor))
        return outcomes

    def _read(
        self, fmt: FileFormat, data: bytes, project: Project, document: SourceDocument
    ) -> ReaderResult:
        kwargs = {
            "project_id": project.id,
            "document_id": document.id,
            "file_name": document.file_name,
        }
        try:
            if fmt == FileFormat.PDF:
                return read_pdf(
                    data,
                    ocr=self._ocr,
                    ocr_min_chars=self._settings.ocr_min_chars_per_page,
                    ocr_review_threshold=self._settings.ocr_review_threshold,
                    **kwargs,
                )
            if fmt == FileFormat.DOCX:
                return read_docx(data, **kwargs)
            return read_txt(data, **kwargs)
        except Exception as exc:  # 리더 내부의 예기치 않은 오류도 실패 기록으로 변환
            log.exception("리더 예외 %s", document.file_name)
            return ReaderResult(
                file_format=fmt,
                status=ExtractionStatus.FAILED,
                error={
                    "message": "문서 추출 중 예기치 않은 오류가 발생했습니다.",
                    "cause": f"{type(exc).__name__}: {exc}",
                    "resolution": "파일을 다른 형식으로 변환해 다시 시도하고, 로그를 확인하십시오.",
                },
            )

    def _write_blocks_json(
        self, project: Project, run: ExtractionRun, blocks: list[ExtractedBlock]
    ) -> str:
        ws = self._paths.ensure_workspace(project.workspace_dir or project.id)
        target = ws / "chunks" / f"{run.source_document_id}_{run.id}.json"
        payload = {
            "run": run.model_dump(mode="json"),
            "blocks": [b.model_dump(mode="json") for b in blocks],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return target.relative_to(self._paths.workspace_root).as_posix()

    # --- 조회 ------------------------------------------------------------------------
    def latest_runs(self, project: Project) -> dict[str, ExtractionRun]:
        return self._repos.extraction_runs.latest_by_document(project.id)

    def current_blocks(
        self, project: Project, *, required_only: bool = False
    ) -> list[ExtractedBlock]:
        """각 문서의 최신 성공 실행 블록을 문서 순서대로 합친다."""
        out: list[ExtractedBlock] = []
        runs = self.latest_runs(project)
        for doc in self._repos.documents.find(project.id):
            if required_only and not doc.is_required_input:
                continue
            run = runs.get(doc.id)
            if run and run.ok:
                out.extend(self._repos.blocks.for_run(project.id, run.id))
        return out

    # --- Gate 0 ----------------------------------------------------------------------
    def evaluate_gate0(self, project: Project, *, step_run_id: str | None = None) -> GateEvaluation:
        """문서 추출 품질 게이트. 코드가 결정하며 LLM 판단을 쓰지 않는다."""
        docs = self._repos.documents.find(project.id)
        runs = self.latest_runs(project)
        reasons: list[str] = []
        status = GateStatus.PASS
        metrics: dict[str, object] = {"documents": len(docs)}

        required = [d for d in docs if d.is_required_input]
        if not required:
            return self._save_gate(
                project,
                GateStatus.FAIL,
                ["필수 입력 문서가 등록되지 않았습니다."],
                metrics,
                step_run_id,
            )

        ocr_pages = 0
        total_pages = 0
        review_blocks = 0
        for doc in required:
            run = runs.get(doc.id)
            if run is None:
                status = GateStatus.FAIL
                reasons.append(f"{doc.file_name}: 아직 추출하지 않았습니다.")
                continue
            if run.status in (ExtractionStatus.FAILED, ExtractionStatus.UNSUPPORTED):
                status = GateStatus.FAIL
                reasons.append(
                    f"{doc.file_name}: 추출 실패 — {(run.error or {}).get('message', '')}"
                )
                continue
            if run.block_count == 0:
                status = GateStatus.FAIL
                reasons.append(f"{doc.file_name}: 추출된 텍스트가 없습니다.")
                continue
            total_pages += run.page_count or 0
            ocr_pages += run.ocr_pages
            review_blocks += run.low_confidence_blocks
            if run.status == ExtractionStatus.PARTIAL and status != GateStatus.FAIL:
                status = GateStatus.NEEDS_HUMAN_REVIEW
                reasons.append(
                    f"{doc.file_name}: 일부 페이지 추출 품질이 낮습니다 ({'; '.join(run.warnings[:2])})."
                )
            if run.low_confidence_blocks and status != GateStatus.FAIL:
                status = GateStatus.NEEDS_HUMAN_REVIEW
                reasons.append(
                    f"{doc.file_name}: 검토 필요 블록 {run.low_confidence_blocks}건 (OCR 저신뢰 등)."
                )
            if (
                run.page_count
                and run.empty_pages
                and run.empty_pages / run.page_count > 0.3
                and status != GateStatus.FAIL
            ):
                status = GateStatus.NEEDS_HUMAN_REVIEW
                reasons.append(
                    f"{doc.file_name}: 빈 페이지 비율이 높습니다 ({run.empty_pages}/{run.page_count})."
                )
        metrics.update(
            {"total_pages": total_pages, "ocr_pages": ocr_pages, "review_blocks": review_blocks}
        )
        if (
            ocr_pages
            and total_pages
            and ocr_pages / total_pages >= 0.5
            and status == GateStatus.PASS
        ):
            status = GateStatus.NEEDS_HUMAN_REVIEW
            reasons.append(
                f"OCR 적용 페이지 비율이 높습니다 ({ocr_pages}/{total_pages}). 인식 결과를 확인하십시오."
            )
        if status == GateStatus.PASS:
            reasons.append("모든 필수 문서가 정상 추출되었습니다.")
        return self._save_gate(project, status, reasons, metrics, step_run_id)

    def _save_gate(
        self,
        project: Project,
        status: GateStatus,
        reasons: list[str],
        metrics: dict[str, object],
        step_run_id: str | None,
    ) -> GateEvaluation:
        ev = GateEvaluation(
            project_id=project.id,
            gate_key=GATE0_KEY,
            status=status,
            reasons=reasons,
            metrics=metrics,
            evaluated_by="code:ingest.evaluate_gate0",
            step_run_id=step_run_id,
        )
        self._repos.gate_evaluations.insert(ev)
        self._audit.record(
            project.id,
            "gate.evaluated",
            entity_type="GateEvaluation",
            entity_id=ev.id,
            payload={"gate": GATE0_KEY, "status": str(status), "reasons": reasons},
        )
        return ev
