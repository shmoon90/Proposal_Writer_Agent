"""services.pipeline_service: 모드별 단계 정의, 상태 전이, 게이트, 이슈."""

from __future__ import annotations

import pytest

from proposal_agent.config import ValidationError
from proposal_agent.models import (
    ApprovalDecision,
    Project,
    ProjectMode,
    StepStatus,
    ValidationLevel,
    ValidationResult,
    ValidationTargetType,
)
from proposal_agent.services import Services
from proposal_agent.services.pipeline_service import PipelineService


def test_definitions_differ_by_mode() -> None:
    proposal = PipelineService.definitions(ProjectMode.PROPOSAL)
    build = PipelineService.definitions(ProjectMode.BUILD)
    assert [d.key for d in proposal][:3] == ["upload", "extract", "rfp_analysis"]
    assert [d.key for d in build][:3] == ["upload", "doc_structure", "load_baseline"]
    assert sum(d.requires_gate for d in proposal) == 5  # Phase 18: Gate P 추가
    assert sum(d.requires_gate for d in build) == 2
    assert [d.order for d in proposal] == list(range(1, len(proposal) + 1))


def test_overview_starts_pending(services: Services, proposal_project: Project) -> None:
    views = services.pipeline.overview(proposal_project)
    assert all(v.status == StepStatus.PENDING for v in views)
    assert services.pipeline.progress(proposal_project) == (0, len(views))
    assert services.pipeline.current_step(proposal_project).definition.key == "upload"


def test_step_without_gate_completes_to_approved(
    services: Services, proposal_project: Project
) -> None:
    run = services.pipeline.start_step(proposal_project, "upload", actor="tester")
    assert run.status == StepStatus.RUNNING and run.attempt == 1
    with pytest.raises(ValidationError):
        services.pipeline.start_step(proposal_project, "upload")  # 이미 실행 중
    services.pipeline.complete_step(proposal_project, run, summary="done")
    assert run.status == StepStatus.APPROVED
    assert services.pipeline.progress(proposal_project) == (
        1,
        16,
    )  # Phase 23: impl_design 단계 추가
    assert services.pipeline.current_step(proposal_project).definition.key == "extract"


def test_gated_step_needs_review_then_approval(
    services: Services, proposal_project: Project
) -> None:
    run = services.pipeline.start_step(proposal_project, "req_verify")
    services.pipeline.complete_step(proposal_project, run, summary="검증 완료")
    assert run.status == StepStatus.NEEDS_REVIEW
    with pytest.raises(ValidationError):
        services.pipeline.decide_gate(
            proposal_project, run, decision=ApprovalDecision.REJECTED, approver="a", comments="  "
        )
    gate = services.pipeline.decide_gate(
        proposal_project,
        run,
        decision=ApprovalDecision.APPROVED_WITH_COMMENTS,
        approver="a",
        comments="ok",
    )
    assert run.status == StepStatus.APPROVED
    history = services.pipeline.gate_history(proposal_project)
    assert len(history) == 1 and history[0][0].id == gate.id and history[0][1].approver == "a"
    with pytest.raises(ValidationError):
        services.pipeline.decide_gate(
            proposal_project, run, decision=ApprovalDecision.APPROVED, approver="a"
        )


def test_gate_rejection_fails_step_and_allows_retry(
    services: Services, proposal_project: Project
) -> None:
    run = services.pipeline.start_step(proposal_project, "req_verify")
    services.pipeline.complete_step(proposal_project, run)
    services.pipeline.decide_gate(
        proposal_project, run, decision=ApprovalDecision.REJECTED, approver="a", comments="누락"
    )
    assert run.status == StepStatus.FAILED and run.error and run.error["cause"] == "누락"
    issues = services.pipeline.open_issues(proposal_project)
    assert issues and issues[0].level == "error" and "반려" in issues[0].message
    again = services.pipeline.start_step(proposal_project, "req_verify")
    assert again.attempt == 2


def test_gate_on_ungated_step_rejected(services: Services, proposal_project: Project) -> None:
    run = services.pipeline.start_step(proposal_project, "upload")
    services.pipeline.complete_step(proposal_project, run)
    with pytest.raises(ValidationError):
        services.pipeline.decide_gate(
            proposal_project, run, decision=ApprovalDecision.APPROVED, approver="a"
        )


def test_fail_step_records_error_and_audit(services: Services, build_project: Project) -> None:
    run = services.pipeline.start_step(build_project, "load_baseline")
    services.pipeline.fail_step(build_project, run, RuntimeError("파싱 실패"))
    assert run.status == StepStatus.FAILED and run.error["message"] == "파싱 실패"
    errors = services.ctx.repos.audit.recent(build_project.id, errors_only=True)
    assert errors and errors[0].action == "step.failed" and errors[0].error["resolution"]
    with pytest.raises(ValidationError):
        services.pipeline.complete_step(build_project, run)  # failed → 전이 불가


def test_skip_only_ungated_steps(services: Services, build_project: Project) -> None:
    run = services.pipeline.skip_step(build_project, "doc_structure", reason="매핑 재사용")
    assert run.status == StepStatus.SKIPPED
    with pytest.raises(ValidationError):
        services.pipeline.skip_step(build_project, "impact", reason="x")


def test_open_issues_includes_unresolved_validations(
    services: Services, proposal_project: Project
) -> None:
    v = services.pipeline.add_validation(
        ValidationResult(
            project_id=proposal_project.id,
            target_type=ValidationTargetType.DOCUMENT,
            target_id="doc_1",
            rule_id="doc.required",
            level=ValidationLevel.WARNING,
            message="RFP 누락",
            detail={"resolution": "RFP를 업로드하십시오."},
        )
    )
    services.pipeline.add_validation(
        ValidationResult(
            project_id=proposal_project.id,
            target_type=ValidationTargetType.DOCUMENT,
            target_id="doc_1",
            rule_id="info.only",
            level=ValidationLevel.INFO,
            message="참고",
        )
    )
    issues = services.pipeline.open_issues(proposal_project)
    assert [i.message for i in issues] == ["RFP 누락"] and issues[
        0
    ].resolution == "RFP를 업로드하십시오."
    services.pipeline.resolve_validation(proposal_project, v.id)
    assert services.pipeline.open_issues(proposal_project) == []
