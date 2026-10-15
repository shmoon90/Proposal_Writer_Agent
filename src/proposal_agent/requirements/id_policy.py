"""요구사항 ID 발급 정책 (WORKFLOW_DESIGN.md 3절).

- 형식: ``REQ-F-001`` (기능), ``REQ-N-001`` (비기능). 프로젝트 내 단조 증가, ``sequences`` 테이블 관리.
- 발급 이후 재발급·재사용하지 않는다. 삭제는 상태 변경이므로 번호는 영구 예약된다.
- 추출 재실행 시 ``name``/``rfp_quote`` 정규화 문자열이 일치하면 기존 ID를 유지한다 (``resolve``).
- 구축 단계에서 기존 ID 체계를 가져올 때는 ``LegacyIdScheme``으로 접두·자리수를 이어서 발급한다.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from proposal_agent.config.errors import ValidationError
from proposal_agent.models.enums import RequirementType
from proposal_agent.models.requirement import Requirement
from proposal_agent.storage.repositories import SequenceRepository

DEFAULT_WIDTH = 3
_TYPE_CODE = {RequirementType.FUNCTIONAL: "F", RequirementType.NON_FUNCTIONAL: "N"}
_ID_RE = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")
_NORMALIZE_DROP = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text: str | None) -> str:
    """공백·구두점·대소문자·유니코드 정규화 차이를 무시하는 비교용 문자열."""
    if not text:
        return ""
    return _NORMALIZE_DROP.sub("", unicodedata.normalize("NFKC", text)).casefold()


def find_match(
    name: str, rfp_quote: str | None, existing: Iterable[Requirement]
) -> Requirement | None:
    """정규화한 ``name`` 또는 ``rfp_quote``가 일치하는 기존 요구사항 (첫 번째)."""
    n_name = normalize_text(name)
    n_quote = normalize_text(rfp_quote)
    for req in existing:
        if n_name and normalize_text(req.name) == n_name:
            return req
        if n_quote and normalize_text(req.rfp_quote) == n_quote:
            return req
    return None


@dataclass(frozen=True)
class LegacyIdScheme:
    """기존 산출물의 ID 체계 (예: ``SFR-012`` → prefix ``SFR-``, width 3)."""

    prefix: str
    width: int

    @classmethod
    def infer(cls, existing_ids: Iterable[str]) -> LegacyIdScheme | None:
        """기존 ID 목록에서 가장 흔한 접두사·자리수를 추론한다."""
        counts: dict[tuple[str, int], int] = {}
        for raw in existing_ids:
            m = _ID_RE.match(raw.strip())
            if not m:
                continue
            key = (m.group("prefix"), len(m.group("number")))
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            return None
        prefix, width = max(counts, key=lambda k: counts[k])
        return cls(prefix=prefix, width=width)

    def max_number(self, existing_ids: Iterable[str]) -> int:
        best = 0
        for raw in existing_ids:
            m = _ID_RE.match(raw.strip())
            if m and m.group("prefix") == self.prefix:
                best = max(best, int(m.group("number")))
        return best

    def format(self, number: int) -> str:
        return f"{self.prefix}{number:0{self.width}d}"


class RequirementIdPolicy:
    def __init__(self, sequences: SequenceRepository, width: int = DEFAULT_WIDTH) -> None:
        self._sequences = sequences
        self._width = width

    @staticmethod
    def sequence_key(req_type: RequirementType) -> str:
        return f"REQ-{_TYPE_CODE[req_type]}"

    def allocate(self, project_id: str, req_type: RequirementType) -> str:
        key = self.sequence_key(req_type)
        number = self._sequences.next(project_id, key)
        return f"{key}-{number:0{self._width}d}"

    def peek(self, project_id: str, req_type: RequirementType) -> str:
        key = self.sequence_key(req_type)
        return f"{key}-{self._sequences.peek(project_id, key):0{self._width}d}"

    def resolve(
        self,
        project_id: str,
        req_type: RequirementType,
        *,
        name: str,
        rfp_quote: str | None,
        existing: Iterable[Requirement],
    ) -> tuple[str, bool]:
        """기존 항목과 매칭되면 ``(기존 ID, True)``, 아니면 새 ID를 발급해 ``(새 ID, False)``."""
        match = find_match(name, rfp_quote, existing)
        if match is not None:
            return match.id, True
        return self.allocate(project_id, req_type), False

    def allocate_legacy(
        self, project_id: str, scheme: LegacyIdScheme, existing_ids: Iterable[str]
    ) -> str:
        """기존 체계를 이어서 발급. 시퀀스를 기존 최대값 다음 이상으로 끌어올린 뒤 발급한다."""
        key = f"legacy:{scheme.prefix}"
        self._sequences.ensure_at_least(project_id, key, scheme.max_number(existing_ids) + 1)
        number = self._sequences.next(project_id, key)
        return scheme.format(number)

    @staticmethod
    def validate_format(req_id: str) -> None:
        if not re.fullmatch(r"REQ-[FN]-\d{3,}", req_id):
            raise ValidationError(
                f"요구사항 ID 형식 오류: {req_id}",
                cause="REQ-F-001 / REQ-N-001 형식이 아님",
                resolution="ID는 id_policy가 발급한 값만 사용하십시오.",
            )
