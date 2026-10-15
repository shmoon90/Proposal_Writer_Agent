"""문서 리더 공통: 결과 구조, 제목 감지, 블록 생성 헬퍼."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from proposal_agent.models import (
    BlockLocation,
    BlockType,
    ExtractedBlock,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    PageStat,
)

# 번호 체계 기반 제목 감지: "1.", "1.1", "1.1.1", "제1장", "제 2 절", "가.", "Ⅱ.", "II.", "[별첨 1]"
_HEADING_RE = re.compile(
    r"^\s*("
    r"제\s*\d+\s*(장|절|조|항|편)|"
    r"\d+(\.\d+){0,3}\.?\s|"
    r"[가-힣]\.\s|"
    r"[IVXⅠ-Ⅻ]+\.\s|"
    r"\[?(별첨|별표|부록|첨부)\s*\d*\]?"
    r")"
)
_TOC_RE = re.compile(r"^\s*(목\s*차|차\s*례|table of contents)\s*$", re.IGNORECASE)
_TOC_LINE_RE = re.compile(r".+(\.{3,}|…+|\s{3,})\s*\d+\s*$")
_APPENDIX_RE = re.compile(r"^\s*\[?(별첨|별표|부록|첨부)")
_LIST_RE = re.compile(r"^\s*([-•·▪◦※○●■□]|\(?\d+\)|\d+\)|[가-힣]\)|[a-zA-Z][.)])\s+")

MAX_HEADING_CHARS = 80


def looks_like_heading(text: str) -> bool:
    t = text.strip()
    return (
        0 < len(t) <= MAX_HEADING_CHARS
        and bool(_HEADING_RE.match(t))
        and not t.endswith(("다.", "."))
    )


def looks_like_toc_title(text: str) -> bool:
    return bool(_TOC_RE.match(text.strip()))


def looks_like_toc_line(text: str) -> bool:
    return bool(_TOC_LINE_RE.match(text.strip()))


def looks_like_appendix(text: str) -> bool:
    return bool(_APPENDIX_RE.match(text.strip()))


def looks_like_list_item(text: str) -> bool:
    return bool(_LIST_RE.match(text))


def heading_level(text: str) -> int:
    t = text.strip()
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", t)
    if m:
        return min(m.group(1).count(".") + 1, 4)
    if re.match(r"^제\s*\d+\s*장", t):
        return 1
    if re.match(r"^제\s*\d+\s*(절|조)", t):
        return 2
    if re.match(r"^[가-힣]\.\s", t):
        return 3
    return 2


@dataclass
class SectionTracker:
    """현재 섹션 경로(상위 제목들)를 유지한다."""

    stack: list[tuple[int, str]] = field(default_factory=list)

    def push(self, level: int, title: str) -> None:
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, title.strip()[:MAX_HEADING_CHARS]))

    @property
    def path(self) -> str | None:
        return " > ".join(t for _, t in self.stack) if self.stack else None


@dataclass
class ReaderResult:
    file_format: FileFormat
    status: ExtractionStatus
    blocks: list[ExtractedBlock] = field(default_factory=list)
    page_count: int | None = None
    unit_label: str = "page"
    page_stats: list[PageStat] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: dict[str, str] | None = None
    ocr_engine: str | None = None

    @property
    def ocr_pages(self) -> int:
        return sum(1 for p in self.page_stats if p.method == ExtractionMethod.OCR)

    @property
    def text_pages(self) -> int:
        return sum(
            1 for p in self.page_stats if p.method == ExtractionMethod.TEXT and p.char_count > 0
        )

    @property
    def empty_pages(self) -> int:
        return sum(1 for p in self.page_stats if p.char_count == 0)


class BlockBuilder:
    """순서·섹션을 관리하며 ExtractedBlock을 만든다."""

    def __init__(
        self, project_id: str, document_id: str, file_name: str, file_format: FileFormat
    ) -> None:
        self._project_id = project_id
        self._document_id = document_id
        self._file_name = file_name
        self._file_format = file_format
        self._order = 0
        self.sections = SectionTracker()
        self.blocks: list[ExtractedBlock] = []
        self._paragraph_index = 0
        self._in_toc = False

    def next_paragraph_index(self) -> int:
        idx = self._paragraph_index
        self._paragraph_index += 1
        return idx

    def add(
        self,
        text: str,
        block_type: BlockType,
        *,
        location: BlockLocation | None = None,
        method: ExtractionMethod = ExtractionMethod.TEXT,
        confidence: float = 1.0,
        needs_review: bool = False,
        review_reason: str | None = None,
        heading_level: int | None = None,
        table_cells: list[list[str]] | None = None,
    ) -> ExtractedBlock | None:
        text = text.strip()
        if not text:
            return None
        loc = location or BlockLocation()
        if loc.section is None:
            loc.section = self.sections.path
        block = ExtractedBlock(
            project_id=self._project_id,
            source_document_id=self._document_id,
            file_name=self._file_name,
            file_format=self._file_format,
            order=self._order,
            block_type=block_type,
            text=text,
            location=loc,
            extraction_method=method,
            confidence=confidence,
            needs_review=needs_review,
            review_reason=review_reason,
            heading_level=heading_level,
            table_cells=table_cells,
        )
        self._order += 1
        self.blocks.append(block)
        return block

    def add_text(
        self,
        text: str,
        *,
        location: BlockLocation | None = None,
        style_hint: str | None = None,
        method: ExtractionMethod = ExtractionMethod.TEXT,
        confidence: float = 1.0,
    ) -> ExtractedBlock | None:
        """스타일 힌트와 텍스트 패턴으로 블록 종류를 정해 추가한다."""
        t = text.strip()
        if not t:
            return None
        hint = (style_hint or "").lower()
        if hint == "title":
            self._in_toc = False
            return self.add(
                t, BlockType.TITLE, location=location, method=method, confidence=confidence
            )
        if looks_like_toc_title(t):
            self._in_toc = True
            return self.add(
                t, BlockType.TOC, location=location, method=method, confidence=confidence
            )
        if self._in_toc and looks_like_toc_line(t):
            return self.add(
                t, BlockType.TOC, location=location, method=method, confidence=confidence
            )
        level: int | None = None
        if hint.startswith("heading"):
            digits = "".join(ch for ch in hint if ch.isdigit())
            level = int(digits) if digits else heading_level(t)
        elif looks_like_heading(t):
            level = heading_level(t)
        if level is not None:
            self._in_toc = False
            self.sections.push(level, t)
            btype = BlockType.APPENDIX if looks_like_appendix(t) else BlockType.HEADING
            loc = location or BlockLocation()
            loc.section = self.sections.path
            return self.add(
                t, btype, location=loc, method=method, confidence=confidence, heading_level=level
            )
        if hint.startswith("list") or looks_like_list_item(t):
            return self.add(
                t, BlockType.LIST_ITEM, location=location, method=method, confidence=confidence
            )
        return self.add(
            t, BlockType.PARAGRAPH, location=location, method=method, confidence=confidence
        )

    def add_table(
        self,
        cells: list[list[str]],
        *,
        location: BlockLocation | None = None,
        method: ExtractionMethod = ExtractionMethod.TEXT,
        confidence: float = 1.0,
    ) -> ExtractedBlock | None:
        clean = [[(c or "").strip() for c in row] for row in cells]
        if not any(any(row) for row in clean):
            return None
        lines = [" | ".join(row) for row in clean if any(row)]
        return self.add(
            "\n".join(lines),
            BlockType.TABLE,
            location=location,
            method=method,
            confidence=confidence,
            table_cells=clean,
        )


def render_table_markdown(cells: list[list[str]]) -> str:
    if not cells:
        return ""
    width = max(len(r) for r in cells)
    rows = [r + [""] * (width - len(r)) for r in cells]
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "---|" * width
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([head, sep, *body])
