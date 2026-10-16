"""수정 문서 비교 (지시문 §11.1, 단계 5, A-5): Excel 정의서 → PPT 텍스트 → Word 순으로 신뢰도가 낮아진다.

- Excel 정의서(ID 기준): 같은 ID 의 내용을 비교해 **문구만 변경 / 의미 변경 / 화면 이동 / 추가 / 삭제 / 변경 없음** 으로 분류.
  ID 가 있어 확실하므로 신뢰도가 높다(0.9).
- PPT·Word 텍스트: 항목을 쪼개 기존 요구사항과 유사도로 대조한다. 판독이 불확실하므로 ``uncertain=True`` 와 신뢰도 상한(0.6/0.7)
  을 두고 사용자 확인을 요구한다.
"""

from __future__ import annotations

from typing import Any

from proposal_agent.changes.baseline_service import infer_type
from proposal_agent.changes.semantic import (
    aspect_labels,
    change_difficulty,
    classify_item,
    context_delta,
    similarity,
    snapshot,
    split_items,
)
from proposal_agent.ingest.excel_reader import parse_rows, profile_workbook
from proposal_agent.models import DocumentKind, Requirement
from proposal_agent.models.change import CandidateClass, ChangeCandidate, InputKind

# 변경 종류 (분류 세분화, 지시문 §11.1)
KIND_WORDING = "wording"  # 문구만 변경 (문맥 차이 없음)
KIND_SEMANTIC = "semantic"  # 의미 변경 (범위·규칙·수치·연계 등)
KIND_SCREEN_MOVE = "screen_move"  # 화면 이동 (화면 관점만 달라짐)
KIND_ADD = "add"
KIND_DELETE = "delete"
KIND_NONE = "none"

CHANGE_KIND_LABELS = {
    KIND_WORDING: "문구만 변경",
    KIND_SEMANTIC: "의미 변경",
    KIND_SCREEN_MOVE: "화면 이동",
    KIND_ADD: "추가",
    KIND_DELETE: "삭제",
    KIND_NONE: "변경 없음",
    "": "",
}

SOURCE_EXCEL = "excel"
SOURCE_PPTX = "pptx"
SOURCE_DOCX = "docx"
SOURCE_TEXT = "text"
_CONFIDENCE_CAP = {SOURCE_PPTX: 0.6, SOURCE_DOCX: 0.7, SOURCE_TEXT: 0.8}


def change_kind_of(classification: CandidateClass, aspects: list[str]) -> str:
    """분류와 문맥 차이 관점으로 변경 종류를 정한다."""
    if classification == CandidateClass.ADD:
        return KIND_ADD
    if classification == CandidateClass.DELETE_REQUEST:
        return KIND_DELETE
    if classification == CandidateClass.NO_CHANGE:
        return KIND_NONE
    if classification != CandidateClass.MODIFY:
        return ""
    if not aspects:
        return KIND_WORDING
    if set(aspects) <= {"screen"}:
        return KIND_SCREEN_MOVE
    return KIND_SEMANTIC


