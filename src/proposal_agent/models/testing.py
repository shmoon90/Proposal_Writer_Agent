"""테스트 케이스·결함 엔티티 (지시문 §14·§17, 단계 1).

단계 7(테스트 계획·실행·결함) 에서 채워지며, 단계 1 에서는 안정적 ID(TC-001, DEF-001) 와 상태 전이·추적 필드만 둔다.
테스트하지 않은 케이스는 ``unverified`` 로 남고 완료로 표시되지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import DefectStatus, TestCaseStatus, TestLevel


class TestCase(ProjectScoped):
    id_prefix: ClassVar[str] = "TC"

    code: str = Field(default="", description="문서 표시 ID (예: TC-001)")
    name: str = Field(min_length=1)
    level: TestLevel = TestLevel.UNIT
    purpose: str = ""
    preconditions: list[str] = Field(default_factory=list)
    input_data: str = ""
    procedure: list[str] = Field(default_factory=list, description="실행 방법 (단계)")
    expected_result: str = ""
    actual_result: str = ""
    status: TestCaseStatus = TestCaseStatus.DRAFT
    error_detail: str = ""
    fix_note: str = ""
    rerun_result: str = ""
    executed_at: datetime | None = None
    executed_by: str = ""
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_screen_ids: list[str] = Field(default_factory=list)
    related_api_ids: list[str] = Field(default_factory=list)
    related_module_ids: list[str] = Field(default_factory=list)
    defect_ids: list[str] = Field(default_factory=list)
    version: int = 1


class Defect(ProjectScoped):
    id_prefix: ClassVar[str] = "DEF"

    code: str = Field(default="", description="문서 표시 ID (예: DEF-001)")
    title: str = Field(min_length=1)
    severity: str = Field(default="medium", description="critical | high | medium | low")
    status: DefectStatus = DefectStatus.OPEN
    reproduction: str = Field(default="", description="재현 조건")
    cause: str = Field(default="", description="원인 분석")
    impact_scope: str = Field(default="", description="영향 범위")
    fix_plan: str = ""
    fix_note: str = ""
    retest_result: str = ""
    regression_note: str = ""
    found_in_test_case_id: str | None = None
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_module_ids: list[str] = Field(default_factory=list)
    assignee: str = ""
    due_date: datetime | None = None
    resolved_at: datetime | None = None
    version: int = 1


__all__ = ["Defect", "TestCase"]
