"""모델 공통 기반: ID 발급, 시각, 베이스 모델."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def new_id(prefix: str) -> str:
    """``<prefix>_<32 hex>`` 형식의 내부 ID (사람이 읽는 ID는 requirements/id_policy.py)."""
    return f"{prefix}_{uuid.uuid4().hex}"


class Entity(BaseModel):
    """영속 엔티티 공통 필드."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", use_enum_values=False)

    id_prefix: ClassVar[str] = "ent"

    id: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: str = "system"

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            object.__setattr__(self, "id", new_id(self.id_prefix))

    def touch(self) -> None:
        self.updated_at = utcnow()


class ProjectScoped(Entity):
    """프로젝트에 속한 엔티티."""

    project_id: str