def compare_spec_workbook(
    data: bytes, existing: list[Requirement], *, file_name: str = ""
) -> tuple[list[ChangeCandidate], list[str]]:
    """수정된 요구사항 정의서(Excel) 를 기준 요구사항과 ID 기준으로 비교한다. (후보 목록, 경고) 를 돌려준다."""
    warnings: list[str] = []
    profile = profile_workbook(data, DocumentKind.REQUIREMENT_SPEC)
    if profile.needs_confirmation:
        warnings.append(
            f"{file_name or '정의서'}: 열 매핑이 불확실한 시트가 있음 — 기준 문서와 같은 양식인지 확인"
        )
    rows = parse_rows(data, profile)
    active = {r.id: r for r in existing if r.change_state != "deleted"}
    seen: set[str] = set()
    out: list[ChangeCandidate] = []
    idx = 0
    for row in rows:
        v: dict[str, Any] = row.values
        rid = str(v.get("requirement_id") or "").strip()
        name = str(v.get("name") or "").strip()
        desc = str(v.get("description") or "").strip()
        if not (rid or name or desc):
            continue
        idx += 1
        cid = f"X{idx:02d}"
        base = {"id": cid, "source": "rule", "compare_source": SOURCE_EXCEL, "uncertain": False}
        if rid and rid in active:
            seen.add(rid)
            r = active[rid]
            same_desc = _norm(desc) == _norm(r.description)
            same_name = not name or _norm(name) == _norm(r.name)
            if same_desc and same_name:
                out.append(
                    ChangeCandidate(
                        classification=CandidateClass.NO_CHANGE,
                        requirement_id=rid,
                        proposed_name=r.name,
                        proposed_description=r.description,
                        before=snapshot(r),
                        after=snapshot(r),
                        rationale=f"{rid}: 정의서 내용이 기준과 같음",
                        confidence=0.98,
                        needs_confirmation=False,
                        change_kind=KIND_NONE,
                        user_decision="reject",
                        **base,
                    )
                )
                continue
            aspects = context_delta(r.description, desc) if desc else []
            kind = change_kind_of(CandidateClass.MODIFY, aspects)
            level, level_why = change_difficulty(desc or r.description, aspects, r)
            why = {
                KIND_WORDING: "문맥 차이 없음 — 문구만 변경",
                KIND_SCREEN_MOVE: "화면 관점만 달라짐 — 화면 이동",
                KIND_SEMANTIC: "문맥 차이: " + ", ".join(aspect_labels(aspects)),
            }[kind]
            out.append(
                ChangeCandidate(
                    classification=CandidateClass.MODIFY,
                    requirement_id=rid,
                    proposed_name=name or r.name,
                    proposed_description=desc or r.description,
                    proposed_type=r.type.value,
                    before=snapshot(r),
                    after={
                        **snapshot(r),
                        "name": name or r.name,
                        "description": desc or r.description,
                    },
                    rationale=f"{rid}: 정의서 행이 기준과 다름 ({why}). ID 기준 비교",
                    confidence=0.9,
                    similarity=similarity(r.description, desc) if desc else 1.0,
                    needs_confirmation=kind != KIND_WORDING,
                    change_aspects=aspects,
                    difficulty=level if kind != KIND_WORDING else None,
                    difficulty_basis=level_why
                    if kind != KIND_WORDING
                    else "문구만 변경 — 난이도 영향 없음",
                    change_kind=kind,
                    evidence=[f"[{file_name or '정의서'} {row.sheet} {row.row}행] {desc[:200]}"],
                    **base,
                )
            )
        else:
            text = desc or name
            aspects = context_delta("", text)
            level, level_why = change_difficulty(text, aspects, None)
            out.append(
                ChangeCandidate(
                    classification=CandidateClass.ADD,
                    requirement_id=None,
                    proposed_name=name[:40] or text[:40],
                    proposed_description=text,
                    proposed_type=infer_type({**v, "_sheet": row.sheet}, {}).value,
                    rationale=(
                        f"정의서에 새 ID {rid} 행 — 기준에 없음"
                        if rid
                        else "정의서에 ID 없는 새 행"
                    )
                    + " (ID 는 승인 후 코드가 발급)",
                    confidence=0.85 if rid else 0.7,
                    needs_confirmation=True,
                    change_aspects=aspects,
                    difficulty=level,
                    difficulty_basis=level_why,
                    change_kind=KIND_ADD,
                    evidence=[f"[{file_name or '정의서'} {row.sheet} {row.row}행] {text[:200]}"],
                    **base,
                )
            )
    for rid, r in active.items():
        if rid in seen:
            continue
        idx += 1
        out.append(
            ChangeCandidate(
                id=f"X{idx:02d}",
                classification=CandidateClass.DELETE_REQUEST,
                requirement_id=rid,
                proposed_name=r.name,
                proposed_description=r.description,
                before=snapshot(r),
                rationale=f"{rid}: 수정 정의서에 행이 없음 — 삭제 요청으로 봄 (기록은 보존)",
                confidence=0.8,
                needs_confirmation=True,
                change_kind=KIND_DELETE,
                source="rule",
                compare_source=SOURCE_EXCEL,
                uncertain=False,
            )
        )
    if not out:
        warnings.append(f"{file_name or '정의서'}: 비교할 행이 없음")
    return out, warnings


def classify_document_text(
    text: str, existing: list[Requirement], *, source: str, file_name: str = ""
) -> list[ChangeCandidate]:
    """PPT·Word 등 텍스트 문서를 항목으로 쪼개 규칙 분류하되, 판독 불확실 표시와 신뢰도 상한을 둔다 (A-5)."""
    cap = _CONFIDENCE_CAP.get(source, 0.7)
    label = {SOURCE_PPTX: "PPT 텍스트", SOURCE_DOCX: "Word 텍스트"}.get(source, "문서 텍스트")
    active = [r for r in existing if r.change_state != "deleted"]
    out: list[ChangeCandidate] = []
    for i, item in enumerate(split_items(text), start=1):
        c = classify_item(item, active, index=i, input_kind=InputKind.DOCUMENT)
        c.id = f"{'P' if source == SOURCE_PPTX else 'D'}{i:02d}"
        c.compare_source = source
        c.uncertain = True
        c.confidence = round(min(c.confidence, cap), 2)
        c.needs_confirmation = True
        c.change_kind = change_kind_of(c.classification, c.change_aspects)
        c.rationale = f"{label} 비교 — 판독 불확실, 사용자 확인 필요 | " + c.rationale
        if file_name:
            c.evidence = [f"[{file_name}] {item[:200]}", *c.evidence]
        out.append(c)
    return out


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


__all__ = [
    "CHANGE_KIND_LABELS",
    "KIND_ADD",
    "KIND_DELETE",
    "KIND_NONE",
    "KIND_SCREEN_MOVE",
    "KIND_SEMANTIC",
    "KIND_WORDING",
    "SOURCE_DOCX",
    "SOURCE_EXCEL",
    "SOURCE_PPTX",
    "SOURCE_TEXT",
    "change_kind_of",
    "classify_document_text",
    "compare_spec_workbook",
]
