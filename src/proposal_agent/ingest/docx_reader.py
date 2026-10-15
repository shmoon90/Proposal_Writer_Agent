"""DOCX 리더 (python-docx).

본문 순서대로 문단과 표를 읽는다. 제목은 스타일(Heading N / 제목 N / Title)과 번호 패턴으로 감지한다.
DOCX는 페이지 번호를 신뢰성 있게 알 수 없으므로 ``page=None``으로 두고 섹션·문단·표 위치만 기록한다.
"""

from __future__ import annotations

from typing import Any

from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.base import BlockBuilder, ReaderResult
from proposal_agent.models import (
    BlockLocation,
    BlockType,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    PageStat,
)

log = get_logger("ingest.docx")


def _style_hint(paragraph: Any) -> str | None:
    try:
        name = (paragraph.style.name or "").lower()
    except Exception:
        name = ""
    if name == "title" or name == "제목":
        return "title"
    if name.startswith("heading") or name.startswith("제목 "):
        digits = "".join(ch for ch in name if ch.isdigit())
        return f"heading{digits or ''}"
    if name.startswith("toc"):
        return "toc"
    if "list" in name or "목록" in name:
        return "list"
    try:
        if paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
            return "list"
    except Exception:
        pass
    return None


def _table_cells(table: Any) -> list[list[str]]:
    cells: list[list[str]] = []
    for row in table.rows:
        out_row: list[str] = []
        prev = None
        for cell in row.cells:
            # 병합 셀은 같은 객체가 반복됨 → 중복 제거
            if prev is not None and cell._tc is prev:
                continue
            prev = cell._tc
            out_row.append(" ".join(cell.text.split()))
        cells.append(out_row)
    return cells


def read_docx(data: bytes, *, project_id: str, document_id: str, file_name: str) -> ReaderResult:
    result = ReaderResult(
        file_format=FileFormat.DOCX, status=ExtractionStatus.SUCCESS, unit_label="paragraph"
    )
    try:
        import io

        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "python-docx가 설치되지 않았습니다.",
            "cause": str(exc),
            "resolution": "pip install python-docx",
        }
        return result

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "DOCX를 열 수 없습니다 (손상되었거나 DOCX가 아님).",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "Word에서 '다른 이름으로 저장'으로 .docx를 다시 만들거나 PDF로 변환해 업로드하십시오. 암호화된 문서는 암호를 해제하십시오.",
        }
        return result

    builder = BlockBuilder(project_id, document_id, file_name, FileFormat.DOCX)
    body = doc.element.body
    table_index = 0
    units = 0
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = para.text
            if not text.strip():
                continue
            hint = _style_hint(para)
            idx = builder.next_paragraph_index()
            if hint == "toc":
                builder.add(text, BlockType.TOC, location=BlockLocation(paragraph_index=idx))
            else:
                builder.add_text(text, location=BlockLocation(paragraph_index=idx), style_hint=hint)
            units += 1
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            try:
                cells = _table_cells(table)
            except Exception as exc:
                result.warnings.append(
                    f"표 {table_index + 1} 추출 실패: {type(exc).__name__}: {exc}"
                )
                result.status = ExtractionStatus.PARTIAL
                table_index += 1
                continue
            builder.add_table(cells, location=BlockLocation(table_index=table_index))
            table_index += 1
            units += 1

    # 머리글/바닥글은 요구사항 원문이 아니므로 제외. 섹션 수만 참고 정보로 기록.
    result.page_count = None
    result.page_stats = [
        PageStat(
            page=0,
            method=ExtractionMethod.TEXT,
            char_count=sum(len(b.text) for b in builder.blocks),
        )
    ]
    result.blocks = builder.blocks
    result.warnings.append("DOCX는 페이지 번호를 확인할 수 없어 섹션·문단·표 위치만 기록합니다.")
    if not result.blocks:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "DOCX에서 텍스트를 찾지 못했습니다.",
            "cause": "본문 문단·표 없음 (이미지만 포함되었을 수 있음)",
            "resolution": "텍스트가 포함된 문서인지 확인하거나 PDF로 변환해 OCR을 적용하십시오.",
        }
    return result
