"""파이프라인 단계 실행과 Gate 결과.

WORKFLOW_DESIGN.md 2절의 단계 상태(pending/running/needs_review/approved/failed/skipped)를 저장한다.
단계 정의(어떤 단계가 어떤 모드에 있는지)는 services/pipeline_service.py 의 코드 상수이고,
이 모델은 **실행 기록**만 담는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import ApprovalDecision, StepStatus


class StepDefinition(BaseModel):
    """단계 정의 (코드 상수용 값 객체)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    order: int
    title: str
    description: str = ""
    requires_gate: bool = False
    gate_title: str | None = None
    agent_role: str | None = None


class StepRun(ProjectScoped):
    """단계 실행 기록. 같은 단계를 재실행하면 ``attempt``가 증가한 새 레코드를 만든다."""

    id_prefix: ClassVar[str] = "step"

    step_key: str
    attempt: int = 1
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: dict[str, Any] | None = None
    summary: str = ""
    cost_usd: float = 0.0
    output_refs: dict[str, Any] = Field(default_factory=dict)
    # 단계 1 (지시문 §15·§16): 긴 작업의 진행률·중단 요청·재개 지점·마지막 생존 신호
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="0~1 진행률")
    progress_note: str = Field(default="", description="현재 하는 일 (화면 표시)")
    cancel_requested: bool = False
    resume_point: dict[str, Any] = Field(
        default_factory=dict,
        description="중단 시 이어서 실행할 지점 (단계별 의미, 예: 처리한 청크 수)",
    )
    heartbeat_at: datetime | None = None
    background: bool = Field(default=False, description="백그라운드 작업으로 실행되었는가")


class GateResult(ProjectScoped):
    """승인 게이트 결과. ``Approval``과 1:1로 연결된다."""

    id_prefix: ClassVar[str] = "gate"

    step_key: str
    step_run_id: str
    decision: ApprovalDecision
    approval_id: str
    comments: str = ""
