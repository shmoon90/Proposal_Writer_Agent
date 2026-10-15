"""Project, SourceDocument (DATA_MODEL.md 4.1~4.2)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from pydantic import Field, field_validator, model_validator

from proposal_agent.models.common import Entity, ProjectScoped
from proposal_agent.models.enums import DocumentKind, ExtractionMethod, ProjectMode, ProjectStatus


class Project(Entity):
    id_prefix: ClassVar[str] = "prj"

    name: str = Field(min_length=1, max_length=200)
    mode: ProjectMode
    status: ProjectStatus = ProjectStatus.CREATED
    client_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    output_dir: str = Field(description="Output 루트 기준 프로젝트 폴더명")
    workspace_dir: str = Field(description="workspace 루트 기준 폴더명")
    baseline_revision_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("프로젝트명은 비어 있을 수 없습니다.")
        return v

    @model_validator(mode="after")
    def _check_dates(self) -> Project:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        return self

    @property
    def duration_days(self) -> int | None:
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None


class SourceDocument(ProjectScoped):
    id_prefix: ClassVar[str] = "doc"

    kind: DocumentKind
    file_name: str
    stored_path: str = Field(description="Output 루트 기준 상대 경로")
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    page_count: int | None = None
    extraction_method: ExtractionMethod = ExtractionMethod.PENDING
    extracted_text_path: str | None = None
    column_mapping: dict[str, Any] | None = None
    is_required_input: bool = False
    template_purpose: str | None = Field(
        default=None,
        description="제안서 템플릿 용도: submission | presentation (None이면 용지 방향으로 추정)",
    )
