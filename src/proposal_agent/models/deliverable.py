"""Deliverable, ValidationResult, Approval, Revision (DATA_MODEL.md 4.11~4.13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import Field

from proposal_agent.models.common import ProjectScoped, utcnow
from proposal_agent.models.enums import (
    ApprovalDecision,
    ApprovalTarget,
    DeliverableKind,
    IntegrityStatus,
    QaStatus,
    ValidationLevel,
    ValidationTargetType,
)


class Deliverable(ProjectScoped):
    id_prefix: ClassVar[str] = "dlv"

    revision_id: str | None = None
    kind: DeliverableKind
    file_path: str = Field(description="Output 루트 기준 상대 경로, 버전 포함 파일명")
    version: str = "v1.0"
    sha256: str = ""
    generated_from_snapshot: str | None = None
    integrity_status: IntegrityStatus = IntegrityStatus.PENDING
    qa_status: QaStatus = QaStatus.PENDING


class ValidationResult(ProjectScoped):
    id_prefix: ClassVar[str] = "val"

    target_type: ValidationTargetType
    target_id: str
    rule_id: str
    level: ValidationLevel
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    validator: str = "code:unknown"
    resolved: bool = False


class Approval(ProjectScoped):
    id_prefix: ClassVar[str] = "apr"

    target_type: ApprovalTarget
    target_id: str
    decision: ApprovalDecision
    approver: str
    comments: str = ""
    decided_at: datetime = Field(default_factory=utcnow)


class Revision(ProjectScoped):
    id_prefix: ClassVar[str] = "rev"

    number: str = Field(description="v1.0 형식")
    label: str = ""
    reason: str = ""
    change_ids: list[str] = Field(default_factory=list)
    snapshot_path: str | None = None
    approval_id: str | None = None
    parent_revision_id: str | None = None
