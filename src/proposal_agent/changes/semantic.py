"""결정적 의미 비교·분류 (규칙 기반). 에이전트 결과는 ``service``에서 "ai" 출처로 덧붙인다.

분류: ADD / MODIFY / DELETE_REQUEST / NO_CHANGE / AMBIGUOUS
- 유사한 기존 항목이 있으면 기존 ID를 유지한다. 새 ID는 승인 후에만 발급한다.
- 모호하면 수정·삭제를 자동 결정하지 않고 AMBIGUOUS + 확인 필요로 둔다.
- 모든 결정에 근거(rationale)·신뢰도·관련 ID·확인 필요 여부를 붙인다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from proposal_agent.models import Requirement
from proposal_agent.models.change import (
    CandidateClass,
    ChangeCandidate,
    InputKind,
    SemanticFeatures,
)
from proposal_agent.requirements.id_policy import normalize_text

# 의도 키워드 ---------------------------------------------------------------------------
DELETE_WORDS = ("삭제", "제거", "없애", "빼 ", "빼주", "불필요", "제외", "중단", "폐기", "하지 않")
MODIFY_WORDS = (
    "변경",
    "수정",
    "바꾸",
    "바꿔",
    "대신",
    "으로 변경",
    "로 변경",
    "늘려",
    "줄여",
    "조정",
    "강화",
    "완화",
    "개선",
    "확대",
    "축소",
    "도 포함",
    "까지 지원",
)
ADD_WORDS = (
    "추가",
    "신규",
    "새로",
    "새 ",
    "신설",
    "도입",
    "지원해",
    "필요하다",
    "요청한다",
    "구현한다",
    "제공한다",
)
NON_FUNCTIONAL_WORDS = (
    "초 이내",
    "초이내",
    "응답",
    "성능",
    "가용",
    "보안",
    "암호화",
    "동시 사용자",
    "동시접속",
    "tps",
    "백업",
    "복구",
    "가동률",
    "접근성",
    "호환",
    "로그 보관",
    "용량",
)
ACTOR_WORDS = (
    "사용자",
    "관리자",
    "민원인",
    "담당자",
    "운영자",
    "시스템",
    "고객",
    "회원",
    "직원",
    "승인자",
    "결재자",
    "부서",
    "기관",
)
ACTION_WORDS = (
    "등록",
    "조회",
    "수정",
    "삭제",
    "로그인",
    "로그아웃",
    "접수",
    "처리",
    "출력",
    "전송",
    "알림",
    "승인",
    "반려",
    "검색",
    "다운로드",
    "업로드",
    "통계",
    "집계",
    "연계",
    "인증",
    "저장",
    "발급",
    "결제",
    "예약",
    "배포",
    "모니터링",
    "인쇄",
    "첨부",
    "암호화",
    "백업",
)
SCREEN_RE = re.compile(r"(SCR-\d+|[가-힣A-Za-z0-9 ]{1,20}(?:화면|페이지|메뉴|팝업))")
ID_RE = re.compile(r"\b[A-Z]{2,5}-?\d{2,5}\b")
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:초|분|시간|회|건|명|%|MB|GB|TB|TPS|개월|일)")
SCHEDULE_RE = re.compile(
    r"(다음 배포 전|오픈 전|검수 전|\d{4}[-./]\d{1,2}[-./]\d{1,2}\s*까지|\d{1,2}월\s*(?:말|까지)|이번 달|긴급|즉시|분기 내)"
)
SPLIT_RE = re.compile(
    r"(?:\r?\n|;\s*|(?:^|\s)(?:[-•*·]|\d+[.)])\s+)"
)  # 줄·글머리·번호 단위 (마침표로는 나누지 않음)

THRESH_SAME = 0.85
THRESH_MODIFY = 0.55
THRESH_RELATED = 0.35
THRESH_DUPLICATE = 0.7  # 추가 버튼 요청이 기존 항목과 이 이상 유사하면 중복 확인


ATTACH_HEADER_RE = re.compile(r"^\[첨부 .*발췌\]$")


def split_items(text: str) -> list[str]:
    parts = [p.strip(" -•*·\t") for p in SPLIT_RE.split(text or "")]
    out = [p for p in parts if p and len(p) >= 4 and not ATTACH_HEADER_RE.match(p)]
    return out or ([text.strip()] if text and text.strip() else [])


def _bigrams(norm: str) -> set[str]:
    return {norm[i : i + 2] for i in range(len(norm) - 1)} if len(norm) > 1 else {norm}


def extract_features(text: str) -> SemanticFeatures:
    t = text or ""
    low = t.casefold()
    f = SemanticFeatures()
    f.actors = [w for w in ACTOR_WORDS if w in t]
    f.actions = [w for w in ACTION_WORDS if w in t]
    f.quality = [w for w in NON_FUNCTIONAL_WORDS if w in low]
    f.rules = NUM_RE.findall(t)
    f.screens = [m.strip() for m in SCREEN_RE.findall(t)][:5]
    f.constraints = [
        w for w in ("이내", "이상", "이하", "필수", "반드시", "금지", "만", "제한") if w in t
    ]
    f.keywords = sorted(set(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", t)))[:40]
    f.purpose = split_items(t)[0][:80] if t.strip() else ""
    return f


def similarity(a: str, b: str) -> float:
    """문자 bigram Jaccard(0.5) + 순서 유사도(0.3) + 특징 겹침(0.2)."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    ba, bb = _bigrams(na), _bigrams(nb)
    jacc = len(ba & bb) / len(ba | bb) if ba | bb else 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    fa, fb = extract_features(a), extract_features(b)
    sa = set(fa.actors + fa.actions + fa.quality + fa.keywords)
    sb = set(fb.actors + fb.actions + fb.quality + fb.keywords)
    feat = len(sa & sb) / len(sa | sb) if sa | sb else 0.0
    score = 0.5 * jacc + 0.3 * seq + 0.2 * feat
    if fa.rules and fb.rules and set(fa.rules) != set(fb.rules):
        score = min(score, 0.84)  # 숫자 조건이 다르면 '같음'으로 보지 않는다
    return round(score, 4)


