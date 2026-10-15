"""PDF 리더 (pdfplumber + pypdf + pypdfium2).

PyMuPDF는 이 개발 PC의 애플리케이션 제어 정책이 DLL을 차단해 사용할 수 없다(RISK R-19). 대신:
- 텍스트·표: ``pdfplumber``(순수 Python, pdfminer.six 기반)
- 암호화·손상 판별: ``pypdf``
- 스캔 페이지 렌더링(OCR 입력): ``pypdfium2``. 렌더링이 불가능하면 ``pypdf``로 페이지 내장 이미지를 꺼내 OCR.

텍스트가 거의 없는 페이지는 스캔 페이지로 보고 OCR을 시도한다. OCR 엔진이 없으면 경고와 함께
검토 필요로 표시하고 내용을 추측하지 않는다.
"""

from __future__ import annotations

import io
import re
from typing import Any

from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.base import (
    BlockBuilder,
    ReaderResult,
    looks_like_heading,
    looks_like_list_item,
)
from proposal_agent.ingest.ocr import OcrEngine
from proposal_agent.models import (
    BlockLocation,
    BlockType,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    PageStat,
)

log = get_logger("ingest.pdf")

OCR_RENDER_DPI = 200
_SENTENCE_END = re.compile(r"[.。!?:;다요음함됨임]\s*$|[\)\]」』”]\s*$")


