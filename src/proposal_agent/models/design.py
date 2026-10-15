"""Screen, UnitTest, IntegrationTest, ArchitectureComponent (DATA_MODEL.md 4.6, 4.10).
TechnologyResearch는 models/research.py 로 이동했다.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped


class Screen(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "SCR"

    name: str
    description: str = ""
    screen_type: str = "list"
    status: str = "draft"


class UnitTest(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "UT"

    name: str
    target_component: str = ""
    description: str = ""
    status: str = "draft"


class IntegrationTest(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "IT"

    name: str
    scenario: str = ""
    description: str = ""
    status: str = "draft"


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