ASPECT_LABELS: dict[str, str] = {
    "scope": "범위",
    "actor": "대상 사용자",
    "io": "입력/출력",
    "rule": "업무 규칙",
    "number": "수치 조건",
    "screen": "화면",
    "interface": "연계",
    "quality": "성능/보안",
    "data": "데이터",
}
_IO_WORDS = ("입력", "출력", "업로드", "다운로드", "첨부", "파일", "양식", "출력물", "인쇄")
_INTERFACE_WORDS = ("연계", "인터페이스", "api", "외부", "전송", "수신", "연동")
_DATA_WORDS = ("데이터", "테이블", "이관", "저장", "보관", "이력", "db")
_RULE_WORDS = ("규칙", "조건", "기준", "권한", "승인", "반려", "검증", "제한", "필수", "만")


def context_delta(before: str, after: str) -> list[str]:
    """변경 전후 문장의 **문맥** 차이를 관점(ASPECT_LABELS 키)으로 돌려준다 — 단순 문자열 비교가 아니다.

    주체(사용자)·행위·수치 조건·화면·품질 조건·연계·데이터·입출력·규칙 단어 집합을 비교하고,
    분량이 크게 늘거나 줄면 '범위'로 본다.
    """
    fb, fa = extract_features(before or ""), extract_features(after or "")
    lb, la = (before or "").casefold(), (after or "").casefold()
    out: list[str] = []
    if set(fb.actors) != set(fa.actors):
        out.append("actor")
    if set(fb.rules) != set(fa.rules):
        out.append("number")
    if set(fb.screens) != set(fa.screens):
        out.append("screen")
    if set(fb.quality) != set(fa.quality):
        out.append("quality")

    def diff(words: tuple[str, ...]) -> bool:
        return {w for w in words if w in lb} != {w for w in words if w in la}

    if diff(_INTERFACE_WORDS):
        out.append("interface")
    if diff(_DATA_WORDS):
        out.append("data")
    if diff(_IO_WORDS):
        out.append("io")
    if diff(_RULE_WORDS) or set(fb.constraints) != set(fa.constraints):
        out.append("rule")
    actions_changed = set(fb.actions) != set(fa.actions)
    longer = len(la) > len(lb) * 1.3 + 20 or len(la) * 1.3 + 20 < len(lb)
    if actions_changed or longer:
        out.append("scope")
    return out


def aspect_labels(aspects: list[str]) -> list[str]:
    return [ASPECT_LABELS.get(a, a) for a in aspects]


