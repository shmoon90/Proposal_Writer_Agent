"""테스트 실행 결과 모델 (RFP_JAVA models/test_result 발췌). 실행기 결과가 유일한 통과/실패 기준이다."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class TestOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NO_TESTS = "no_tests"
    INCOMPLETE = "incomplete"
    TIMEOUT = "timeout"
    RUNNER_ERROR = "runner_error"


class TestCaseResult(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    node_id: str
    outcome: str  # passed / failed / error / skipped
    message: str = ""


class TestRunResult(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    label: str = ""
    mode: str = "docker"
    command: list[str] = Field(default_factory=list)
    started_at: datetime
    duration_seconds: float = 0.0
    exit_code: int | None = None
    timed_out: bool = False
    runner_error: str | None = None
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    cases: list[TestCaseResult] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _ignore_saved_outcome(cls, data: Any) -> Any:
        if isinstance(data, dict) and "outcome" in data:
            return {k: v for k, v in data.items() if k != "outcome"}
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outcome(self) -> TestOutcome:
        if self.runner_error is not None:
            return TestOutcome.RUNNER_ERROR
        if self.timed_out:
            return TestOutcome.TIMEOUT
        if self.failed or self.errors or (self.exit_code not in (0, 5)):
            return TestOutcome.FAILED
        if self.passed == 0:
            return TestOutcome.NO_TESTS
        if self.missing_required:
            return TestOutcome.INCOMPLETE
        return TestOutcome.PASSED

    @property
    def is_success(self) -> bool:
        return self.outcome == TestOutcome.PASSED

    @property
    def failing_cases(self) -> list[TestCaseResult]:
        return [c for c in self.cases if c.outcome in ("failed", "error")]

    def summary(self) -> str:
        text = (
            f"{self.outcome.value}: 통과 {self.passed}, 실패 {self.failed}, 오류 {self.errors}, 건너뜀 {self.skipped}"
            f" (종료 코드 {self.exit_code}, {self.duration_seconds:.1f}초)"
        )
        if self.missing_required:
            text += f", 미실행 필수 테스트 {len(self.missing_required)}개"
        if self.runner_error:
            text += f", 실행기 오류: {self.runner_error}"
        return text


__all__ = ["TestCaseResult", "TestOutcome", "TestRunResult"]
