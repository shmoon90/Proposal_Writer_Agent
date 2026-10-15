"""문서 추출 결과 모델 (Phase 2).

- ``ExtractedBlock``: 문서에서 추출한 단위(제목·문단·목록·표 셀 등). 출처 좌표·원문·추출 방식·신뢰도·검토 필요 여부를 기록한다.
- ``ExtractionRun``: 문서 1건의 추출 실행 요약(성공/실패, 페이지 수, OCR 페이지, 경고). Gate 0 판정의 입력.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import BlockType, ExtractionMethod, ExtractionStatus, FileFormat


class BlockLocation(BaseModel):
    """확인 가능한 출처 좌표. 확인할 수 없는 값은 None (추측 금지)."""

    model_config = ConfigDict(extra="forbid")

    page: int | None = Field(default=None, description="PDF 1-base 페이지. DOCX/TXT는 None")
    section: str | None = Field(default=None, description="가장 가까운 상위 제목 경로")
    paragraph_index: int | None = Field(default=None, description="문서 내 문단 순번 (0-base)")
    table_index: int | None = None
    row: int | None = None
    col: int | None = None
    line_start: int | None = Field(default=None, description="TXT 줄 번호 (1-base)")
    line_end: int | None = None

    def label(self) -> str:
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"p.{self.page}")
        if self.section:
            parts.append(self.section)
        if self.table_index is not None:
            cell = f"표{self.table_index + 1}"
            if self.row is not None:
                cell += f" r{self.row + 1}"
            if self.col is not None:
                cell += f"c{self.col + 1}"
            parts.append(cell)
        elif self.paragraph_index is not None:
            parts.append(f"¶{self.paragraph_index + 1}")
        if self.line_start is not None:
            parts.append(f"L{self.line_start}" + (f"-{self.line_end}" if self.line_end else ""))
        return " / ".join(parts) or "(위치 미상)"


class ExtractedBlock(ProjectScoped):
    id_prefix: ClassVar[str] = "blk"

    source_document_id: str
    extraction_run_id: str = ""
    file_name: str
    file_format: FileFormat
    order: int = Field(description="문서 내 순서")
    block_type: BlockType
    text: str
    location: BlockLocation = Field(default_factory=BlockLocation)
    extraction_method: ExtractionMethod = ExtractionMethod.TEXT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    needs_review: bool = False
    review_reason: str | None = None
    heading_level: int | None = None
    table_cells: list[list[str]] | None = Field(
        default=None, description="block_type=table일 때 전체 셀"
    )

    @property
    def source_label(self) -> str:
        return f"{self.file_name} · {self.location.label()}"


class PageStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    method: ExtractionMethod
    char_count: int
    confidence: float = 1.0
    warning: str | None = None


class ExtractionRun(ProjectScoped):
    id_prefix: ClassVar[str] = "ext"

    source_document_id: str
    file_name: str
    file_format: FileFormat
    status: ExtractionStatus
    page_count: int | None = None
    unit_label: str = "page"
    text_pages: int = 0
    ocr_pages: int = 0
    empty_pages: int = 0
    block_count: int = 0
    table_count: int = 0
    low_confidence_blocks: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    page_stats: list[PageStat] = Field(default_factory=list)
    ocr_engine: str | None = None
    blocks_path: str | None = Field(default=None, description="workspace 내 블록 JSON 상대 경로")

    @property
    def ok(self) -> bool:
        return self.status in (ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL)
