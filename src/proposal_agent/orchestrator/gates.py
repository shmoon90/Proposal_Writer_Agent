"""Gate 상태 검사 (코드). LLM이 "통과"라고 말하는 것은 아무 효력이 없다.

- 유효 상태: 최신 ``GateEvaluation``이 PASS면 PASS. NEEDS_HUMAN_REVIEW이고 그 평가에 대한 사람 승인(Approval)이
  있으면 PASS(승인 ID 기록). FAIL은 사람이 승인할 수 없다(재처리 필요).
- ``require(project, gate_key)``: PASS가 아니면 ``GateBlockedError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from proposal_agent.config.errors import PWAError, ValidationError
from proposal_agent.models import (
    ActorKind,
    Approval,
    ApprovalDecision,
    ApprovalTarget,
    GateEvaluation,
    GateStatus,
    Project,
)
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

GATE_TITLES: dict[str, str] = {
    "gate0": "Gate 0: 문서 추출 품질",
    "gate1": "Gate 1: 요구사항 추출 및 독립 검증",
    "gate4": "Gate 4: 산출물 QA 및 최종 승인",
}


class GateBlockedError(PWAError):
    default_resolution = (
        "게이트 사유를 해결하고 재평가하거나, 검토 필요 상태라면 사람이 승인하십시오."
    )


@dataclass(frozen=True)
class GateState:
    gate_key: str
    status: GateStatus
    evaluation: GateEvaluation | None
    approved_by: str | None = None

    @property
    def title(self) -> str:
        return GATE_TITLES.get(self.gate_key, self.gate_key)

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS


class GateService:
    def __init__(self, repos: Repositories, audit: AuditService) -> None:
        self._repos = repos
        self._audit = audit

    def state(self, project: Project, gate_key: str) -> GateState:
        ev = self._repos.gate_evaluations.latest(project.id, gate_key)
        if ev is None:
            return GateState(gate_key, GateStatus.FAIL, None)
        if ev.status == GateStatus.NEEDS_HUMAN_REVIEW and ev.approval_id:
            approval = self._repos.approvals.get(ev.approval_id)
            if approval.decision != ApprovalDecision.REJECTED:
                return GateState(gate_key, GateStatus.PASS, ev, approved_by=approval.approver)
        return GateState(gate_key, ev.status, ev)

    def require(self, project: Project, gate_key: str) -> GateState:
        st = self.state(project, gate_key)
        if not st.passed:
            reasons = st.evaluation.reasons if st.evaluation else ["아직 평가되지 않았습니다."]
            raise GateBlockedError(
                f"{st.title} 미통과 ({st.status}).",
                cause="; ".join(reasons),
                detail={"gate": gate_key, "status": str(st.status)},
            )
        return st

    def approve_human_review(
        self, project: Project, gate_key: str, *, approver: str, comments: str
    ) -> GateState:
        """NEEDS_HUMAN_REVIEW 상태를 사람이 검토 후 통과시킨다. 사유(comments) 필수. FAIL은 승인 불가."""
        ev = self._repos.gate_evaluations.latest(project.id, gate_key)
        if ev is None:
            raise ValidationError(f"{GATE_TITLES.get(gate_key, gate_key)}: 평가 결과가 없습니다.")
        if ev.status == GateStatus.FAIL:
            raise ValidationError(
                f"{GATE_TITLES.get(gate_key, gate_key)}: FAIL 상태는 승인으로 통과시킬 수 없습니다.",
                cause="; ".join(ev.reasons),
                resolution="원인을 해결하고 재처리한 뒤 다시 평가하십시오.",
            )
        if ev.status == GateStatus.PASS:
            return self.state(project, gate_key)
        if not comments.strip():
            raise ValidationError(
                "검토 의견을 입력하십시오. 어떤 근거로 통과시키는지 기록해야 합니다."
            )
        approval = Approval(
            project_id=project.id,
            target_type=ApprovalTarget.STEP,
            target_id=ev.id,
            decision=ApprovalDecision.APPROVED_WITH_COMMENTS,
            approver=approver,
            comments=comments,
            created_by=approver,
        )
        self._repos.approvals.insert(approval)
        ev.approval_id = approval.id
        self._repos.gate_evaluations.update(ev)
        self._audit.record(
            project.id,
            "gate.human_approved",
            actor=approver,
            actor_kind=ActorKind.USER,
            entity_type="GateEvaluation",
            entity_id=ev.id,
            payload={"gate": gate_key, "comments": comments},
        )
        return self.state(project, gate_key)

    def reject_human_review(
        self, project: Project, gate_key: str, *, approver: str, comments: str
    ) -> GateState:
        ev = self._repos.gate_evaluations.latest(project.id, gate_key)
        if ev is None or ev.status != GateStatus.NEEDS_HUMAN_REVIEW:
            raise ValidationError("검토 대기 상태의 게이트만 반려할 수 있습니다.")
        if not comments.strip():
            raise ValidationError("반려 사유를 입력하십시오.")
        approval = Approval(
            project_id=project.id,
            target_type=ApprovalTarget.STEP,
            target_id=ev.id,
            decision=ApprovalDecision.REJECTED,
            approver=approver,
            comments=comments,
            created_by=approver,
        )
        self._repos.approvals.insert(approval)
        rejected = GateEvaluation(
            project_id=project.id,
            gate_key=gate_key,
            status=GateStatus.FAIL,
            reasons=[f"사람 검토 반려: {comments}", *ev.reasons],
            metrics=ev.metrics,
            evaluated_by=f"user:{approver}",
            approval_id=approval.id,
            step_run_id=ev.step_run_id,
        )
        self._repos.gate_evaluations.insert(rejected)
        self._audit.record(
            project.id,
            "gate.human_rejected",
            actor=approver,
            actor_kind=ActorKind.USER,
            entity_type="GateEvaluation",
            entity_id=rejected.id,
            payload={"gate": gate_key, "comments": comments},
        )
        return self.state(project, gate_key)
