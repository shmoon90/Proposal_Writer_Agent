"""파이프라인 단계 정의와 실행 상태 관리 (WORKFLOW_DESIGN.md 2~4절).

Phase 1 범위: 단계 정의(모드별), 단계 실행 기록(StepRun) 생성·상태 전이, 게이트 결정(Approval +
GateResult) 기록, 진행 요약과 미해결 이슈 조회. 실제 단계 실행 로직(에이전트·생성기)은 이후 Phase에서
``run_step``에 연결된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from proposal_agent.config.errors import PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import (
    ActorKind,
    Approval,
    ApprovalDecision,
    ApprovalTarget,
    GateResult,
    Project,
    ProjectMode,
    StepDefinition,
    StepRun,
    StepStatus,
    ValidationLevel,
    ValidationResult,
    utcnow,
)
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.pipeline")


def _steps(*rows: tuple[str, str, str | None, str | None]) -> tuple[StepDefinition, ...]:
    out: list[StepDefinition] = []
    for i, (key, title, gate_title, agent_role) in enumerate(rows, start=1):
        out.append(
            StepDefinition(
                key=key,
                order=i,
                title=title,
                requires_gate=gate_title is not None,
                gate_title=gate_title,
                agent_role=agent_role,
            )
        )
    return tuple(out)


PROPOSAL_STEPS = _steps(
    ("upload", "RFP 업로드", None, None),
    ("extract", "문서 추출", None, None),
    ("rfp_analysis", "RFP 분석", None, "rfp_analyst"),
    ("req_extract", "요구사항 추출", None, "requirement_extractor"),
    ("req_verify", "독립 검증", "게이트 1: 요구사항 기준선 승인", "requirement_verifier"),
    ("tech_research", "기술 조사·구현 가능성", "게이트 2: 조사 결과 검토", "tech_researcher"),
    ("architecture", "아키텍처 설계", None, "architect"),
    ("wbs_schedule", "WBS·일정 계산", None, "planner"),
    ("staffing", "인력 투입계획", "게이트 3: 계획 승인", None),
    ("generate_docs", "문서 생성 (Excel·다이어그램)", None, None),
    ("proposal_ppt", "제안 문안·PPT 생성", None, "proposal_writer"),
    ("qa", "통합 QA (독립 검증)", "게이트 5: 최종 독립 QA 승인", "qa_reviewer"),
    ("finalize", "최종 산출물 확정", None, None),
)

BUILD_STEPS = _steps(
    ("upload", "기존 산출물 업로드", None, None),
    ("doc_structure", "문서 구조 분석·컬럼 매핑", None, None),
    ("load_baseline", "기준 데이터 적재", None, None),
    ("change_request", "변경 요청 등록", None, None),
    ("diff", "결정적·의미 비교", None, "semantic_differ"),
    ("impact", "영향 분석·재계산", "변경 승인 (사람, Approval 기록)", None),
    ("apply", "기준 데이터 적용", None, None),
    ("regenerate", "문서 갱신 (새 버전)", None, None),
    ("qa", "변경 후 통합 QA", "게이트 5: 최종 독립 QA 승인", "qa_reviewer"),
    ("finalize", "Revision 확정", None, None),
)

STEPS_BY_MODE: dict[ProjectMode, tuple[StepDefinition, ...]] = {
    ProjectMode.PROPOSAL: PROPOSAL_STEPS,
    ProjectMode.BUILD: BUILD_STEPS,
}

# 허용되는 단계 상태 전이
STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.SKIPPED}),
    StepStatus.RUNNING: frozenset(
        {StepStatus.NEEDS_REVIEW, StepStatus.APPROVED, StepStatus.FAILED}
    ),
    StepStatus.NEEDS_REVIEW: frozenset({StepStatus.APPROVED, StepStatus.FAILED}),
    StepStatus.FAILED: frozenset(),
    StepStatus.APPROVED: frozenset(),
    StepStatus.SKIPPED: frozenset(),
}


@dataclass(frozen=True)
class StepView:
    definition: StepDefinition
    run: StepRun | None

    @property
    def status(self) -> StepStatus:
        return self.run.status if self.run else StepStatus.PENDING


@dataclass(frozen=True)
class Issue:
    level: str
    source: str
    message: str
    resolution: str | None = None
    entity_id: str | None = None


class PipelineService:
    def __init__(self, repos: Repositories, audit: AuditService) -> None:
        self._repos = repos
        self._audit = audit

    # --- 정의 ------------------------------------------------------------------------
    @staticmethod
    def definitions(mode: ProjectMode) -> tuple[StepDefinition, ...]:
        return STEPS_BY_MODE[mode]

    @classmethod
    def definition(cls, mode: ProjectMode, step_key: str) -> StepDefinition:
        for d in cls.definitions(mode):
            if d.key == step_key:
                return d
        raise ValidationError(f"알 수 없는 단계: {step_key}", cause=f"mode={mode}")

    # --- 조회 ------------------------------------------------------------------------
    def overview(self, project: Project) -> list[StepView]:
        latest = self._repos.step_runs.latest_by_step(project.id)
        return [StepView(d, latest.get(d.key)) for d in self.definitions(project.mode)]

    def current_step(self, project: Project) -> StepView | None:
        """첫 번째 미승인·미건너뜀 단계."""
        for view in self.overview(project):
            if view.status not in (StepStatus.APPROVED, StepStatus.SKIPPED):
                return view
        return None

    def progress(self, project: Project) -> tuple[int, int]:
        views = self.overview(project)
        done = sum(1 for v in views if v.status in (StepStatus.APPROVED, StepStatus.SKIPPED))
        return done, len(views)

    def gate_history(self, project: Project) -> list[tuple[GateResult, Approval]]:
        gates = self._repos.gates.find(project.id, order_by="created_at", descending=True)
        out: list[tuple[GateResult, Approval]] = []
        for g in gates:
            out.append((g, self._repos.approvals.get(g.approval_id)))
        return out

    def open_issues(self, project: Project) -> list[Issue]:
        """실패 단계 + 미해결 검증 결과(error/warning) + 최근 오류 감사 이벤트."""
        issues: list[Issue] = []
        for view in self.overview(project):
            if view.run and view.run.status == StepStatus.FAILED:
                err = view.run.error or {}
                issues.append(
                    Issue(
                        level="error",
                        source=f"단계: {view.definition.title}",
                        message=err.get("message", "단계 실행 실패"),
                        resolution=err.get("resolution"),
                        entity_id=view.run.id,
                    )
                )
        for v in self._repos.validations.find(project.id, resolved=False):
            if v.level in (ValidationLevel.ERROR, ValidationLevel.WARNING):
                issues.append(
                    Issue(
                        level=str(v.level),
                        source=f"검증: {v.rule_id}",
                        message=v.message,
                        resolution=v.detail.get("resolution") if v.detail else None,
                        entity_id=v.id,
                    )
                )
        return issues

    # --- 실행 상태 전이 ------------------------------------------------------------------
    def start_step(self, project: Project, step_key: str, *, actor: str = "system") -> StepRun:
        definition = self.definition(project.mode, step_key)
        prev = self._repos.step_runs.latest(project.id, step_key)
        if prev and prev.status == StepStatus.RUNNING:
            raise ValidationError(
                f"단계 '{definition.title}'가 이미 실행 중입니다.",
                cause=f"run={prev.id}",
                resolution="완료 또는 실패 처리 후 다시 시작하십시오.",
            )
        run = StepRun(
            project_id=project.id,
            step_key=step_key,
            attempt=(prev.attempt + 1) if prev else 1,
            status=StepStatus.RUNNING,
            started_at=utcnow(),
            created_by=actor,
        )
        self._repos.step_runs.insert(run)
        self._audit.record(
            project.id,
            "step.started",
            actor=actor,
            entity_type="StepRun",
            entity_id=run.id,
            payload={"step": step_key, "attempt": run.attempt},
        )
        return run

    def _transition(self, run: StepRun, new: StepStatus) -> None:
        if new not in STEP_TRANSITIONS[run.status]:
            raise ValidationError(
                f"허용되지 않는 단계 상태 전이: {run.status} → {new}",
                cause=f"run={run.id}",
                resolution="현재 상태에서 가능한 작업만 수행하십시오.",
            )
        run.status = new

    def complete_step(
        self,
        project: Project,
        run: StepRun,
        *,
        summary: str = "",
        output_refs: dict[str, Any] | None = None,
        cost_usd: float = 0.0,
        actor: str = "system",
    ) -> StepRun:
        """실행 완료. 게이트가 있는 단계는 ``needs_review``, 없으면 바로 ``approved``."""
        definition = self.definition(project.mode, run.step_key)
        self._transition(
            run, StepStatus.NEEDS_REVIEW if definition.requires_gate else StepStatus.APPROVED
        )
        run.finished_at = utcnow()
        run.summary = summary
        run.output_refs = output_refs or {}
        run.cost_usd = cost_usd
        self._repos.step_runs.update(run)
        self._audit.record(
            project.id,
            "step.completed",
            actor=actor,
            entity_type="StepRun",
            entity_id=run.id,
            payload={"step": run.step_key, "status": str(run.status), "cost_usd": cost_usd},
        )
        return run

    def fail_step(
        self, project: Project, run: StepRun, error: BaseException, *, actor: str = "system"
    ) -> StepRun:
        self._transition(run, StepStatus.FAILED)
        run.finished_at = utcnow()
        run.error = (
            error.to_dict()
            if isinstance(error, PWAError)
            else {
                "type": type(error).__name__,
                "message": str(error),
                "cause": str(error),
                "resolution": PWAError.default_resolution,
            }
        )
        self._repos.step_runs.update(run)
        self._audit.record_error(
            project.id,
            "step.failed",
            error,
            actor=actor,
            entity_type="StepRun",
            entity_id=run.id,
            payload={"step": run.step_key},
        )
        return run

    def skip_step(
        self, project: Project, step_key: str, *, reason: str, actor: str = "user"
    ) -> StepRun:
        definition = self.definition(project.mode, step_key)
        if definition.requires_gate:
            raise ValidationError(
                f"게이트가 있는 단계 '{definition.title}'는 건너뛸 수 없습니다.",
                resolution="단계를 실행하고 승인 절차를 거치십시오.",
            )
        prev = self._repos.step_runs.latest(project.id, step_key)
        run = StepRun(
            project_id=project.id,
            step_key=step_key,
            attempt=(prev.attempt + 1) if prev else 1,
            status=StepStatus.SKIPPED,
            summary=reason,
            created_by=actor,
        )
        self._repos.step_runs.insert(run)
        self._audit.record(
            project.id,
            "step.skipped",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="StepRun",
            entity_id=run.id,
            payload={"step": step_key, "reason": reason},
        )
        return run

    # --- 게이트 ------------------------------------------------------------------------
    def decide_gate(
        self,
        project: Project,
        run: StepRun,
        *,
        decision: ApprovalDecision,
        approver: str,
        comments: str = "",
    ) -> GateResult:
        """게이트 결정을 기록한다. 반려는 사유가 필수이며 단계를 ``failed``로 바꾼다."""
        definition = self.definition(project.mode, run.step_key)
        if not definition.requires_gate:
            raise ValidationError(f"단계 '{definition.title}'에는 게이트가 없습니다.")
        if run.status != StepStatus.NEEDS_REVIEW:
            raise ValidationError(
                "검토 대기 상태의 단계만 승인·반려할 수 있습니다.",
                cause=f"status={run.status}",
            )
        if decision == ApprovalDecision.REJECTED and not comments.strip():
            raise ValidationError("반려 사유를 입력하십시오.", cause="comments 비어 있음")
        approval = Approval(
            project_id=project.id,
            target_type=ApprovalTarget.STEP,
            target_id=run.id,
            decision=decision,
            approver=approver,
            comments=comments,
            created_by=approver,
        )
        self._repos.approvals.insert(approval)
        gate = GateResult(
            project_id=project.id,
            step_key=run.step_key,
            step_run_id=run.id,
            decision=decision,
            approval_id=approval.id,
            comments=comments,
            created_by=approver,
        )
        self._repos.gates.insert(gate)
        self._transition(
            run, StepStatus.FAILED if decision == ApprovalDecision.REJECTED else StepStatus.APPROVED
        )
        if decision == ApprovalDecision.REJECTED:
            run.error = {
                "type": "GateRejected",
                "message": f"{definition.gate_title} 반려",
                "cause": comments,
                "resolution": "지적 사항을 반영한 뒤 단계를 재실행하십시오.",
            }
        self._repos.step_runs.update(run)
        self._audit.record(
            project.id,
            "gate.decided",
            actor=approver,
            actor_kind=ActorKind.USER,
            entity_type="GateResult",
            entity_id=gate.id,
            payload={"step": run.step_key, "decision": str(decision), "comments": comments},
        )
        return gate

    # --- 검증 결과 ------------------------------------------------------------------
    def add_validation(self, result: ValidationResult) -> ValidationResult:
        return self._repos.validations.insert(result)

    def resolve_validation(
        self, project: Project, validation_id: str, *, actor: str = "user"
    ) -> ValidationResult:
        v = self._repos.validations.get(validation_id)
        v.resolved = True
        self._repos.validations.update(v)
        self._audit.record(
            project.id,
            "validation.resolved",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ValidationResult",
            entity_id=v.id,
        )
        return v