def _probe(data: bytes) -> dict[str, Any] | None:
    """pypdf로 암호화·손상 여부를 먼저 확인한다. 문제 없으면 None."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover
        return {
            "message": "pypdf가 설치되지 않았습니다.",
            "cause": str(exc),
            "resolution": "pip install pypdf",
        }
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # 빈 암호로 열리는 '소유자 암호만' 문서는 허용
            try:
                if reader.decrypt("") == 0:
                    raise PdfReadError("password required")
            except Exception:
                return {
                    "message": "암호로 보호된 PDF입니다.",
                    "cause": "is_encrypted=True (사용자 암호 필요)",
                    "resolution": "암호를 해제한 PDF를 업로드하십시오. 이 시스템은 암호를 입력하지 않습니다.",
                }
        _ = len(reader.pages)
    except PdfReadError as exc:
        return {
            "message": "PDF를 열 수 없습니다 (손상되었거나 PDF가 아님).",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "원본 프로그램에서 PDF를 다시 내보내거나 다른 파일을 업로드하십시오.",
        }
    except Exception as exc:
        return {
            "message": "PDF를 열 수 없습니다.",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "원본 프로그램에서 PDF를 다시 내보내거나 다른 파일을 업로드하십시오.",
        }
    return None


def _group_paragraphs(lines: list[str]) -> list[str]:
    """PDF 줄바꿈을 문단으로 합친다. 제목·목록·문장 끝에서 끊는다."""
    paragraphs: list[str] = []
    buf: list[str] = []
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        if looks_like_heading(line) or looks_like_list_item(line):
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            buf.append(line)
            if looks_like_heading(line):
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        buf.append(line)
        if _SENTENCE_END.search(line):
            paragraphs.append(" ".join(buf))
            buf = []
    if buf:
        paragraphs.append(" ".join(buf))
    return paragraphs


def _render_page_image(data: bytes, page_index: int) -> Any:
    """pypdfium2로 페이지를 RGB numpy 배열로 렌더링한다. 실패 시 pypdf 내장 이미지로 대체."""
    import numpy as np

    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            page = pdf[page_index]
            bitmap = page.render(scale=OCR_RENDER_DPI / 72)
            pil = bitmap.to_pil().convert("RGB")
        finally:
            pdf.close()
        return np.array(pil)
    except Exception as exc:
        log.warning("pypdfium2 렌더링 실패 p.%d, 내장 이미지로 대체: %s", page_index + 1, exc)
    from PIL import Image
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    page = reader.pages[page_index]
    images = list(page.images)
    if not images:
        raise RuntimeError("페이지에 내장 이미지가 없어 OCR 입력을 만들 수 없습니다.")
    largest = max(images, key=lambda im: len(im.data))
    pil = Image.open(io.BytesIO(largest.data)).convert("RGB")
    return np.array(pil)


def read_pdf(
    data: bytes,
    *,
    project_id: str,
    document_id: str,
    file_name: str,
    ocr: OcrEngine | None,
    ocr_min_chars: int,
    ocr_review_threshold: float,
) -> ReaderResult:
    result = ReaderResult(file_format=FileFormat.PDF, status=ExtractionStatus.SUCCESS)
    problem = _probe(data)
    if problem is not None:
        result.status = ExtractionStatus.FAILED
        result.error = problem
        return result

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "pdfplumber가 설치되지 않았습니다.",
            "cause": str(exc),
            "resolution": "pip install pdfplumber",
        }
        return result

    builder = BlockBuilder(project_id, document_id, file_name, FileFormat.PDF)
    ocr_engine_name: str | None = None
    ocr_unavailable_reported = False

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "PDF 구조를 해석할 수 없습니다.",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "원본 프로그램에서 PDF를 다시 내보내거나 다른 파일을 업로드하십시오.",
        }
        return result

    with pdf:
        result.page_count = len(pdf.pages)
        for page in pdf.pages:
            page_no = page.page_number
            loc_base = {"page": page_no}
            try:
                tables_found = page.find_tables()
                table_cells: list[list[list[str]]] = []
                for t in tables_found:
                    rows = t.extract()
                    cells = [[(c if isinstance(c, str) else "") for c in row] for row in rows]
                    if any(any(c.strip() for c in row) for row in cells):
                        table_cells.append(cells)
                bboxes = [t.bbox for t in tables_found]

                def outside_tables(
                    obj: dict[str, Any], _b: list[tuple[float, float, float, float]] = bboxes
                ) -> bool:
                    x, top = obj.get("x0", 0), obj.get("top", 0)
                    return not any(
                        bx0 <= x <= bx1 and by0 <= top <= by1 for (bx0, by0, bx1, by1) in _b
                    )

                text_page = page.filter(outside_tables) if bboxes else page
                text = text_page.extract_text() or ""
            except Exception as exc:
                result.warnings.append(
                    f"p.{page_no}: 텍스트 추출 실패 ({type(exc).__name__}: {exc})"
                )
                result.page_stats.append(
                    PageStat(
                        page=page_no,
                        method=ExtractionMethod.TEXT,
                        char_count=0,
                        warning="추출 실패",
                    )
                )
                result.status = ExtractionStatus.PARTIAL
                continue

            char_count = len(text.strip()) + sum(
                len(c) for tb in table_cells for row in tb for c in row
            )
            if char_count >= ocr_min_chars:
                for para in _group_paragraphs(text.splitlines()):
                    builder.add_text(
                        para,
                        location=BlockLocation(
                            **loc_base, paragraph_index=builder.next_paragraph_index()
                        ),
                    )
                for ti, cells in enumerate(table_cells):
                    builder.add_table(cells, location=BlockLocation(**loc_base, table_index=ti))
                result.page_stats.append(
                    PageStat(page=page_no, method=ExtractionMethod.TEXT, char_count=char_count)
                )
                continue

            has_images = bool(page.images)
            if ocr is None or not ocr.available():
                reason = "OCR 엔진 사용 불가" if ocr is not None else "OCR 비활성화"
                if not ocr_unavailable_reported:
                    result.warnings.append(
                        f"{reason}: 스캔 페이지를 인식하지 못했습니다. OCR 엔진을 설정한 뒤 재처리하십시오."
                    )
                    ocr_unavailable_reported = True
                result.page_stats.append(
                    PageStat(
                        page=page_no,
                        method=ExtractionMethod.TEXT,
                        char_count=char_count,
                        confidence=0.0,
                        warning="스캔 페이지 추정, OCR 미적용" if has_images else "텍스트 없음",
                    )
                )
                if has_images:
                    builder.add(
                        f"[p.{page_no}: 스캔 이미지 페이지 — OCR 미적용]",
                        BlockType.PAGE_TEXT,
                        location=BlockLocation(**loc_base),
                        confidence=0.0,
                        needs_review=True,
                        review_reason=reason,
                    )
                result.status = ExtractionStatus.PARTIAL
                continue

            try:
                image = _render_page_image(data, page_no - 1)
                ocr_result = ocr.recognize(image)
                ocr_engine_name = ocr.name
            except Exception as exc:
                result.warnings.append(f"p.{page_no}: OCR 실패 ({type(exc).__name__}: {exc})")
                result.page_stats.append(
                    PageStat(
                        page=page_no,
                        method=ExtractionMethod.OCR,
                        char_count=0,
                        confidence=0.0,
                        warning="OCR 실패",
                    )
                )
                result.status = ExtractionStatus.PARTIAL
                continue

            ocr_text = ocr_result.text
            conf = ocr_result.confidence
            low = conf < ocr_review_threshold
            if ocr_text.strip():
                for para in _group_paragraphs(ocr_text.splitlines()):
                    block = builder.add_text(
                        para,
                        location=BlockLocation(
                            **loc_base, paragraph_index=builder.next_paragraph_index()
                        ),
                        method=ExtractionMethod.OCR,
                        confidence=round(conf, 3),
                    )
                    if block is not None and low:
                        block.needs_review = True
                        block.review_reason = f"OCR 신뢰도 낮음 ({conf:.2f})"
            else:
                result.warnings.append(f"p.{page_no}: OCR 결과 없음")
            result.page_stats.append(
                PageStat(
                    page=page_no,
                    method=ExtractionMethod.OCR,
                    char_count=len(ocr_text),
                    confidence=round(conf, 3),
                    warning=f"OCR 신뢰도 낮음 ({conf:.2f})" if low else None,
                )
            )
            if low:
                result.status = ExtractionStatus.PARTIAL

    result.blocks = builder.blocks
    result.ocr_engine = ocr_engine_name
    if not result.blocks:
        result.status = (
            ExtractionStatus.FAILED if result.status == ExtractionStatus.SUCCESS else result.status
        )
        result.warnings.append("추출된 텍스트가 없습니다.")
        if result.status == ExtractionStatus.FAILED:
            result.error = {
                "message": "PDF에서 텍스트를 추출하지 못했습니다.",
                "cause": "텍스트 레이어 없음, OCR 결과 없음",
                "resolution": "OCR 엔진 설정을 확인하거나 텍스트가 포함된 PDF로 다시 내보내십시오.",
            }
    return result
