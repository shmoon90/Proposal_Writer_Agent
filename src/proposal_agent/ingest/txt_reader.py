"""TXT 리더. 인코딩(utf-8-sig → utf-8 → cp949)을 순서대로 시도하고 빈 줄 기준으로 문단을 나눈다."""

from __future__ import annotations

from proposal_agent.ingest.base import (
    BlockBuilder,
    ReaderResult,
    looks_like_heading,
    looks_like_list_item,
)
from proposal_agent.models import (
    BlockLocation,
    ExtractionMethod,
    ExtractionStatus,
    FileFormat,
    PageStat,
)

_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")


def decode_text(data: bytes) -> tuple[str, str]:
    last: UnicodeDecodeError | None = None
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError as exc:
            last = exc
    raise ValueError(f"지원 인코딩으로 해석할 수 없음: {last}")


def read_txt(data: bytes, *, project_id: str, document_id: str, file_name: str) -> ReaderResult:
    result = ReaderResult(
        file_format=FileFormat.TXT, status=ExtractionStatus.SUCCESS, unit_label="line"
    )
    if b"\x00" in data[:4096]:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "텍스트 파일이 아닌 것 같습니다 (바이너리 데이터).",
            "cause": "NUL 바이트 포함",
            "resolution": "UTF-8 또는 CP949로 저장한 .txt 파일을 업로드하십시오.",
        }
        return result
    try:
        text, enc = decode_text(data)
    except ValueError as exc:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "텍스트 인코딩을 해석할 수 없습니다.",
            "cause": str(exc),
            "resolution": "UTF-8로 저장한 뒤 다시 업로드하십시오.",
        }
        return result

    builder = BlockBuilder(project_id, document_id, file_name, FileFormat.TXT)
    lines = text.splitlines()
    buf: list[str] = []
    start = 0
    for i, line in enumerate(lines, start=1):
        if line.strip():
            if not buf:
                start = i
            buf.append(line.rstrip())
            # 한 줄짜리 제목/목록은 즉시 블록으로 (다음 줄과 합치지 않음)
            if looks_like_heading(line) or looks_like_list_item(line):
                builder.add_text(
                    "\n".join(buf),
                    location=BlockLocation(
                        line_start=start, line_end=i, paragraph_index=builder.next_paragraph_index()
                    ),
                )
                buf = []
        elif buf:
            builder.add_text(
                "\n".join(buf),
                location=BlockLocation(
                    line_start=start, line_end=i - 1, paragraph_index=builder.next_paragraph_index()
                ),
            )
            buf = []
    if buf:
        builder.add_text(
            "\n".join(buf),
            location=BlockLocation(
                line_start=start,
                line_end=len(lines),
                paragraph_index=builder.next_paragraph_index(),
            ),
        )

    result.page_count = len(lines)
    result.page_stats = [PageStat(page=0, method=ExtractionMethod.TEXT, char_count=len(text))]
    result.blocks = builder.blocks
    result.warnings.append(f"인코딩 {enc}로 해석. 페이지 개념이 없어 줄 번호로 위치를 기록합니다.")
    if not result.blocks:
        result.status = ExtractionStatus.FAILED
        result.error = {
            "message": "빈 텍스트 파일입니다.",
            "cause": "내용 없음",
            "resolution": "내용이 있는 파일을 업로드하십시오.",
        }
    return result
