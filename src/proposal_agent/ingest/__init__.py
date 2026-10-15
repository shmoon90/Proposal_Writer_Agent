"""문서 입력 및 추출 (PDF/DOCX/TXT, OCR, 청크, Gate 0)."""

from proposal_agent.ingest.chunker import Chunk, build_chunks, render_block
from proposal_agent.ingest.ocr import NullOcrEngine, OcrEngine, RapidOcrEngine, build_ocr_engine
from proposal_agent.ingest.service import (
    GATE0_KEY,
    ExtractionOutcome,
    ExtractionService,
    detect_format,
)

__all__ = [
    "GATE0_KEY",
    "Chunk",
    "ExtractionOutcome",
    "ExtractionService",
    "NullOcrEngine",
    "OcrEngine",
    "RapidOcrEngine",
    "build_chunks",
    "build_ocr_engine",
    "detect_format",
    "render_block",
]
