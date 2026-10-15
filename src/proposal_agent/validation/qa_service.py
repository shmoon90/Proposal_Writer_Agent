"""통합 QA 서비스: 입력 수집 → 독립 검증 → 자동 수정·재검증(횟수 제한) → 게이트 2·3·4·5 판정 → 보고서·기록.

- 산출물을 만든 에이전트의 자기 평가는 쓰지 않는다. 코드 검증(``independent_qa``)이 기본이고,
  설정(``qa_use_agent``)이나 호출 인자로 켜면 ``qa_reviewer`` 역할의 독립 검토를 덧붙인다(결과는 사람 검토 항목).
- 자동 수정은 '기준 데이터로 산출물 재생성'뿐이다. 요구사항·WBS·기술 데이터는 바꾸지 않는다.
- 보고서는 ``11_QA_Validation_Reports/통합QA보고서_vX.Y.md``(+ ``.json``)에 남기고, 실제 실행한 검사만 기록한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from proposal_agent.config.errors import PWAError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.service import GenerationService
from proposal_agent.models import (
    ChangeStatus,
    Deliverable,
    DeliverableKind,
    GateEvaluation,
    GateStatus,
    IntegrityStatus,
    Project,
    ProjectMode,
    QaCategory,
    QaCheck,
    QaResult,
    QaRun,
    QaStatus,
    ValidationLevel,
    ValidationResult,
    ValidationTargetType,
    utcnow,
)
from proposal_agent.planning.calendar import BusinessCalendar, parse_holidays
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories
from proposal_agent.validation.deliverables import QaOutcome
from proposal_agent.validation.independent_qa import (
    FIX_REGENERATE,
    CheckArtifacts,
    QaInputs,
    gate_status,
    run_all_checks,
)

if TYPE_CHECKING:
    from proposal_agent.changes.service import ChangeService
    from proposal_agent.ingest.service import ExtractionService
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService

log = get_logger("validation.qa")

GATE2_KEY = "gate2"
GATE3_KEY = "gate3"
GATE4_KEY = "gate4"
GATE5_KEY = "gate5"
GATE_KEYS = (GATE2_KEY, GATE3_KEY, GATE4_KEY, GATE5_KEY)
REPORT_SUBDIR = "11_QA_Validation_Reports"
REPORT_STEM = "통합QA보고서"


@dataclass
class QaRunResult:
    outcome: QaOutcome
    report_path: str
    gate: GateEvaluation  # gate5 (최종 독립 QA)
    review_items: list[str] = field(default_factory=list)
    checked: list[Deliverable] = field(default_factory=list)
    qa_run: QaRun | None = None
    gates: dict[str, GateEvaluation] = field(default_factory=dict)

    @property
    def checks(self) -> list[QaCheck]:
        return self.qa_run.checks if self.qa_run else []


class QaService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        audit: AuditService,
        files: FileStore,
        generation: GenerationService,
        *,
        settings: Settings | None = None,
        extraction: ExtractionService | None = None,
        changes: ChangeService | None = None,
        steps: AgentStepService | None = None,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._audit = audit
        self._files = files
        self._generation = generation
        self._settings = settings or Settings()
        self._extraction = extraction
        self._changes = changes
        self._steps = steps

    # --- 입력 수집 ----------------------------------------------------------------------------
    def _context(self, project: Project, actor: str) -> GenerationContext:
        if project.mode == ProjectMode.BUILD and self._changes is not None:
            revs = self._repos.revisions.find(project.id, order_by="created_at")
            return self._changes.build_context(project, revs[-1].number if revs else "v1.0")
        return self._generation.build_context(project, actor=actor)

    def collect_inputs(
        self, project: Project, *, actor: str = "user", context: GenerationContext | None = None
    ) -> QaInputs:
        ctx = context or self._context(project, actor)
        blocks = (
            self._extraction.current_blocks(project, required_only=True)
            if self._extraction and project.mode == ProjectMode.PROPOSAL
            else []
        )
        analysis = None
        if self._steps is not None and project.mode == ProjectMode.PROPOSAL:
            analysis = self._steps.prior_output(project, "rfp_analyst")
        prefixes = {**self._settings.id_prefixes, **(project.settings.get("id_prefixes") or {})}
        return QaInputs(
            project=project,
            ctx=ctx,
            paths=self._paths,
            calendar=BusinessCalendar(parse_holidays(self._settings.holidays)),
            blocks=blocks,
            documents=self._repos.documents.find(project.id),
            all_requirements=self._repos.requirements.find(project.id, order_by="id"),
            research=self._repos.research.find(project.id, order_by="created_at"),
            deliverables=self._generation.latest_deliverables(project),
            change_requests=self._repos.change_requests.find(project.id, order_by="created_at"),
            revisions=self._repos.revisions.find(project.id, order_by="created_at"),
            rfp_analysis=analysis,
            id_prefixes=prefixes,
        )

    # --- 실행 ------------------------------------------------------------------------------------
    def run(
        self,
        project: Project,
        *,
        actor: str = "user",
        step_run_id: str | None = None,
        context: GenerationContext | None = None,
        use_agent: bool | None = None,
        tests_executed: list[dict[str, Any]] | None = None,
        max_fix_rounds: int | None = None,
    ) -> QaRunResult:
        limit = self._settings.qa_max_fix_rounds if max_fix_rounds is None else max_fix_rounds
        inputs = self.collect_inputs(project, actor=actor, context=context)
        checks, art = run_all_checks(inputs)
        fixes: list[str] = []
        rounds = 0
        # 자동 수정·재검증 루프: 재생성으로 고칠 수 있는 실패만. 기준 데이터는 바꾸지 않는다.
        while rounds < limit:
            fixable = [
                c
                for c in checks
                if c.executed
                and c.result == QaResult.FAIL
                and c.fixable == FIX_REGENERATE
                and c.reverified != QaResult.PASS
            ]
            if not fixable:
                break
            rounds += 1
            try:
                note = self._apply_fix(project, actor, inputs)
            except PWAError as exc:
                fixes.append(f"{rounds}회차 재생성 실패: {exc}")
                for c in fixable:
                    c.attempts += 1
                    c.fix_applied = False
                    c.fix_detail = f"재생성 실패: {exc}"
                break
            fixes.append(f"{rounds}회차: {note}")
            inputs = self.collect_inputs(project, actor=actor)
            new_checks, art = run_all_checks(inputs)
            by_id = {c.check_id: c for c in new_checks}
            for c in checks:
                n = by_id.get(c.check_id)
                if n is None:
                    continue
                if c.check_id in {x.check_id for x in fixable}:
                    c.attempts += 1
                    c.fix_applied = True
                    c.fix_detail = note
                    c.reverified = n.result
                    c.issues = (
                        n.issues if n.result != QaResult.PASS else [*c.issues, "→ 재생성 후 해결"]
                    )
                else:
                    # 수정 대상이 아니어도 재생성 영향을 받을 수 있으므로 최신 결과를 반영
                    c.result, c.issues, c.files, c.requirement_ids = (
                        n.result,
                        n.issues,
                        n.files,
                        n.requirement_ids,
                    )
        for c in checks:
            if c.fix_applied and c.reverified == QaResult.FAIL:
                c.reverified = QaResult.NEEDS_HUMAN_REVIEW
                c.issues.append(
                    f"자동 수정 {c.attempts}회 후에도 실패 — 사용자 검토로 전환 (한도 {limit}회)"
                )
        agent_review = None
        if use_agent if use_agent is not None else self._settings.qa_use_agent:
            agent_review = self._agent_review(project, inputs, art, checks, actor)

        # 게이트 (코드 판정)
        gate_evals: dict[str, GateEvaluation] = {}
        for key in GATE_KEYS:
            status, reasons = gate_status(checks, key)
            if key == GATE5_KEY:
                for g in ("gate0", "gate1"):
                    if project.mode == ProjectMode.PROPOSAL:
                        prev = self._repos.gate_evaluations.latest(project.id, g)
                        if prev is None or prev.status == GateStatus.FAIL:
                            status = "FAIL"
                            reasons.insert(0, f"{g} 미통과 상태")
            ev = GateEvaluation(
                project_id=project.id,
                gate_key=key,
                status=GateStatus(status),
                reasons=reasons,
                metrics=self._counts([c for c in checks if c.gate == key or key == GATE5_KEY]),
                evaluated_by="code:validation.independent_qa",
                step_run_id=step_run_id,
            )
            self._repos.gate_evaluations.insert(ev)
            gate_evals[key] = ev

        # 산출물 상태·ValidationResult
        checked = list(inputs.deliverables.values())
        self._update_deliverables(checked, checks, art)
        for c in checks:
            if c.executed and c.final_result != QaResult.PASS:
                self._repos.validations.insert(
                    ValidationResult(
                        project_id=project.id,
                        target_type=ValidationTargetType.DELIVERABLE
                        if c.category == QaCategory.FILE_QUALITY
                        else ValidationTargetType.PLAN
                        if c.gate == GATE3_KEY
                        else ValidationTargetType.REQUIREMENT
                        if c.category == QaCategory.RFP_FIT
                        else ValidationTargetType.STEP,
                        target_id=", ".join(c.files[:3]) or c.target,
                        rule_id=c.check_id,
                        level=ValidationLevel.ERROR
                        if c.final_result == QaResult.FAIL
                        else ValidationLevel.WARNING,
                        message="; ".join(c.issues)[:800],
                        detail={
                            "resolution": c.fix_suggestion,
                            "requirement_ids": c.requirement_ids,
                        },
                        validator="code:validation.independent_qa",
                    )
                )
        review_items = list(inputs.ctx.review_notes)
        counts = self._counts(checks)
        verdict = gate_evals[GATE5_KEY].status.value
        qa_run = QaRun(
            project_id=project.id,
            step_run_id=step_run_id,
            mode=project.mode.value,
            scope=["RFP 적합성", "기술 타당성", "문서 간 일관성", "파일 품질"]
            + (["에이전트 독립 검토"] if agent_review else []),
            checks=checks,
            gates={k: v.status.value for k, v in gate_evals.items()},
            counts=counts,
            fix_rounds=rounds,
            max_fix_rounds=limit,
            fixes=fixes,
            tests_executed=list(tests_executed or []),
            unresolved_risks=[
                f"{c.check_id} {c.target}: {c.issues[0] if c.issues else ''}"
                for c in checks
                if c.executed and c.final_result != QaResult.PASS
            ],
            approval_needed=[
                f"{c.check_id} {c.target}"
                for c in checks
                if c.applicable and c.final_result == QaResult.NEEDS_HUMAN_REVIEW
            ]
            + [f"{GATE5_KEY}: 최종 독립 QA 사람 승인"],
            verdict=verdict,
            agent_review=agent_review,
            created_by=actor,
        )
        qa_run.report_path, qa_run.json_path = self._write_report(project, qa_run, review_items)
        self._repos.qa_runs.insert(qa_run)
        self._audit.record(
            project.id,
            "qa.completed",
            actor=actor,
            payload={
                **counts,
                "gates": qa_run.gates,
                "fix_rounds": rounds,
                "report": qa_run.report_path,
                "review_items": len(review_items),
                "verdict": verdict,
            },
        )
        return QaRunResult(
            outcome=art.outcome,
            report_path=qa_run.report_path or "",
            gate=gate_evals[GATE5_KEY],
            review_items=review_items,
            checked=checked,
            qa_run=qa_run,
            gates=gate_evals,
        )

    def _apply_fix(self, project: Project, actor: str, inputs: QaInputs) -> str:
        """기준 데이터로 산출물을 재생성한다 (요구사항·WBS·기술 데이터 불변)."""
        if project.mode == ProjectMode.BUILD:
            if self._changes is None:
                raise PWAError("구축 단계 재생성 서비스가 없습니다.")
            revs = self._repos.revisions.find(project.id, order_by="created_at")
            if not revs:
                raise PWAError(
                    "Revision이 없어 재생성할 수 없습니다.",
                    resolution="기준 데이터를 먼저 적재하십시오.",
                )
            applied = [cr for cr in inputs.change_requests if cr.status == ChangeStatus.APPLIED]
            cr = applied[-1] if applied else None
            if cr is None:
                raise PWAError(
                    "반영된 변경 요청이 없어 재생성 대상이 없습니다.",
                    resolution="변경 요청을 승인·반영한 뒤 QA를 실행하십시오.",
                )
            deliverables, errors = self._changes.regenerate(
                project, cr, revs[-1], actor=actor, include_staffing=bool(inputs.ctx.allocations)
            )
            return f"구축 산출물 {len(deliverables)}건 재생성" + (
                f" (오류 {len(errors)})" if errors else ""
            )
        result = self._generation.generate_all(project, actor=actor)
        if result.errors:
            raise PWAError(
                "재생성 중 오류",
                cause="; ".join(result.errors),
                resolution="오류를 해결한 뒤 QA를 다시 실행하십시오.",
            )
        return f"산출물 {len(result.deliverables)}건 재생성"

    def _agent_review(
        self,
        project: Project,
        inputs: QaInputs,
        art: CheckArtifacts,
        checks: list[QaCheck],
        actor: str,
    ) -> dict[str, Any] | None:
        """qa_reviewer 역할의 독립 검토. 실패하면 None(실행 안 함)으로 기록하고 코드 결과만 쓴다."""
        if self._steps is None:
            return {"executed": False, "reason": "에이전트 실행 서비스 없음"}
        from proposal_agent.agents.schemas import QaReport

        summary = {
            "deliverables": {k.value: d.file_path for k, d in inputs.deliverables.items()},
            "ppt_excerpt": {k: "\n".join(v)[:4000] for k, v in art.ppt_texts.items()},
            "requirements": [
                {"id": r.id, "name": r.name, "mandatory": r.is_mandatory, "type": r.type.value}
                for r in inputs.requirements[:150]
            ],
            "research": [
                {
                    "topic": t.topic,
                    "feasibility": t.feasibility.value,
                    "unverified": t.unverified_items[:5],
                }
                for t in inputs.research[:30]
            ],
            "code_checks": [
                {"id": c.check_id, "result": c.final_result.value, "issues": c.issues[:3]}
                for c in checks
            ],
        }
        prompt = (
            "<deliverables>\n"
            + json.dumps(summary, ensure_ascii=False)[:20000]
            + "\n</deliverables>\n<baseline>\n요구사항·WBS는 mcp__pwa 도구로 조회\n</baseline>"
        )
        try:
            res = self._steps.run_role(
                project, "qa_reviewer", prompt, actor=actor, include_prior=False
            )
        except PWAError as exc:
            return {"executed": False, "reason": str(exc)}
        report = res.output
        if not isinstance(report, QaReport):
            return {"executed": False, "reason": "출력 형식 오류"}
        for i, fnd in enumerate(report.findings, start=1):
            checks.append(
                QaCheck(
                    check_id=f"QA-AI-{i:02d}",
                    category=QaCategory.AGENT_REVIEW,
                    target=fnd.target,
                    criteria="qa_reviewer 에이전트 독립 검토 (사람 확인 필요)",
                    result=QaResult.NEEDS_HUMAN_REVIEW,
                    issues=[fnd.message] + ([fnd.suggestion] if fnd.suggestion else []),
                    files=[fnd.location] if fnd.location else [],
                    fix_suggestion=fnd.suggestion,
                    mandatory=False,
                    gate=GATE5_KEY,
                    evaluated_by="agent:qa_reviewer",
                )
            )
        return {
            "executed": True,
            "overall": report.overall,
            "summary": report.summary,
            "findings": len(report.findings),
            "cost_usd": res.response.cost_usd,
        }

    # --- 기록 ------------------------------------------------------------------------------------
    @staticmethod
    def _counts(checks: list[QaCheck]) -> dict[str, int]:
        executed = [c for c in checks if c.executed]
        return {
            "total": len(checks),
            "executed": len(executed),
            "not_run": len(checks) - len(executed),
            "pass": sum(1 for c in executed if c.final_result == QaResult.PASS),
            "fail": sum(1 for c in executed if c.final_result == QaResult.FAIL),
            "needs_human_review": sum(
                1 for c in checks if c.applicable and c.final_result == QaResult.NEEDS_HUMAN_REVIEW
            ),
            "not_applicable": sum(1 for c in checks if not c.applicable),
            "fixed": sum(1 for c in checks if c.fix_applied and c.reverified == QaResult.PASS),
        }

    def _update_deliverables(
        self, checked: list[Deliverable], checks: list[QaCheck], art: CheckArtifacts
    ) -> None:
        file_fail_paths: set[str] = set()
        for c in checks:
            if (
                c.category in (QaCategory.FILE_QUALITY, QaCategory.CONSISTENCY)
                and c.executed
                and c.final_result == QaResult.FAIL
            ):
                file_fail_paths.update(c.files)
        for d in checked:
            label = {
                DeliverableKind.SUBMISSION_PPTX: "제출용",
                DeliverableKind.PRESENTATION_PPTX: "발표용",
            }.get(d.kind, d.kind.value)
            opened = art.outcome.opened.get(label, True)
            d.integrity_status = IntegrityStatus.PASSED if opened else IntegrityStatus.FAILED
            d.qa_status = (
                QaStatus.FAILED
                if (d.file_path in file_fail_paths or not opened)
                else QaStatus.PASSED
            )
            self._repos.deliverables.update(d)

    def _write_report(
        self, project: Project, run: QaRun, review_items: list[str]
    ) -> tuple[str, str]:
        md = render_qa_report(project, run, review_items)
        name = self._files.next_version_name(project.output_dir, REPORT_SUBDIR, REPORT_STEM, ".md")
        stored = self._files.save_bytes(project.output_dir, REPORT_SUBDIR, name, md.encode("utf-8"))
        jname = name[:-3] + ".json"
        payload = run.model_dump(mode="json")
        payload["generated_at"] = utcnow().isoformat()
        jstored = self._files.save_bytes(
            project.output_dir,
            REPORT_SUBDIR,
            jname,
            json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"),
        )
        return stored.relative_path, jstored.relative_path

    def latest_run(self, project: Project) -> QaRun | None:
        return self._repos.qa_runs.latest(project.id)


def render_qa_report(project: Project, run: QaRun, review_items: list[str]) -> str:
    c = run.counts
    lines = [
        f"# 통합 QA 보고서 — {project.name}",
        "",
        f"- 실행 시각: {run.created_at.isoformat()} · 모드: {run.mode} · 판정 기준: 코드(validation.independent_qa)",
        f"- **최종 판정: {run.verdict}**"
        + (
            " — 필수 검증 실패가 있어 최종 완료로 전환할 수 없습니다."
            if run.verdict == "FAIL"
            else " — 사람 승인이 필요합니다."
            if run.verdict == "NEEDS_HUMAN_REVIEW"
            else ""
        ),
        "",
        "## 1. 전체 검증 범위",
        *[f"- {s}" for s in run.scope],
        "- 게이트: " + ", ".join(f"{k}={v}" for k, v in run.gates.items()),
        "",
        "## 2. 실제 실행한 테스트",
        f"- 자동 검증 항목 {c.get('executed', 0)}건 실행 / {c.get('not_run', 0)}건 미실행 (미실행은 통과로 세지 않음)",
    ]
    if run.tests_executed:
        for t in run.tests_executed:
            lines.append(
                f"- {t.get('name', '테스트')}: "
                + ", ".join(f"{k}={v}" for k, v in t.items() if k != "name")
            )
    else:
        lines.append(
            "- 외부 테스트(pytest) 결과는 이 실행에 첨부되지 않았습니다 (scripts/run_regression.py로 첨부 가능)."
        )
    if run.agent_review:
        lines.append(
            "- 에이전트 독립 검토(qa_reviewer): "
            + (
                "실행됨 — "
                + json.dumps(
                    {k: v for k, v in run.agent_review.items() if k != "executed"},
                    ensure_ascii=False,
                )
                if run.agent_review.get("executed")
                else f"미실행 ({run.agent_review.get('reason')})"
            )
        )
    lines += [
        "",
        "## 3. 건수",
        f"- 통과 {c.get('pass', 0)} · 실패 {c.get('fail', 0)} · 검토 필요 {c.get('needs_human_review', 0)} · 미실행 {c.get('not_run', 0)} · 자동 수정 후 통과 {c.get('fixed', 0)}",
        "",
        "## 4. 검증 항목별 결과",
        "",
        "| 검증 ID | 대상 | 기준 | 결과 | 발견 문제 | 관련 요구사항 | 영향 파일 | 수정 제안 | 수정 여부 | 재검증 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for ch in run.checks:
        result = (
            ch.final_result.value
            if ch.executed
            else f"미실행 ({ch.not_run_reason})" + ("" if ch.applicable else " · 해당 없음")
        )
        fixed = "-" if ch.fix_applied is None else ("반영" if ch.fix_applied else "보류")
        lines.append(
            f"| {ch.check_id} | {ch.target} | {_cell(ch.criteria)} | {result} | {_cell('; '.join(ch.issues) or '없음')} | {', '.join(ch.requirement_ids[:6]) or '-'} | {_cell(', '.join(ch.files[:3]) or '-')} | {_cell(ch.fix_suggestion if ch.final_result != QaResult.PASS else '-')} | {fixed} | {ch.reverified.value if ch.reverified else '-'} |"
        )
    major = [ch for ch in run.checks if ch.executed and ch.final_result == QaResult.FAIL]
    lines += ["", "## 5. 주요 발견 사항"]
    lines += [f"- **{ch.check_id} {ch.target}**: " + "; ".join(ch.issues[:3]) for ch in major] or [
        "- 필수 검증 실패 없음"
    ]
    lines += ["", "## 6. 수정 내역", f"- 자동 수정 라운드 {run.fix_rounds}/{run.max_fix_rounds}"]
    lines += [f"- {f}" for f in run.fixes] or ["- 자동 수정 없음"]
    lines += ["", "## 7. 재검증 결과"]
    re_items = [ch for ch in run.checks if ch.reverified is not None]
    lines += [
        f"- {ch.check_id}: {ch.result.value} → {ch.reverified.value if ch.reverified else '-'} ({ch.attempts}회)"
        for ch in re_items
    ] or ["- 재검증 항목 없음"]
    lines += ["", "## 8. 미해결 위험"]
    lines += [f"- {r}" for r in run.unresolved_risks] or ["- 없음"]
    lines += ["", "## 9. 승인 필요 항목"]
    lines += [f"- {a}" for a in run.approval_needed]
    if review_items:
        lines += ["", "### 생성 단계 사람 검토 항목", *[f"- {r}" for r in review_items]]
    lines += [
        "",
        "## 10. 최종 판정",
        f"- {run.verdict}",
        "- 실제 실행한 검사 결과만 반영했습니다. 미실행 항목은 통과로 표시하지 않았습니다.",
    ]
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "／").replace("\n", " ")[:200]


__all__ = [
    "GATE2_KEY",
    "GATE3_KEY",
    "GATE4_KEY",
    "GATE5_KEY",
    "QaRunResult",
    "QaService",
    "render_qa_report",
]
