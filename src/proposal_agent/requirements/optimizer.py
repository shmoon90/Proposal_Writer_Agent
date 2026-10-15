"""추출·검증 호출 최적화 (결정적 코드).

- 신호 없는 청크 건너뛰기: 요구사항 표현(의무·제공·성능·제출·평가·수치 등)이 전혀 없고 표도 없는 청크는 에이전트에 보내지 않는다.
- 청크 캐시: (역할·시스템 프롬프트·청크 본문) 해시가 같으면 이전 구조화 출력을 재사용한다(비용 0). 문서가 바뀐 청크만 다시 호출.
- 검증 창(window): 검증은 출력이 작으므로 추출 청크보다 큰 창으로 묶어 호출 수를 줄인다.
- 호출 수 상한·프로젝트 누적 예산 상한: 호출 전에 코드가 검사해 초과하면 호출하지 않고 멈춘다.
- 프롬프트 압축: 검증 프롬프트의 요구사항 JSON은 필요한 필드만, 긴 본문은 절단한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from proposal_agent.config.errors import ValidationError
from proposal_agent.ingest.chunker import Chunk
from proposal_agent.models import BlockType, ExtractedBlock, Requirement

SIGNAL_RE = re.compile(
    r"(하여야|해야|필수|반드시|요구|제공|구축|지원|기능|성능|보안|제출|평가|납품|기간|비용|예산|연계|"
    r"이상|이하|이내|초|분|건|명|%|구현|개발|설계|운영|유지보수|교육|검수|산출물|\|)"
)
HEADING_TYPES = {BlockType.HEADING, BlockType.TITLE, BlockType.TOC}
MIN_CHUNK_TEXT = 120  # 태그 제외 본문이 이보다 짧으면 요구사항이 들어 있다고 보지 않는다
DESC_MAX = 400
QUOTE_MAX = 200
CROSS_CHECK_MAX_ITEMS = 200


def plain_text(chunk: Chunk) -> str:
    """청크 본문에서 <block …> 태그를 제거한 텍스트."""
    return re.sub(r"</?block[^>]*>", "", chunk.text)


def has_signal(chunk: Chunk, blocks_by_id: dict[str, ExtractedBlock]) -> bool:
    kinds = {blocks_by_id[b].block_type for b in chunk.block_ids if b in blocks_by_id}
    if kinds and kinds <= HEADING_TYPES:
        return False
    if BlockType.TABLE in kinds:
        return True
    text = plain_text(chunk)
    if len(text.strip()) < MIN_CHUNK_TEXT:
        return False
    return bool(SIGNAL_RE.search(text))


def chunk_key(role: str, system_prompt: str, text: str, model: str | None = None) -> str:
    h = hashlib.sha256()
    for part in (role, model or "", system_prompt, text):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


@dataclass
class ChunkCache:
    """워크스페이스 파일 캐시. 같은 입력이면 이전 구조화 출력을 재사용한다."""

    folder: Path
    enabled: bool = True

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        p = self.folder / f"{key}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, output: dict[str, Any], *, cost_usd: float, turns: int) -> None:
        if not self.enabled:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = {"output": output, "cost_usd": cost_usd, "turns": turns}
        (self.folder / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )


@dataclass
class RunPlan:
    """실행 전 예상치 (호출 수·건너뜀·캐시·최대 비용). UI와 호출 상한 검사에 쓴다."""

    kind: str  # extract | verify
    chunks_total: int = 0
    to_call: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    cached: list[int] = field(default_factory=list)
    cross_check: bool = False
    input_chars: int = 0
    max_cost_per_call: float = 0.0
    max_calls: int = 0
    project_cost_so_far: float = 0.0
    project_budget: float = 0.0

    @property
    def calls(self) -> int:
        return len(self.to_call) + (1 if self.cross_check else 0)

    @property
    def est_max_cost(self) -> float:
        return round(self.calls * self.max_cost_per_call, 2)

    @property
    def over_call_limit(self) -> bool:
        return self.max_calls > 0 and self.calls > self.max_calls

    @property
    def over_budget(self) -> bool:
        return self.project_budget > 0 and (
            self.project_cost_so_far + self.est_max_cost > self.project_budget
        )

    def summary(self) -> str:
        return (
            f"청크 {self.chunks_total}개 중 호출 {len(self.to_call)}개"
            + (" + 교차 검사 1회" if self.cross_check else "")
            + f", 건너뜀 {len(self.skipped)}개, 캐시 재사용 {len(self.cached)}개, "
            f"입력 약 {self.input_chars:,}자, 최대 비용 ${self.est_max_cost:.2f} "
            f"(호출 상한 {self.max_calls or '없음'}, 프로젝트 누적 ${self.project_cost_so_far:.2f}/"
            f"{'$' + format(self.project_budget, '.2f') if self.project_budget else '상한 없음'})"
        )

    def require_within_limits(self) -> None:
        if self.over_call_limit:
            raise ValidationError(
                f"에이전트 호출 수가 상한을 넘습니다: {self.calls}회 > {self.max_calls}회",
                cause=f"{self.kind}: 청크 {self.chunks_total}개 (건너뜀 {len(self.skipped)}, 캐시 {len(self.cached)})",
                resolution="PWA_MAX_AGENT_CALLS_PER_STEP을 올리거나, 문서를 나누어 올리거나, PWA_EXTRACTION_CHUNK_CHARS를 키우십시오.",
            )
        if self.over_budget:
            raise ValidationError(
                "프로젝트 누적 비용 상한을 넘을 수 있어 실행하지 않습니다.",
                cause=f"누적 ${self.project_cost_so_far:.2f} + 예상 최대 ${self.est_max_cost:.2f} > 상한 ${self.project_budget:.2f}",
                resolution="PWA_MAX_BUDGET_USD_PER_PROJECT를 올리거나 호출 수를 줄이십시오.",
            )


def build_windows(chunks: list[Chunk], max_chars: int) -> list[Chunk]:
    """추출 청크를 더 큰 검증 창으로 합친다 (순서 유지, 블록 분할 없음)."""
    windows: list[Chunk] = []
    current: Chunk | None = None
    for ch in chunks:
        if current is not None and current.char_count + ch.char_count <= max_chars:
            current.block_ids.extend(ch.block_ids)
            current.text += "\n\n" + ch.text
            current.char_count += ch.char_count
            for s in ch.sections:
                if s not in current.sections:
                    current.sections.append(s)
            continue
        current = Chunk(
            index=len(windows),
            block_ids=list(ch.block_ids),
            sections=list(ch.sections),
            text=ch.text,
            char_count=ch.char_count,
        )
        windows.append(current)
    return windows


def compact_items(reqs: list[Requirement], *, with_sources: bool) -> list[dict[str, Any]]:
    """검증 프롬프트용 요구사항 요약 — 필요한 필드만, 긴 본문은 절단."""
    out = []
    for r in reqs:
        item: dict[str, Any] = {
            "id": r.id,
            "name": r.name,
            "description": r.description[:DESC_MAX],
            "type": str(r.type),
            "scope_class": str(r.scope_class),
            "is_mandatory": r.is_mandatory,
        }
        if with_sources:
            item["rfp_quote"] = (r.rfp_quote or "")[:QUOTE_MAX]
            item["source_block_ids"] = [ref.block_id for ref in r.source_refs]
        out.append(item)
    return out


def dumps_compact(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ": "))


__all__ = [
    "CROSS_CHECK_MAX_ITEMS",
    "ChunkCache",
    "RunPlan",
    "build_windows",
    "chunk_key",
    "compact_items",
    "dumps_compact",
    "has_signal",
    "plain_text",
]
