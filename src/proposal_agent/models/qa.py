"""통합 QA(독립 검증) 모델 (Phase 7).

- ``QaCheck``: 검증 항목 1건. 검증 ID·대상·기준·결과·발견 문제·관련 요구사항·영향 파일·수정 제안·수정 여부·재검증 결과를 기록한다.
- ``QaRun``: 통합 QA 실행 1회. 검증 항목 전체, 게이트 결과, 건수, 보고서 경로, 최종 판정을 보존한다.
결과는 PASS / FAIL / NEEDS_HUMAN_REVIEW 세 가지뿐이며, 실행하지 않은 항목은 ``executed=False``로 따로 표시한다(통과로 세지 않는다).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped


class QaResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class QaCategory(StrEnum):
    RFP_FIT = "rfp_fit"
    TECH_FEASIBILITY = "tech_feasibility"
    CONSISTENCY = "consistency"
    FILE_QUALITY = "file_quality"
    AGENT_REVIEW = "agent_review"


class QaCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str = Field(description="예: QA-RFP-01")
    category: QaCategory
    target: str = Field(description="검증 대상 (문서·데이터)")
    criteria: str = Field(description="검증 기준")
    result: QaResult = QaResult.NEEDS_HUMAN_REVIEW
    executed: bool = True
    applicable: bool = Field(
        default=True, description="False면 이 모드에 해당 없음(미실행이지만 게이트를 막지 않음)"
    )
    not_run_reason: str = ""
    issues: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    fix_suggestion: str = ""
    fixable: str | None = Field(
        default=None, description="자동 수정 방식 키 (예: regenerate). None이면 자동 수정 불가"
    )
    fix_applied: bool | None = Field(
        default=None, description="None=시도 안 함, True=수정 반영, False=수정 보류"
    )
    fix_detail: str = ""
    reverified: QaResult | None = None
    attempts: int = 0
    mandatory: bool = Field(default=True, description="필수 검증 여부 (실패 시 최종 완료 불가)")
    gate: str = Field(default="gate5", description="이 항목이 속한 게이트 키")
    evaluated_by: str = "code:validation.independent_qa"

    @property
    def final_result(self) -> QaResult:
        return self.reverified if self.reverified is not None else self.result


class QaRun(ProjectScoped):
    id_prefix: ClassVar[str] = "qar"

    step_run_id: str | None = None
    mode: str = ""
    scope: list[str] = Field(default_factory=list)
    checks: list[QaCheck] = Field(default_factory=list)
    gates: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    fix_rounds: int = 0
    max_fix_rounds: int = 0
    fixes: list[str] = Field(default_factory=list)
    tests_executed: list[dict[str, Any]] = Field(
        default_factory=list, description="외부 테스트 실행 결과 (pytest 등, 실제 실행분만)"
    )
    unresolved_risks: list[str] = Field(default_factory=list)
    approval_needed: list[str] = Field(default_factory=list)
    verdict: str = Field(
        default="NEEDS_HUMAN_REVIEW", description="PASS | FAIL | NEEDS_HUMAN_REVIEW"
    )
    report_path: str | None = None
    json_path: str | None = None
    agent_review: dict[str, Any] | None = None

    def by_category(self, category: QaCategory) -> list[QaCheck]:
        return [c for c in self.checks if c.category == category]
