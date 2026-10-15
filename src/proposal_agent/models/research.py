"""기술 조사 결과와 에이전트 실행 산출물 모델 (Phase 3).

- ``TechnologyResearch``: 조사 주제별 기록. 출처 URL·문서명·제품·버전·조사일·확인된 사실·적용 조건·미확인 사항·영향을 모두 남긴다.
- ``AgentOutput``: 역할별 구조화 출력 파일(JSON) 기록. 다른 역할이 ``get_prior_output``으로 재사용한다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped, utcnow
from proposal_agent.models.enums import FeasibilityVerdict, SourceTrust


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    product: str = ""
    version: str = ""
    trust: SourceTrust = SourceTrust.UNKNOWN
    trust_by_rule: SourceTrust | None = Field(
        default=None, description="코드(도메인 규칙)가 판정한 신뢰도"
    )
    accessed_at: datetime = Field(default_factory=utcnow)
    excerpt: str = ""


class TechAlternativeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    scores: dict[str, str] = Field(default_factory=dict)
    license_and_cost: str = ""
    notes: str = ""
    sources: list[ResearchSource] = Field(default_factory=list)


class FeasibilityComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    rfp_specified: str | None = None
    alternatives: list[TechAlternativeRecord] = Field(default_factory=list)
    recommendation: str = ""
    rationale: str = ""
    unverified_items: list[str] = Field(default_factory=list)


class TechnologyResearch(ProjectScoped):
    id_prefix: ClassVar[str] = "TR"

    topic: str
    related_requirement_ids: list[str] = Field(default_factory=list)
    investigated_at: date = Field(default_factory=lambda: utcnow().date())
    summary: str = ""
    confirmed_facts: list[str] = Field(default_factory=list)
    applicability_conditions: list[str] = Field(default_factory=list)
    unverified_items: list[str] = Field(default_factory=list)
    impact_on_implementation: str = ""
    impact_on_proposal: str = ""
    feasibility: FeasibilityVerdict = FeasibilityVerdict.UNKNOWN
    risks: list[str] = Field(default_factory=list)
    recommended_stack: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    verified_by_human: bool = False
    agent_output_id: str | None = None

    @property
    def has_sources(self) -> bool:
        return bool(self.sources)


class FeasibilityStudy(ProjectScoped):
    id_prefix: ClassVar[str] = "FS"

    comparisons: list[FeasibilityComparisonRecord] = Field(default_factory=list)
    notes: str = ""
    agent_output_id: str | None = None


class AgentOutput(ProjectScoped):
    id_prefix: ClassVar[str] = "aout"

    role: str
    version: str = "v1.0"
    file_path: str = Field(description="Output 루트 기준 상대 경로 (JSON)")
    sha256: str = ""
    step_run_id: str | None = None
    cost_usd: float = 0.0
    num_turns: int = 0
    tool_calls: int = 0
    attempts: int = 1
    inputs_used: list[str] = Field(default_factory=list, description="재사용한 이전 역할 키")
    summary: dict[str, Any] = Field(default_factory=dict)
