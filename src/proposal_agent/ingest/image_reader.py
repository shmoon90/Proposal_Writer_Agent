"""이미지 리더 (PNG·JPG → OCR) — 단계 2 (지시문 §0.1 입력 자료: 이미지).

스캔본·캡처 이미지를 OCR 엔진(rapidocr) 으로 읽어 줄 단위 문단 블록을 만든다. 평균 신뢰도가 기준보다 낮으면
``needs_review`` 로 표시하고, OCR 엔진이 없으면 실패(사유·조치) 로 기록한다 — 없는 텍스트를 만들지 않는다.
"""

from __future__ import annotations

import io

from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.base import BlockBuilder, ReaderResult
from proposal_agent.ingest.ocr import OcrEngine
from proposal_agent.models import (
    BlockLocation,
    BlockType,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    PageStat,
)

log = get_logger("ingest.image")


def read_image(
    data: bytes,
    *,
    ocr: OcrEngine | None,
    ocr_review_threshold: float,
    project_id: str,
    document_id: str,
    file_name: str,
) -> ReaderResult:
    result = ReaderResult(
        file_format=FileFormat.IMAGE, status=ExtractionStatus.SUCCESS, unit_label="image"
    )
    if ocr is None or not ocr.available():
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "이미지 문서는 OCR 엔진이 있어야 읽을 수 있습니다.",
            "cause": "OCR 비활성화" if ocr is None else "OCR 엔진 사용 불가",
            "resolution": "설정 PWA_OCR_ENGINE=rapidocr 을 확인하거나, 텍스트가 있는 PDF/DOCX 로 변환해 업로드하십시오.",
        }
        return result
    try:
        import numpy as np
        from PIL import Image

        pil = Image.open(io.BytesIO(data)).convert("RGB")
        image = np.array(pil)
    except Exception as exc:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "이미지 파일을 열 수 없습니다.",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "PNG 또는 JPG 로 다시 저장해 업로드하십시오.",
        }
        return result
    try:
        ocr_result = ocr.recognize(image)
    except Exception as exc:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "OCR 실행 중 오류가 발생했습니다.",
            "cause": f"{type(exc).__name__}: {exc}",
            "resolution": "이미지 해상도·형식을 확인하고 다시 시도하십시오.",
        }
        return result
    builder = BlockBuilder(project_id, document_id, file_name, FileFormat.IMAGE)
    confidence = float(ocr_result.confidence) if ocr_result.lines else 0.0
    low = confidence < ocr_review_threshold
    chars = 0
    for i, line in enumerate(ocr_result.lines):
        if not line.text.strip():
            continue
        chars += len(line.text)
        builder.add(
            line.text,
            BlockType.PARAGRAPH,
            location=BlockLocation(page=1, paragraph_index=i),
            method=ExtractionMethod.OCR,
            confidence=float(line.confidence),
            needs_review=low or float(line.confidence) < ocr_review_threshold,
            review_reason="OCR 신뢰도 낮음" if low else None,
        )
    result.blocks = builder.blocks
    result.page_count = 1
    result.ocr_engine = type(ocr).__name__
    result.page_stats.append(
        PageStat(page=1, char_count=chars, method=ExtractionMethod.OCR, confidence=confidence)
    )
    if chars == 0:
        result.warnings.append("OCR 결과 텍스트가 없습니다 (글자가 없는 이미지이거나 인식 실패).")
    elif low:
        result.warnings.append(
            f"OCR 평균 신뢰도 {confidence:.2f} < {ocr_review_threshold} — 검토 필요"
        )
    return result


__all__ = ["read_image"]
