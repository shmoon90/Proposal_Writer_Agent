"""AuditEvent (DATA_MODEL.md 4.13). 추가 전용(append-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped, utcnow
from proposal_agent.models.enums import ActorKind


class AuditEvent(ProjectScoped):
    id_prefix: ClassVar[str] = "evt"

    at: datetime = Field(default_factory=utcnow)
    actor_kind: ActorKind = ActorKind.SYSTEM
    actor: str = "system"
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None
