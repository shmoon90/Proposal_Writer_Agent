"""요구사항 품질 검토 (지시문 §5.3, 단계 2) — 결정론적 규칙.

누락·중복, 충돌 후보, 검증 불가능한 표현, 구현 방안 불명확, RFP 근거 없는 추가, 업무 규칙·예외 누락 가능성,
비기능 요구 누락 후보, 테스트 불가능한 수용 기준을 찾는다. 결과는 **검토 목록**이며 자동으로 요구사항을 바꾸지
않는다. 화면(요구사항 페이지) 과 QA-RFP-09 에서 같은 함수를 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from proposal_agent.changes.semantic import similarity
from proposal_agent.models import (
    AcceptanceStatus,
    Requirement,
    RequirementCategory,
    RequirementStatus,
    RequirementType,
    ScopeClass,
)
from proposal_agent.requirements.difficulty import NUM_COND_RE
from proposal_agent.requirements.id_policy import normalize_text

VAGUE_WORDS: tuple[str, ...] = (
    "적절",
    "최대한",
    "신속",
    "편리",
    "친화적",
    "충분",
    "효율적",
    "원활",
    "유연",
    "다양한",
    "필요시",
    "가능한 한",
    "최적",
    "안정적",
    "빠르",
    "쉽게",
    "직관",
)
RULE_WORDS: tuple[str, ...] = (
    "규칙",
    "조건",
    "예외",
    "오류",
    "검증",
    "권한",
    "경우",
    "이상",
    "이하",
    "미만",
    "초과",
    "단계",
    "상태",
    "이면",
    "하면",
    "않",
)
EXPECTED_NFR_CATEGORIES: tuple[tuple[RequirementCategory, str], ...] = (
    (RequirementCategory.PERFORMANCE, "성능"),
    (RequirementCategory.SECURITY, "보안"),
    (RequirementCategory.AVAILABILITY, "가용성"),
    (RequirementCategory.COMPATIBILITY, "호환성·표준"),
    (RequirementCategory.OPERABILITY, "운영·유지관리"),
)
DUP_THRESHOLD = 0.85
_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(초|분|시간|건|명|%|MB|GB|TB|TPS|자리|개월|일|회)")
_TOKEN_RE = re.compile(r"[가-힣A-Za-z]{2,}")
_STOP = frozenset(
    {
        "시스템",
        "기능",
        "제공",
        "구현",
        "사용자",
        "관리",
        "화면",
        "처리",
        "지원",
        "정보",
        "데이터",
        "하여야",
        "한다",
        "있어야",
    }
)


@dataclass
class QualityFinding:
    rule: str  # Q-DUP | Q-CONFLICT | Q-VAGUE | Q-APPROACH | Q-NOSRC | Q-RULES | Q-NFR | Q-ACCEPT
    level: str  # warning | info
    requirement_ids: list[str]
    message: str
    suggestion: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return RULE_TITLES.get(self.rule, self.rule)


RULE_TITLES = {
    "Q-DUP": "중복 후보",
    "Q-CONFLICT": "충돌 후보(수치 조건)",
    "Q-VAGUE": "검증 불가 표현",
    "Q-APPROACH": "구현 방안 불명확",
    "Q-NOSRC": "RFP 근거 없음",
    "Q-RULES": "업무 규칙·예외 누락 가능",
    "Q-NFR": "비기능 요구 누락 후보",
    "Q-ACCEPT": "테스트 불가능한 수용 기준",
}


def _active(reqs: list[Requirement]) -> list[Requirement]:
    return [
        r
        for r in reqs
        if r.status != RequirementStatus.DELETED
        and r.change_state != "deleted"
        and r.acceptance_status != AcceptanceStatus.REJECTED
    ]


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text or "") if t not in _STOP}


def _vague_hits(text: str) -> list[str]:
    return [w for w in VAGUE_WORDS if w in (text or "")]


def check_requirement_quality(requirements: list[Requirement]) -> list[QualityFinding]:
    reqs = _active(requirements)
    out: list[QualityFinding] = []
    # Q-DUP: 이름 정규화 동일 또는 유사도 높음
    seen_pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(reqs):
        for b in reqs[i + 1 :]:
            key = (a.id, b.id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if (
                normalize_text(a.name) == normalize_text(b.name)
                or similarity(f"{a.name} {a.description}", f"{b.name} {b.description}")
                >= DUP_THRESHOLD
            ):
                out.append(
                    QualityFinding(
                        "Q-DUP",
                        "warning",
                        [a.id, b.id],
                        f"{a.id} '{a.name[:30]}' 와 {b.id} '{b.name[:30]}' 이 같거나 매우 유사",
                        "하나로 합치거나 범위 차이를 설명에 명시",
                    )
                )
    # Q-CONFLICT: 같은 주제(키워드 2개 이상 공유) 에서 같은 단위의 수치가 다름
    with_nums = [(r, _UNIT_RE.findall(f"{r.name} {r.description}")) for r in reqs]
    with_nums = [(r, n) for r, n in with_nums if n]
    for i, (a, na) in enumerate(with_nums):
        for b, nb in with_nums[i + 1 :]:
            if len(_tokens(a.name) & _tokens(b.name)) < 2:
                continue
            ua = {unit: val for val, unit in na}
            ub = {unit: val for val, unit in nb}
            diff = [u for u in ua if u in ub and ua[u] != ub[u]]
            if diff:
                out.append(
                    QualityFinding(
                        "Q-CONFLICT",
                        "warning",
                        [a.id, b.id],
                        f"{a.id} 와 {b.id} 의 '{', '.join(diff)}' 조건이 다름 ({', '.join(ua[u] + u for u in diff)} vs {', '.join(ub[u] + u for u in diff)})",
                        "RFP 원문을 확인해 하나의 조건으로 정리하거나 적용 범위를 구분",
                    )
                )
    for r in reqs:
        text = f"{r.name} {r.description}"
        # Q-VAGUE
        hits = _vague_hits(text)
        if hits and not NUM_COND_RE.search(text):
            out.append(
                QualityFinding(
                    "Q-VAGUE",
                    "warning",
                    [r.id],
                    f"{r.id}: '{', '.join(hits[:3])}' 는 검증할 수 없는 표현이며 수치·조건이 없음",
                    "측정 가능한 조건(수치·판정 기준) 으로 바꾸거나 확인 질문으로 관리",
                )
            )
        # Q-APPROACH
        if r.type in (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL):
            approach = r.implementation_approach or ""
            if not approach.strip():
                out.append(
                    QualityFinding(
                        "Q-APPROACH",
                        "warning",
                        [r.id],
                        f"{r.id}: 구현 방안 없음",
                        "'구현 방안 작성(에이전트)' 실행 또는 직접 입력",
                    )
                )
            elif "[자동 초안]" in approach or r.approach_source == "rule":
                out.append(
                    QualityFinding(
                        "Q-APPROACH",
                        "info",
                        [r.id],
                        f"{r.id}: 구현 방안이 규칙 초안([자동 초안])",
                        "에이전트 작성 또는 사람 확정",
                    )
                )
        # Q-NOSRC
        if (
            not r.source_refs
            and r.scope_class != ScopeClass.OPTIONAL_PROPOSAL
            and r.created_by != "user"
        ):
            out.append(
                QualityFinding(
                    "Q-NOSRC",
                    "warning",
                    [r.id],
                    f"{r.id}: RFP 원문 근거(출처 블록) 가 없음",
                    "원문 블록을 연결하거나 부가 제안(optional_proposal) 으로 분류",
                )
            )
        # Q-RULES
        if r.type == RequirementType.FUNCTIONAL and not any(w in text for w in RULE_WORDS):
            out.append(
                QualityFinding(
                    "Q-RULES",
                    "info",
                    [r.id],
                    f"{r.id}: 업무 규칙·조건·예외 처리 서술이 없음",
                    "입력값·업무 규칙·예외 상황을 상세 내용에 추가하거나 확인 질문으로 관리",
                )
            )
        # Q-ACCEPT
        if r.acceptance_status == AcceptanceStatus.ACCEPTED and r.type in (
            RequirementType.FUNCTIONAL,
            RequirementType.NON_FUNCTIONAL,
        ):
            ac = r.acceptance_criteria or ""
            if not ac.strip():
                out.append(
                    QualityFinding(
                        "Q-ACCEPT",
                        "warning",
                        [r.id],
                        f"{r.id}: 수용 기준(검사 기준) 없음",
                        "판정할 수 있는 조건 1~3줄 작성",
                    )
                )
            elif _vague_hits(ac) and not NUM_COND_RE.search(ac):
                out.append(
                    QualityFinding(
                        "Q-ACCEPT",
                        "warning",
                        [r.id],
                        f"{r.id}: 수용 기준에 검증 불가 표현만 있음 ('{ac[:40]}')",
                        "수치·판정 조건으로 교체",
                    )
                )
    # Q-NFR: 비기능 분류 누락 후보
    nfr_cats = {r.category for r in reqs if r.type == RequirementType.NON_FUNCTIONAL}
    missing = [label for cat, label in EXPECTED_NFR_CATEGORIES if cat not in nfr_cats]
    if missing and reqs:
        out.append(
            QualityFinding(
                "Q-NFR",
                "info",
                [],
                "비기능 요구가 없는 분류: " + ", ".join(missing),
                "RFP 에 해당 조건이 있는지 확인하고 없으면 전제(가정) 로 기록",
            )
        )
    return out


def quality_summary(findings: list[QualityFinding]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.rule] = out.get(f.rule, 0) + 1
    return out


__all__ = [
    "DUP_THRESHOLD",
    "EXPECTED_NFR_CATEGORIES",
    "RULE_TITLES",
    "VAGUE_WORDS",
    "QualityFinding",
    "check_requirement_quality",
    "quality_summary",
]
