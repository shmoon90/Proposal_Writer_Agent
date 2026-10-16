"""제안 전략 엔티티 (지시문 §7.1·§17, 단계 1).

전략 브리프(`strategy_planner`) 의 전략 항목을 안정적인 ID(STR-001) 로 관리해 요구사항·화면·설계·WBS 와 추적한다.
근거 없는 우위 주장·확인되지 않은 수치는 ``evidence`` 에 출처가 있어야 하며, 없으면 ``unverified_claims`` 로 남긴다.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped


class ProposalStrategy(ProjectScoped):
    id_prefix: ClassVar[str] = "STR"

    code: str = Field(default="", description="문서 표시 ID (예: STR-001)")
    title: str = Field(min_length=1, description="전략명 (결론형)")
    client_problem: str = Field(default="", description="발주처 관점의 문제 또는 목표")
    rfp_basis: list[str] = Field(default_factory=list, description="RFP 근거 (블록 ID·인용)")
    differentiator: str = Field(default="", description="제안 차별성")
    approach: str = Field(default="", description="구현 방법")
    technologies: list[str] = Field(default_factory=list, description="적용 기술·아키텍처")
    expected_effects: list[str] = Field(
        default_factory=list, description="기대 효과 (근거 있는 것만)"
    )
    risks: list[str] = Field(default_factory=list, description="위험·전제 조건")
    evidence: list[str] = Field(default_factory=list, description="증명 가능한 근거 (출처·ID)")
    unverified_claims: list[str] = Field(
        default_factory=list, description="근거 없어 사람 확인 필요"
    )
    related_requirement_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="draft", description="draft | reviewed | approved | dropped")
    version: int = 1
    source: str = Field(default="agent", description="agent | user")


__all__ = ["ProposalStrategy"]
