"""OCR 엔진 플러그인.

기본 엔진은 ``rapidocr``(ONNX Runtime, 한국어 인식 모델 ``korean_PP-OCRv5_rec_mobile``)이며 지연 임포트한다.
엔진이 없거나 초기화에 실패하면 ``available()``이 False를 돌려주고, 추출 서비스는 OCR을 건너뛰면서
경고와 함께 해당 페이지를 검토 필요로 표시한다 (추측 금지).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from proposal_agent.config.logging import get_logger

log = get_logger("ingest.ocr")


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float


@dataclass(frozen=True)
class OcrResult:
    lines: list[OcrLine]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, image: Any) -> OcrResult: ...


class NullOcrEngine:
    """OCR 비활성화 또는 사용 불가."""

    name = "none"

    def __init__(self, reason: str = "OCR 엔진이 설정되지 않았습니다.") -> None:
        self.reason = reason

    def available(self) -> bool:
        return False

    def recognize(self, image: Any) -> OcrResult:
        raise RuntimeError(self.reason)


class RapidOcrEngine:
    """rapidocr 기반 엔진. 첫 호출 시 모델을 로드한다(필요 시 다운로드)."""

    name = "rapidocr"

    def __init__(self, lang: str = "korean") -> None:
        self.lang = lang
        self._engine: Any = None
        self._error: str | None = None

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self._error is not None:
            raise RuntimeError(self._error)
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            lang_enum = LangRec(self.lang)
            params: dict[str, Any] = {"Rec.lang_type": lang_enum}
            if lang_enum == LangRec.KOREAN:
                params["Rec.ocr_version"] = OCRVersion.PPOCRV5
                params["Rec.model_type"] = ModelType.MOBILE
            self._engine = RapidOCR(params=params)
            return self._engine
        except Exception as exc:  # 임포트 실패, 모델 다운로드 실패 등
            self._error = f"rapidocr 초기화 실패: {type(exc).__name__}: {exc}"
            log.warning(self._error)
            raise RuntimeError(self._error) from exc

    def available(self) -> bool:
        try:
            self._load()
            return True
        except RuntimeError:
            return False

    def recognize(self, image: Any) -> OcrResult:
        engine = self._load()
        result = engine(image)
        txts = list(result.txts or [])
        scores = list(result.scores or [])
        lines = [
            OcrLine(text=t, confidence=float(s)) for t, s in zip(txts, scores, strict=False) if t
        ]
        return OcrResult(lines=lines)


def build_ocr_engine(engine_name: str, lang: str) -> OcrEngine:
    if engine_name.lower() in ("", "none", "off"):
        return NullOcrEngine("설정(PWA_OCR_ENGINE=none)으로 OCR이 비활성화되었습니다.")
    if engine_name.lower() == "rapidocr":
        return RapidOcrEngine(lang=lang)
    return NullOcrEngine(f"알 수 없는 OCR 엔진: {engine_name}")
