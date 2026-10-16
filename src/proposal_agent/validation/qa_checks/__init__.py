"""독립 QA 검사 패키지 (단계 1 분할). 전체 실행(run_all_checks)·게이트 판정(gate_status) 과 재수출.

호환: ``proposal_agent.validation.independent_qa`` 는 이 패키지를 그대로 재수출하는 facade 다."""

from __future__ import annotations

from collections.abc import Callable

from proposal_agent.models import QaCheck, QaResult
from proposal_agent.validation.qa_checks.common import (
    ABSTRACT_WORDS,
    ACRONYM_RE,
    BUILD_KINDS,
    COMMON_ACRONYMS,
    EVALUATION_WORDS,
    FIX_REGENERATE,
    ID_IN_TEXT_RE,
    MANDATORY_PATTERNS,
    NUMBER_CLAIM_RE,
    PROPOSAL_KINDS,
    ROMAN_RE,
    SUBMISSION_WORDS,
    VERSION_RE,
    CheckArtifacts,
    QaInputs,
    _as_date,
    _block_text_index,
    _cap,
    _check,
    _deck_paths,
    _finish,
    _ids_from_sheets,
    _is_filled,
    _kind_files,
    _looks_like_req_id,
    _not_run,
    _spec_rows,
)
from proposal_agent.validation.qa_checks.consistency import (
    _abstract_and_number_issues,
    _approach_coverage_issues,
    _base_number_tokens,
    _design_depth_issues,
    _section_label,
    _section_texts,
    _unexplained_acronyms,
    check_consistency_rules,
)
from proposal_agent.validation.qa_checks.editability import _group_depth, check_editability
from proposal_agent.validation.qa_checks.files import (
    _check_gantt,
    _content_slide_count,
    _invalid_ids,
    _page_limit_issues,
    _render_issues,
    _template_check,
    _template_size,
    run_file_checks,
)
from proposal_agent.validation.qa_checks.rfp import check_rfp_fit
from proposal_agent.validation.qa_checks.tech import check_tech_feasibility


# --- 실행·게이트 ---------------------------------------------------------------------------------
def run_all_checks(inp: QaInputs) -> tuple[list[QaCheck], CheckArtifacts]:
    file_checks, art = run_file_checks(inp)
    sub_text = "\n".join(art.ppt_texts.get("submission", []))
    checks = [
        *check_rfp_fit(inp, sub_text),
        *check_tech_feasibility(inp, art.ppt_texts),
        *check_consistency_rules(inp, art),
        *file_checks,
        *check_editability(inp, art),
    ]
    return checks, art


GATE_SCOPES: dict[str, Callable[[QaCheck], bool]] = {
    "gate2": lambda c: c.gate == "gate2",
    "gate3": lambda c: c.gate == "gate3",
    "gate4": lambda c: c.gate == "gate4",
    "gate5": lambda c: True,
}


def gate_status(checks: list[QaCheck], gate_key: str) -> tuple[str, list[str]]:
    """게이트별 판정 (코드). FAIL: 필수 항목 실패. NEEDS_HUMAN_REVIEW: 검토 필요·미실행·비필수 실패. PASS: 그 외.
    gate5(최종 독립 QA)는 자동으로 PASS가 되지 않는다 — 사람 승인이 필요하다."""
    scope = [c for c in checks if GATE_SCOPES[gate_key](c) and c.applicable]
    reasons: list[str] = []
    fails = [c for c in scope if c.executed and c.final_result == QaResult.FAIL and c.mandatory]
    soft = [
        c
        for c in scope
        if (c.executed and c.final_result == QaResult.FAIL and not c.mandatory)
        or c.final_result == QaResult.NEEDS_HUMAN_REVIEW
        or not c.executed
    ]
    if fails:
        reasons.append(f"필수 검증 실패 {len(fails)}건: " + ", ".join(c.check_id for c in fails))
        return "FAIL", reasons
    if soft:
        reasons.append(f"검토 필요 {len(soft)}건: " + ", ".join(c.check_id for c in soft))
        return "NEEDS_HUMAN_REVIEW", reasons
    if gate_key == "gate5":
        reasons.append("자동 검증 모두 통과 — 최종 판정은 사람 승인이 필요합니다.")
        return "NEEDS_HUMAN_REVIEW", reasons
    reasons.append(f"검증 {len(scope)}건 통과")
    return "PASS", reasons


__all__ = [
    "ABSTRACT_WORDS",
    "ACRONYM_RE",
    "BUILD_KINDS",
    "COMMON_ACRONYMS",
    "CheckArtifacts",
    "EVALUATION_WORDS",
    "FIX_REGENERATE",
    "GATE_SCOPES",
    "ID_IN_TEXT_RE",
    "MANDATORY_PATTERNS",
    "NUMBER_CLAIM_RE",
    "PROPOSAL_KINDS",
    "QaInputs",
    "ROMAN_RE",
    "SUBMISSION_WORDS",
    "VERSION_RE",
    "_abstract_and_number_issues",
    "_approach_coverage_issues",
    "_as_date",
    "_base_number_tokens",
    "_block_text_index",
    "_cap",
    "_check",
    "_check_gantt",
    "_content_slide_count",
    "_deck_paths",
    "_design_depth_issues",
    "_finish",
    "_group_depth",
    "_ids_from_sheets",
    "_invalid_ids",
    "_is_filled",
    "_kind_files",
    "_looks_like_req_id",
    "_not_run",
    "_page_limit_issues",
    "_render_issues",
    "_section_label",
    "_section_texts",
    "_spec_rows",
    "_template_check",
    "_template_size",
    "_unexplained_acronyms",
    "check_consistency_rules",
    "check_editability",
    "check_rfp_fit",
    "check_tech_feasibility",
    "gate_status",
    "run_all_checks",
    "run_file_checks",
]
