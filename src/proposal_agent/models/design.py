"""Screen, UnitTest, IntegrationTest, TechnologyResearch, ArchitectureComponent
(DATA_MODEL.md 4.6, 4.9, 4.10). Phase 1에서는 모델 정의만 제공한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped, utcnow
from proposal_agent.models.enums import FeasibilityVerdict, SourceTrust


class Screen(ProjectScoped):
    id_prefix: ClassVar[str] = "SCR"

    name: str
    description: str = ""
    screen_type: str = "list"
    status: str = "draft"


class UnitTest(ProjectScoped):
    id_prefix: ClassVar[str] = "UT"

    name: str
    target_component: str = ""
    description: str = ""
    status: str = "draft"


class IntegrationTest(ProjectScoped):
    id_prefix: ClassVar[str] = "IT"

    name: str
    scenario: str = ""
    description: str = ""
    status: str = "draft"


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    trust: SourceTrust = SourceTrust.UNKNOWN
    accessed_at: datetime = Field(default_factory=utcnow)
    excerpt: str = ""


class TechnologyResearch(ProjectScoped):
    id_prefix: ClassVar[str] = "TR"

    topic: str
    related_requirement_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    feasibility: FeasibilityVerdict = FeasibilityVerdict.UNKNOWN
    risks: list[str] = Field(default_factory=list)
    recommended_stack: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    verified_by_human: bool = False


class ComponentConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_component_id: str
    protocol: str = ""
    note: str = ""


class ArchitectureComponent(ProjectScoped):
    id_prefix: ClassVar[str] = "ARC"

    layer: str
    name: str
    technology: str = ""
    description: str = ""
    connections: list[ComponentConnection] = Field(default_factory=list)
    diagram_kinds: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
