"""구현 난이도(상/중/하) 추정 — 텍스트 신호 기반 결정적 규칙 (Phase 14).

요구사항 정의서의 '구현 난이도' 초안과, 구축 단계 변경 요청의 공수·일정 영향 가중치에 쓴다.
에이전트가 판단한 값이 있으면 그것이 우선이고, 이 규칙은 초안·보조 근거일 뿐이다.
"""

from __future__ import annotations

import re

from proposal_agent.models.enums import Difficulty, FeasibilityVerdict, RequirementCategory

# 설계·시험이 복잡해지는 신호 (연계·신기술·수치 조건·보안·데이터 이관 등)
HIGH_WORDS: tuple[str, ...] = (
    "연계",
    "인터페이스",
    "외부 시스템",
    "api",
    "실시간",
    "대용량",
    "암호화",
    "이관",
    "마이그레이션",
    "이중화",
    "동시 사용자",
    "동시접속",
    "tps",
    "sso",
    "공인인증",
    "전자서명",
    "ocr",
    "ai",
    "머신러닝",
    "인공지능",
    "알림톡",
    "결제",
    "pg",
    "배치",
    "스케줄",
    "워크플로",
    "전자결재",
    "gis",
    "지도",
    "통계 분석",
    "검색엔진",
    "비식별",
    "개인정보",
    "성능",
    "부하",
    "가용성",
    "복구",
    "모바일 앱",
    "푸시",
)
# 단순 변경·조회 수준 신호
LOW_WORDS: tuple[str, ...] = (
    "라벨",
    "문구",
    "코드값",
    "코드 값",
    "표시 순서",
    "정렬",
    "단순 조회",
    "안내 문구",
    "툴팁",
    "다운로드",
    "출력 형식",
    "색상",
    "폰트",
)
CATEGORY_SCORE: dict[RequirementCategory, int] = {
    RequirementCategory.INTERFACE: 2,
    RequirementCategory.SECURITY: 2,
    RequirementCategory.PERFORMANCE: 2,
    RequirementCategory.DATA: 2,
    RequirementCategory.AVAILABILITY: 2,
    RequirementCategory.BUSINESS: 1,
    RequirementCategory.REPORT: 1,
    RequirementCategory.ADMIN: 1,
    RequirementCategory.OPERABILITY: 1,
    RequirementCategory.COMPATIBILITY: 1,
    RequirementCategory.UI: 1,
    RequirementCategory.CONSTRAINT: 0,
    RequirementCategory.OTHER: 1,
}
NUM_COND_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:초|분|시간|건|명|%|MB|GB|TB|TPS|자리|개월|일|회)")
BULLET_RE = re.compile(r"(?m)^\s*(?:[-•·ㅇ○※■*]|\d+[.)])\s*")


def score_text(text: str) -> tuple[int, list[str]]:
    """텍스트에서 난이도 점수와 근거 목록을 뽑는다 (점수는 -1~4 범위로 제한)."""
    t = (text or "").casefold()
    score = 0
    basis: list[str] = []
    hits = [w for w in HIGH_WORDS if w in t]
    if hits:
        add = min(2, len(hits))
        score += add
        basis.append("복잡도 신호: " + ", ".join(hits[:4]))
    nums = NUM_COND_RE.findall(text or "")
    if nums:
        score += 1
        basis.append("수치 조건: " + ", ".join(dict.fromkeys(n.strip() for n in nums[:3])))
    bullets = len(BULLET_RE.findall(text or ""))
    if bullets >= 5:
        score += 1
        basis.append(f"세부 항목 {bullets}개")
    lows = [w for w in LOW_WORDS if w in t]
    if lows and not hits:
        score -= 1
        basis.append("단순 변경 신호: " + ", ".join(lows[:3]))
    if len((text or "").strip()) < 40 and not hits and not nums:
        score -= 1
        basis.append("짧은 단순 요구")
    return max(-1, min(4, score)), basis


def estimate_difficulty(
    text: str,
    *,
    category: RequirementCategory | None = None,
    feasibility: FeasibilityVerdict | None = None,
    base: Difficulty | None = None,
) -> tuple[Difficulty, str]:
    """(난이도, 근거). ``base``(기존 난이도)가 있으면 그보다 낮추지 않는다."""
    score, basis = score_text(text)
    if category is not None:
        cs = CATEGORY_SCORE.get(category, 1)
        score += cs
        if cs >= 2:
            basis.append(f"분류 '{category.label}'")
    if feasibility == FeasibilityVerdict.FEASIBLE_WITH_RISK:
        score += 1
        basis.append("조사 결과 위험 있음(feasible_with_risk)")
    elif feasibility == FeasibilityVerdict.INFEASIBLE:
        score += 2
        basis.append("조사 결과 구현 불가로 대안 필요")
    if score >= 4:
        level = Difficulty.HIGH
    elif score >= 2:
        level = Difficulty.MEDIUM
    else:
        level = Difficulty.LOW
    order = [Difficulty.LOW, Difficulty.MEDIUM, Difficulty.HIGH]
    if base is not None and order.index(base) > order.index(level):
        level = base
        basis.append(f"기존 난이도 {base.label} 유지")
    return level, ("; ".join(basis) if basis else "일반 업무 기능 수준") + " (규칙 추정)"


def approach_lines(text: str | None) -> list[str]:
    """구현 방안을 글머리 줄 목록으로 정규화한다 ('- ' 접두, 빈 줄 제거)."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        ln = re.sub(r"^(?:[-•·ㅇ○■*]|\d+[.)])\s*", "", ln)
        if ln:
            out.append(f"- {ln}")
    return out