def change_difficulty(
    item: str, aspects: list[str], existing: Requirement | None
) -> tuple[str, str]:
    """변경 항목의 구현 난이도(상/중/하)와 근거. 기존 요구사항의 난이도·분류를 바탕으로 관점 수를 더한다."""
    from proposal_agent.requirements.difficulty import estimate_difficulty

    base = existing.difficulty if existing else None
    category = existing.category if existing else None
    level, why = estimate_difficulty(item, category=category, base=None)
    order = ["low", "medium", "high"]
    idx = order.index(level.value)
    heavy = {"interface", "quality", "data", "number"}
    hits = [a for a in aspects if a in heavy]
    if len(hits) >= 2 or (len(aspects) >= 3 and hits):
        idx = min(2, idx + 1)
        why += f"; 변경 관점 {', '.join(aspect_labels(hits))} → 한 단계 상향"
    if base is not None and order.index(base.value) > idx and hits:
        idx = order.index(base.value)
        why += f"; 기존 난이도 {base.label} 이상"
    labels = {"low": "하", "medium": "중", "high": "상"}
    return labels[order[idx]], why


def name_containment(name: str, text: str) -> float:
    """요구사항 명이 요청문에 얼마나 포함되는지 (overlap coefficient). 이름이 완전히 들어 있으면 0.7."""
    nn, nt = normalize_text(name), normalize_text(text)
    if len(nn) < 2 or not nt:
        return 0.0
    bn, bt = _bigrams(nn), _bigrams(nt)
    return round(0.7 * len(bn & bt) / len(bn), 4)


def requirement_text(r: Requirement) -> str:
    return f"{r.name}. {r.description}"


def detect_intent(item: str) -> str:
    """delete | modify | add | none (문장 의도 키워드)."""
    if any(w in item for w in DELETE_WORDS):
        return "delete"
    if any(w in item for w in MODIFY_WORDS):
        return "modify"
    if any(w in item for w in ADD_WORDS):
        return "add"
    return "none"


def infer_type(item: str) -> str:
    return (
        "non_functional"
        if any(w in item.casefold() for w in NON_FUNCTIONAL_WORDS)
        else "functional"
    )


def propose_name(item: str) -> str:
    head = re.split(r"[,:;·]|(?:을|를|은|는|이|가)\s", item, maxsplit=1)[0].strip()
    head = re.sub(
        r"(추가|신규|새로|삭제|제거|변경|수정)\s*(해\s*주세요|요청|바람|필요)?\.?$", "", head
    ).strip()
    return (head or item)[:40]


def snapshot(r: Requirement) -> dict[str, str]:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "type": r.type.value,
        "acceptance_status": r.acceptance_status.value,
    }


@dataclass
class Match:
    requirement: Requirement
    score: float


def rank_matches(item: str, existing: list[Requirement]) -> list[Match]:
    ids_in_item = set(ID_RE.findall(item))
    out: list[Match] = []
    for r in existing:
        score = max(
            similarity(item, requirement_text(r)),
            similarity(item, r.name),
            name_containment(r.name, item),
        )
        if r.id in ids_in_item:
            score = max(score, 0.95)  # ID를 직접 언급
        out.append(Match(r, score))
    out.sort(key=lambda m: m.score, reverse=True)
    return out


