"""에이전트 구조화 출력 스키마 (요구사항 추출·검증)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models import RequirementDraft, VerificationReport


class RequirementExtraction(BaseModel):
    """추출 에이전트 출력."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[RequirementDraft] = Field(default_factory=list)
    unresolved_items: list[str] = Field(
        default_factory=list,
        description="요구사항인지 판단하기 어려워 사람 검토가 필요한 원문 항목",
    )
    notes: str = Field(
        default="", description="청크 전반에 대한 짧은 메모 (표/이미지 누락 의심 등)"
    )


__all__ = ["RequirementExtraction", "VerificationReport"]
