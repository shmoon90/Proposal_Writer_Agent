"""QA 서비스: 최신 산출물을 열어 검사하고 ValidationResult·QA 보고서·Gate 4 평가를 남긴다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.service import GenerationService
from proposal_agent.models import (
    Deliverable,
    DeliverableKind,
    GateEvaluation,
    GateStatus,
    IntegrityStatus,
    Project,
    QaStatus,
    ValidationLevel,
    ValidationResult,
    ValidationTargetType,
)
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories
from proposal_agent.validation.deliverables import (
    QaOutcome,
    check_consistency,
    check_pptx,
    check_xlsx,
    render_report,
)

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("validation.qa")

GATE4_KEY = "gate4"


@dataclass
class QaRunResult:
    outcome: QaOutcome
    report_path: str
    gate: GateEvaluation
    review_items: list[str] = field(default_factory=list)
    checked: list[Deliverable] = field(default_factory=list)


class QaService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        audit: AuditService,
        files: FileStore,
        generation: GenerationService,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._audit = audit
        self._files = files
        self._generation = generation

    def run(
        self,
        project: Project,
        *,
        actor: str = "user",
        step_run_id: str | None = None,
        context: GenerationContext | None = None,
    ) -> QaRunResult:
        ctx = context or self._generation.build_context(project, actor=actor)
        latest = self._generation.latest_deliverables(project)
        outcome = QaOutcome()
        excel: dict[DeliverableKind, dict[str, list[list[Any]]]] = {}
        ppt_texts: dict[str, list[str]] = {}
        checked: list[Deliverable] = []
        for kind, d in latest.items():
            path = self._paths.resolve_output(d.file_path)
            if kind.value.endswith("xlsx"):
                excel[kind] = check_xlsx(path, kind, outcome, ctx)
            elif kind == DeliverableKind.SUBMISSION_PPTX:
                ppt_texts["submission"] = check_pptx(path, outcome, "제출용")
            elif kind == DeliverableKind.PRESENTATION_PPTX:
                ppt_texts["presentation"] = check_pptx(path, outcome, "발표용")
            elif kind.value.endswith("png"):
                from proposal_agent.agents.tools import verify_file

                info = verify_file(path)
                outcome.opened[kind.value] = bool(info.get("ok"))
                if not info.get("ok"):
                    outcome.add(
                        ValidationLevel.ERROR,
                        "png.open",
                        f"{kind.value}: {info.get('error')}",
                        d.file_path,
                    )
            checked.append(d)
        missing_kinds = [
            k
            for k in (
                DeliverableKind.REQUIREMENT_SPEC_XLSX,
                DeliverableKind.TRACE_MATRIX_XLSX,
                DeliverableKind.WBS_GANTT_XLSX,
                DeliverableKind.STAFFING_PLAN_XLSX,
                DeliverableKind.SUBMISSION_PPTX,
                DeliverableKind.PRESENTATION_PPTX,
                DeliverableKind.SYSTEM_DIAGRAM_PNG,
                DeliverableKind.SW_DIAGRAM_PNG,
                DeliverableKind.SERVICE_DIAGRAM_PNG,
            )
            if k not in latest
        ]
        for k in missing_kinds:
            outcome.add(ValidationLevel.ERROR, "deliverable.missing", f"산출물 없음: {k.value}")
        if excel or ppt_texts:
            check_consistency(ctx, excel, ppt_texts, outcome)

        # 기록
        for d in checked:
            label_ok = outcome.opened.get(
                {
                    DeliverableKind.SUBMISSION_PPTX: "제출용",
                    DeliverableKind.PRESENTATION_PPTX: "발표용",
                }.get(d.kind, d.kind.value),
                True,
            )
            d.integrity_status = IntegrityStatus.PASSED if label_ok else IntegrityStatus.FAILED
            d.qa_status = (
                QaStatus.FAILED
                if any(
                    f.level == ValidationLevel.ERROR
                    and (
                        d.file_path in f.location
                        or d.kind.value in f.message
                        or d.kind.value in f.location
                    )
                    for f in outcome.findings
                )
                else QaStatus.PASSED
            )
            self._repos.deliverables.update(d)
        for f in outcome.findings:
            self._repos.validations.insert(
                ValidationResult(
                    project_id=project.id,
                    target_type=ValidationTargetType.DELIVERABLE,
                    target_id=f.location or "deliverables",
                    rule_id=f"qa.{f.rule}",
                    level=f.level,
                    message=f.message,
                    detail={"resolution": "산출물을 수정·재생성한 뒤 QA를 다시 실행하십시오."},
                    validator="code:validation.qa",
                )
            )
        review_items = list(ctx.review_notes)
        report = render_report(
            project.name, outcome, [(d.kind.value, d.file_path) for d in checked], review_items
        )
        name = self._files.next_version_name(
            project.output_dir, "11_QA_Validation_Reports", "QA보고서", ".md"
        )
        stored = self._files.save_bytes(
            project.output_dir, "11_QA_Validation_Reports", name, report.encode("utf-8")
        )
        gate = self._evaluate_gate4(project, outcome, review_items, step_run_id)
        self._audit.record(
            project.id,
            "qa.completed",
            actor=actor,
            payload={
                "errors": len(outcome.errors),
                "warnings": len(outcome.warnings),
                "opened": outcome.opened,
                "report": stored.relative_path,
                "gate4": str(gate.status),
                "review_items": len(review_items),
            },
        )
        return QaRunResult(
            outcome=outcome,
            report_path=stored.relative_path,
            gate=gate,
            review_items=review_items,
            checked=checked,
        )

    def _evaluate_gate4(
        self, project: Project, outcome: QaOutcome, review_items: list[str], step_run_id: str | None
    ) -> GateEvaluation:
        reasons: list[str] = []
        if outcome.errors:
            status = GateStatus.FAIL
            reasons.append(f"QA 오류 {len(outcome.errors)}건")
            reasons.extend(f.message for f in outcome.errors[:5])
        elif outcome.warnings or review_items or any(not ok for ok in outcome.opened.values()):
            status = GateStatus.NEEDS_HUMAN_REVIEW
            reasons.append(f"경고 {len(outcome.warnings)}건, 사람 검토 항목 {len(review_items)}건")
        else:
            status = GateStatus.NEEDS_HUMAN_REVIEW
            reasons.append("자동 검사 통과. 최종 확정은 사람 승인이 필요합니다.")
        ev = GateEvaluation(
            project_id=project.id,
            gate_key=GATE4_KEY,
            status=status,
            reasons=reasons,
            metrics={
                "errors": len(outcome.errors),
                "warnings": len(outcome.warnings),
                "review_items": len(review_items),
            },
            evaluated_by="code:validation.qa",
            step_run_id=step_run_id,
        )
        self._repos.gate_evaluations.insert(ev)
        return ev