def classify_item(
    item: str,
    existing: list[Requirement],
    *,
    index: int,
    input_kind: InputKind = InputKind.NATURAL_LANGUAGE,
    selected_ids: list[str] | None = None,
) -> ChangeCandidate:
    cid = f"C{index:02d}"
    matches = rank_matches(item, existing)
    best = matches[0] if matches else None
    second = matches[1].score if len(matches) > 1 else 0.0
    related = [m.requirement.id for m in matches[:3] if m.score >= THRESH_RELATED]
    intent = detect_intent(item)
    schedule = SCHEDULE_RE.search(item)
    sched = schedule.group(1) if schedule else None
    selected = [s for s in (selected_ids or []) if any(r.id == s for r in existing)]
    base = dict(
        id=cid,
        related_ids=related,
        evidence=[item],
        schedule_constraint=sched,
        similarity=best.score if best else 0.0,
    )

    # 1) 버튼으로 의도가 명시된 경우: 사용자 선택을 우선하되, 선택이 없으면 자연어 규칙으로 간다.
    if input_kind == InputKind.DELETE_BUTTON and selected:
        r = next(x for x in existing if x.id == selected[0])
        return ChangeCandidate(
            classification=CandidateClass.DELETE_REQUEST,
            requirement_id=r.id,
            proposed_name=r.name,
            proposed_description=r.description,
            before=snapshot(r),
            after=None,
            rationale=f"사용자가 {r.id} 삭제를 직접 요청",
            confidence=0.95,
            needs_confirmation=True,
            source="user",
            **{**base, "similarity": 1.0},
        )
    if input_kind == InputKind.MODIFY_BUTTON and selected:
        r = next(x for x in existing if x.id == selected[0])
        after = {**snapshot(r), "description": item}
        aspects = context_delta(requirement_text(r), item)
        level, level_why = change_difficulty(item, aspects, r)
        return ChangeCandidate(
            classification=CandidateClass.MODIFY,
            requirement_id=r.id,
            proposed_name=r.name,
            proposed_description=item,
            proposed_type=r.type.value,
            before=snapshot(r),
            after=after,
            rationale=f"사용자가 {r.id} 수정을 직접 요청 (유사도 {best.score if best else 0:.2f})"
            + (f"; 문맥 차이: {', '.join(aspect_labels(aspects))}" if aspects else ""),
            confidence=0.95,
            needs_confirmation=True,
            source="user",
            change_aspects=aspects,
            difficulty=level,
            difficulty_basis=level_why,
            **{**base, "similarity": best.score if best else 0.0},
        )
    if input_kind == InputKind.ADD_BUTTON:
        if best and best.score >= THRESH_DUPLICATE:
            return ChangeCandidate(
                classification=CandidateClass.AMBIGUOUS,
                requirement_id=best.requirement.id,
                proposed_name=propose_name(item),
                proposed_description=item,
                proposed_type=infer_type(item),
                before=snapshot(best.requirement),
                after=None,
                rationale=f"추가 요청이지만 기존 {best.requirement.id}와 거의 같음 (유사도 {best.score:.2f}) — 중복 여부 확인 필요",
                confidence=0.5,
                needs_confirmation=True,
                source="user",
                **base,
            )
        aspects = context_delta("", item)
        level, level_why = change_difficulty(item, aspects, None)
        return ChangeCandidate(
            classification=CandidateClass.ADD,
            requirement_id=None,
            proposed_name=propose_name(item),
            proposed_description=item,
            proposed_type=infer_type(item),
            before=None,
            after={"name": propose_name(item), "description": item, "type": infer_type(item)},
            rationale="사용자가 추가 버튼으로 요청"
            + (f"; 관련 기존 항목 {', '.join(related)}" if related else ""),
            confidence=0.9,
            needs_confirmation=True,
            source="user",
            change_aspects=aspects,
            difficulty=level,
            difficulty_basis=level_why,
            **base,
        )

    # 2) 자연어·문서: 의도 키워드 + 유사도
    def no_change(m: Match) -> ChangeCandidate:
        return ChangeCandidate(
            classification=CandidateClass.NO_CHANGE,
            requirement_id=m.requirement.id,
            proposed_name=m.requirement.name,
            proposed_description=m.requirement.description,
            before=snapshot(m.requirement),
            after=snapshot(m.requirement),
            rationale=f"기존 {m.requirement.id}와 사실상 동일 (유사도 {m.score:.2f}) — 변경 없음",
            confidence=round(m.score, 2),
            needs_confirmation=m.score < 0.95,
            **base,
        )

    def ambiguous(reason: str, target: Match | None, conf: float = 0.4) -> ChangeCandidate:
        return ChangeCandidate(
            classification=CandidateClass.AMBIGUOUS,
            requirement_id=target.requirement.id if target else None,
            proposed_name=propose_name(item),
            proposed_description=item,
            proposed_type=infer_type(item),
            before=snapshot(target.requirement) if target else None,
            rationale=reason,
            confidence=conf,
            needs_confirmation=True,
            **base,
        )

    def modify(m: Match, why: str) -> ChangeCandidate:
        r = m.requirement
        aspects = context_delta(requirement_text(r), item)
        level, level_why = change_difficulty(item, aspects, r)
        ctx_note = (
            f"; 문맥 차이: {', '.join(aspect_labels(aspects))}"
            if aspects
            else "; 문맥 차이 없음(표현 차이)"
        )
        return ChangeCandidate(
            classification=CandidateClass.MODIFY,
            requirement_id=r.id,
            proposed_name=r.name,
            proposed_description=item,
            proposed_type=r.type.value,
            before=snapshot(r),
            after={**snapshot(r), "description": item},
            rationale=f"기존 {r.id}와 유사(유사도 {m.score:.2f}), {why}{ctx_note}. 기존 ID 유지",
            confidence=round(min(0.9, 0.4 + m.score), 2),
            needs_confirmation=True,
            change_aspects=aspects,
            difficulty=level,
            difficulty_basis=level_why,
            **base,
        )

    def add(why: str) -> ChangeCandidate:
        aspects = context_delta("", item)
        level, level_why = change_difficulty(item, aspects, None)
        return ChangeCandidate(
            classification=CandidateClass.ADD,
            requirement_id=None,
            proposed_name=propose_name(item),
            proposed_description=item,
            proposed_type=infer_type(item),
            before=None,
            after={"name": propose_name(item), "description": item, "type": infer_type(item)},
            rationale=why
            + (f"; 관련 기존 항목 {', '.join(related)}" if related else "")
            + ". ID는 승인 후 발급",
            confidence=round(0.9 - (best.score if best else 0.0) * 0.5, 2),
            needs_confirmation=True,
            change_aspects=aspects,
            difficulty=level,
            difficulty_basis=level_why,
            **base,
        )

    close_second = best is not None and second >= THRESH_RELATED and best.score - second < 0.08
    if intent == "delete":
        if best and best.score >= THRESH_RELATED and not close_second:
            return ChangeCandidate(
                classification=CandidateClass.DELETE_REQUEST,
                requirement_id=best.requirement.id,
                proposed_name=best.requirement.name,
                proposed_description=best.requirement.description,
                before=snapshot(best.requirement),
                after=None,
                rationale=f"삭제 의도 표현 + 기존 {best.requirement.id}와 유사 (유사도 {best.score:.2f}). 승인 후 '삭제' 상태로만 표시(물리 삭제 없음)",
                confidence=round(min(0.9, 0.5 + best.score), 2),
                needs_confirmation=True,
                **base,
            )
        return ambiguous(
            "삭제 의도는 있으나 대상 요구사항을 특정할 수 없음"
            + (f" (후보 {', '.join(related)})" if related else ""),
            best if best and best.score >= THRESH_RELATED else None,
            0.3,
        )
    if intent == "add":
        if best and best.score >= THRESH_SAME:
            return no_change(best)
        if best and best.score >= THRESH_MODIFY:
            return ambiguous(
                f"추가 요청이지만 기존 {best.requirement.id}의 확장(수정)일 수 있음 (유사도 {best.score:.2f}) — 수정/신규 확인 필요",
                best,
                0.45,
            )
        return add(
            "추가 의도 표현, 유사한 기존 항목 없음 (최고 유사도 "
            + (f"{best.score:.2f}" if best else "0")
            + ")"
        )
    if intent == "modify":
        if best and best.score >= THRESH_RELATED:
            if close_second:
                return ambiguous(
                    f"수정 대상이 {best.requirement.id}({best.score:.2f})와 {matches[1].requirement.id}({second:.2f}) 중 불분명",
                    best,
                )
            return modify(best, "변경 의도 표현 포함")
        return ambiguous(
            "변경 의도는 있으나 대상 요구사항을 찾지 못함 — 신규 추가인지 확인 필요", None, 0.3
        )
    # 의도 표현 없음: 유사도만으로
    if best and best.score >= THRESH_SAME:
        return no_change(best)
    if best and best.score >= THRESH_MODIFY:
        if close_second:
            return ambiguous(
                f"대상이 {best.requirement.id}({best.score:.2f})와 {matches[1].requirement.id}({second:.2f}) 중 불분명",
                best,
            )
        return modify(best, "내용 차이가 있어 수정으로 분류")
    if best and best.score >= THRESH_RELATED:
        return ambiguous(
            f"기존 {best.requirement.id}와 부분 유사(유사도 {best.score:.2f}) — 수정인지 신규 추가인지 확인 필요",
            best,
        )
    return add(
        "기존 요구사항과 유사한 항목 없음 (최고 유사도 "
        + (f"{best.score:.2f}" if best else "0")
        + ") — 신규"
    )


def classify_request(
    request_text: str,
    existing: list[Requirement],
    *,
    input_kind: InputKind = InputKind.NATURAL_LANGUAGE,
    selected_ids: list[str] | None = None,
) -> list[ChangeCandidate]:
    active = [r for r in existing if r.change_state != "deleted"]
    items = split_items(request_text)
    if input_kind in (InputKind.MODIFY_BUTTON, InputKind.DELETE_BUTTON) and selected_ids:
        # 선택한 요구사항마다 1건. 수정은 요청문 전체를 새 내용으로 본다.
        out: list[ChangeCandidate] = []
        for i, sid in enumerate(selected_ids, start=1):
            out.append(
                classify_item(
                    request_text.strip() or sid,
                    active,
                    index=i,
                    input_kind=input_kind,
                    selected_ids=[sid],
                )
            )
        return out
    return [
        classify_item(item, active, index=i, input_kind=input_kind, selected_ids=selected_ids)
        for i, item in enumerate(items, start=1)
    ]
