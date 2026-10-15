"""블록을 LLM 입력 청크로 묶는다 (결정적).

- 섹션 경계를 우선하고, 표는 쪼개지 않는다.
- 각 블록은 ``<block id="…" type="…" loc="…">`` 태그로 감싸 에이전트가 출처 ID를 그대로 인용하게 한다.
- 목차(TOC) 블록은 요구사항 원문이 아니므로 제외한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from proposal_agent.models import BlockType, ExtractedBlock

SKIP_TYPES = {BlockType.TOC}


@dataclass
class Chunk:
    index: int
    block_ids: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    text: str = ""
    char_count: int = 0


def render_block(block: ExtractedBlock) -> str:
    loc = block.location.label()
    flags = ""
    if block.extraction_method.value == "ocr":
        flags += f' ocr="1" conf="{block.confidence:.2f}"'
    if block.needs_review:
        flags += ' needs_review="1"'
    if block.section_kind:
        flags += f' section="{block.section_kind}"'
    if block.rfp_requirement_id:
        flags += f' rfp_id="{block.rfp_requirement_id}"'
    return f'<block id="{block.id}" type="{block.block_type.value}" loc="{loc}"{flags}>\n{block.text}\n</block>'


def build_chunks(blocks: list[ExtractedBlock], max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    current = Chunk(index=0)

    def flush() -> None:
        nonlocal current
        if current.block_ids:
            chunks.append(current)
            current = Chunk(index=len(chunks))

    last_rfp_id: str | None = None
    for block in sorted(blocks, key=lambda b: b.order):
        if block.block_type in SKIP_TYPES:
            continue
        rendered = render_block(block)
        size = len(rendered)
        starts_section = block.block_type in (
            BlockType.HEADING,
            BlockType.TITLE,
            BlockType.APPENDIX,
        )
        # RFP 요구사항 ID가 바뀌는 지점은 자연스러운 경계 — 한 요구사항 표가 청크에 걸쳐 쪼개지지 않게 한다
        new_rfp = bool(block.rfp_requirement_id) and block.rfp_requirement_id != last_rfp_id
        if current.block_ids and (
            current.char_count + size > max_chars
            or (starts_section and current.char_count > max_chars * 0.6)
            or (new_rfp and current.char_count > max_chars * 0.5)
        ):
            flush()
        if block.rfp_requirement_id:
            last_rfp_id = block.rfp_requirement_id
        current.block_ids.append(block.id)
        current.text += ("\n\n" if current.text else "") + rendered
        current.char_count += size
        section = block.location.section
        if section and section not in current.sections:
            current.sections.append(section)
    flush()
    return chunks
