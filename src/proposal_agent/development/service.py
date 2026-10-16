"""개발 서비스 (단계 7, D-22): 코드 생성 패키지 → 템플릿 → 배치별 Developer 에이전트(구조화 출력) → 안전 쓰기 → 정적 검사 →
Docker JUnit 실행 → QA 분석·수정 루프 → 코드 모듈(MOD)·테스트 케이스(TC)·결함(DEF) 반영.

실제 에이전트 실행에는 API 크레딧이 필요하다. 생성물은 프로토타입이며 납품 코드가 아니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from proposal_agent.agents.schemas import CodeBatchReport, CodeFixReport, CodeQaReport
from proposal_agent.config.errors import AgentRunError, PathSecurityError, PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.development.constants import (
    GENERATED_APP_SUBDIR,
    TEMPLATE_PATHS,
    TEST_RESULTS_DIR,
)
from proposal_agent.development.inspector import (
    InspectionResult,
    check_test_rules,
    cross_check_imports,
    inspect_all,
    is_test_file,
)
from proposal_agent.development.models import TestRunResult
from proposal_agent.development.plan import CodeBatchPlan, generatable_modules, plan_batches
from proposal_agent.development.templates import template_files
from proposal_agent.development.test_runner import DockerSandbox, DockerStatus, TestRunner
from proposal_agent.development.workspace import GeneratedWorkspace
from proposal_agent.models import AcceptanceStatus, CodeModule, Project, Requirement
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

log = get_logger(__name__)

ROLE_DEVELOPER = "developer"
ROLE_CODE_QA = "code_qa"
ROLE_CODE_FIXER = "code_fixer"
CONTEXT_FILE_CHARS = 6000
MAX_CONTEXT_FILES = 8


@dataclass
class GenerationOutcome:
    batches_total: int = 0
    batches_done: int = 0
    files_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cost_usd: float = 0.0

    def summary(self) -> str:
        return (
            f"코드 생성: 배치 {self.batches_done}/{self.batches_total}, 파일 {len(self.files_written)}개, "
            f"오류 {len(self.errors)}건, 경고 {len(self.warnings)}건, 비용 ${self.cost_usd:.3f}"
        )


class DevelopmentService:
    def __init__(
        self,
        repos: Repositories,
        audit: AuditService,
        steps: AgentStepService,
        paths: ProjectPaths,
        files: FileStore,
        settings: Settings,
        *,
        testing: Any,
        test_runner: TestRunner | None = None,
    ) -> None:
        self._repos = repos
        self._audit = audit
        self._steps = steps
        self._paths = paths
        self._files = files
        self._settings = settings
        self._testing = testing
        self._runner = test_runner

    # --- 작업 폴더·Docker ------------------------------------------------------------------------------
    def app_dir(self, project: Project) -> Path:
        return self._paths.subdir(project.output_dir, GENERATED_APP_SUBDIR)

    def workspace(self, project: Project) -> GeneratedWorkspace:
        return GeneratedWorkspace(self.app_dir(project))

    def runner(self) -> TestRunner:
        if self._runner is None:
            self._runner = TestRunner(
                image=self._settings.docker_test_image,
                timeout_seconds=self._settings.test_timeout_seconds,
                max_output_chars=self._settings.max_test_output_chars,
            )
        return self._runner

    def docker_status(self) -> DockerStatus:
        return self.runner().docker.status()

    def build_image(self) -> tuple[bool, str]:
        return DockerSandbox(self._settings.docker_test_image).build_image()

    # --- 모듈·배치 ------------------------------------------------------------------------------------------
    def modules(self, project: Project) -> list[CodeModule]:
        return [
            m
            for m in self._repos.code_modules.find(project.id, order_by="code")
            if m.status != "dropped"
        ]

    def plan(
        self, project: Project, *, max_files: int | None = None
    ) -> tuple[list[CodeBatchPlan], list[str]]:
        ok, warnings = generatable_modules(self.modules(project))
        if not ok:
            return [], warnings + [
                "생성할 모듈이 없습니다 — 설계 화면에서 상세 설계(모듈 분해)를 먼저 실행하십시오."
            ]
        return plan_batches(ok, max_files or self._settings.codegen_max_files), warnings

    def prepare(self, project: Project, *, actor: str = "user") -> list[str]:
        """고정 템플릿(pom·Application·properties·README) 을 작업 폴더에 쓴다 (설계가 있어야 함)."""
        ok, _ = generatable_modules(self.modules(project))
        apis = [
            a
            for a in self._repos.api_specs.find(project.id, order_by="code")
            if a.status != "dropped"
        ]
        ws = self.workspace(project)
        written = []
        for rel, content in template_files(project.name, ok, apis).items():
            ws.write(rel, content)
            written.append(rel)
        self._audit.record(
            project.id, "development.prepared", actor=actor, payload={"files": written}
        )
        return written

    # --- 코드 생성 -----------------------------------------------------------------------------------------------
    def generate(
        self,
        project: Project,
        *,
        actor: str = "user",
        max_files: int | None = None,
        only_labels: set[str] | None = None,
        cancel: Any = None,
    ) -> GenerationOutcome:
        out = GenerationOutcome()
        batches, warnings = self.plan(project, max_files=max_files)
        out.warnings.extend(warnings)
        out.batches_total = len(batches)
        if not batches:
            return out
        ws = self.workspace(project)
        if not all(ws.read(p) for p in TEMPLATE_PATHS):
            self.prepare(project, actor=actor)
        known_ids = {r.id for r in self._repos.requirements.find(project.id)}
        modules = {m.path: m for m in self.modules(project)}
        planned_paths = set(modules)
        for batch in batches:
            if only_labels and batch.label not in only_labels:
                continue
            if cancel is not None and bool(getattr(cancel, "is_cancelled", False)):
                out.warnings.append("중단 요청으로 나머지 배치를 건너뜀")
                break
            snapshot = ws.snapshot()
            errors = self._generate_batch(
                project, batch, ws, snapshot, modules, known_ids, planned_paths, actor, out
            )
            if errors:
                ws.restore(snapshot)
                out.errors.append(f"{batch.label}: " + "; ".join(errors[:5]))
                for code in batch.module_codes:
                    self._mark_module(project, modules, code, "failed", errors[:5])
            else:
                out.batches_done += 1
        self._audit.record(
            project.id,
            "development.generated",
            actor=actor,
            payload={
                "batches": out.batches_done,
                "files": out.files_written,
                "errors": out.errors[:10],
            },
        )
        return out

    def _generate_batch(
        self,
        project: Project,
        batch: CodeBatchPlan,
        ws: GeneratedWorkspace,
        snapshot: dict[str, str],
        modules: dict[str, CodeModule],
        known_ids: set[str],
        planned_paths: set[str],
        actor: str,
        out: GenerationOutcome,
    ) -> list[str]:
        prior_errors: list[str] = []
        for attempt in range(2):  # 1회 재요청
            prompt = self._batch_prompt(project, batch, snapshot, modules, prior_errors)
            try:
                result = self._steps.run_role(
                    project, ROLE_DEVELOPER, prompt, actor=actor, include_prior=False
                )
            except (AgentRunError, PWAError) as exc:
                return [f"에이전트 실행 실패: {exc}"]
            out.cost_usd += float(getattr(result.response, "cost_usd", 0.0) or 0.0)
            report = result.output
            if not isinstance(report, CodeBatchReport):
                try:
                    report = CodeBatchReport.model_validate(report)
                except Exception as exc:  # noqa: BLE001
                    prior_errors = [f"출력 형식 오류: {exc}"]
                    continue
            errors = self._apply_report(batch, report, ws, known_ids, planned_paths, out)
            if not errors:
                for code in batch.module_codes:
                    m = next((x for x in modules.values() if x.code == code), None)
                    if m is not None:
                        links = [
                            lk.model_dump() for lk in report.implementation_map if lk.path == m.path
                        ]
                        self._mark_module(project, modules, code, "generated", [], links=links)
                return []
            prior_errors = errors
            if attempt == 0:
                ws.restore(snapshot)
        return prior_errors

    def _apply_report(
        self,
        batch: CodeBatchPlan,
        report: CodeBatchReport,
        ws: GeneratedWorkspace,
        known_ids: set[str],
        planned_paths: set[str],
        out: GenerationOutcome,
    ) -> list[str]:
        errors: list[str] = []
        targets = set(batch.target_paths)
        produced = {f.path.replace("\\", "/") for f in report.files}
        missing = sorted(targets - produced)
        if missing:
            errors.append("작성되지 않은 대상 파일: " + ", ".join(missing))
        for f in report.files:
            rel = f.path.replace("\\", "/")
            if rel not in targets:
                errors.append(f"대상이 아닌 파일: {rel}")
                continue
            if not f.content.strip():
                errors.append(f"내용이 비어 있음: {rel}")
                continue
            unknown = [r for r in f.requirement_ids if r not in known_ids]
            if unknown:
                errors.append(f"{rel}: 존재하지 않는 요구사항 ID {', '.join(unknown)}")
            try:
                res = ws.write(rel, f.content, allowed=targets)
            except PathSecurityError as exc:
                errors.append(str(exc))
                continue
            if res.change_type != "UNCHANGED":
                out.files_written.append(rel)
        if errors:
            return errors
        snapshot = ws.snapshot()
        inspected = inspect_all(snapshot)
        for rel in batch.target_paths:
            r = inspected.get(rel)
            if r is None:
                continue
            errors.extend(r.errors)
            errors.extend(check_test_rules(r, known_ids))
        warnings = [
            w
            for w in cross_check_imports(inspected, planned_paths)
            if w.split(":", 1)[0] in targets
        ]
        out.warnings.extend(warnings)
        for lk in report.implementation_map:
            r = inspected.get(lk.path.replace("\\", "/"))
            if r is None:
                continue
            bad = [
                s for s in lk.symbols if s not in r.symbols and s.split(".")[-1] not in r.symbols
            ]
            if bad:
                errors.append(
                    f"implementation_map: {lk.path} 에 정의되지 않은 이름 {', '.join(bad)}"
                )
        return errors

    def _mark_module(
        self,
        project: Project,
        modules: dict[str, CodeModule],
        code: str,
        status: str,
        notes: list[str],
        *,
        links: list[dict[str, Any]] | None = None,
    ) -> None:
        m = next((x for x in modules.values() if x.code == code), None)
        if m is None:
            return
        m.status = status
        m.review_checklist = list(notes)[:10] if notes else m.review_checklist
        if links is not None:
            m.implementation_map = links
        m.touch()
        self._repos.code_modules.update(m)

    def _batch_prompt(
        self,
        project: Project,
        batch: CodeBatchPlan,
        snapshot: dict[str, str],
        modules: dict[str, CodeModule],
        prior_errors: list[str],
    ) -> str:
        targets = [modules[p] for p in batch.target_paths if p in modules]
        req_ids: set[str] = set()
        api_codes: set[str] = set()
        screen_codes: set[str] = set()
        table_codes: set[str] = set()
        for m in targets:
            req_ids.update(m.related_requirement_ids)
            api_codes.update(m.related_api_ids)
            screen_codes.update(m.related_screen_ids)
            table_codes.update(m.related_table_ids)
        reqs = [
            r for r in self._repos.requirements.find(project.id, order_by="id") if r.id in req_ids
        ]
        apis = [
            a
            for a in self._repos.api_specs.find(project.id, order_by="code")
            if a.code in api_codes or a.id in api_codes
        ]
        screens = [
            s
            for s in self._repos.screens.find(project.id)
            if s.code in screen_codes or s.id in screen_codes
        ]
        tables = [
            t
            for t in self._repos.db_tables.find(project.id, order_by="code")
            if t.code in table_codes or t.id in table_codes
        ]
        deps = [d for m in targets for d in (m.depends_on or [])]
        ctx_paths = [p for p in deps if p in snapshot] + [
            p for p in snapshot if p not in deps and p not in TEMPLATE_PATHS
        ]
        ctx_files = {
            p: snapshot[p][:CONTEXT_FILE_CHARS]
            for p in ctx_paths[:MAX_CONTEXT_FILES]
            if p not in batch.target_paths
        }
        fixed = {p: snapshot[p] for p in TEMPLATE_PATHS if p in snapshot}
        parts = [
            f'<batch label="{batch.label}" kind="{batch.kind}" target_paths={json.dumps(list(batch.target_paths), ensure_ascii=False)}/>',
            "<modules>\n"
            + json.dumps(
                [
                    {
                        "path": m.path,
                        "layer": m.layer,
                        "responsibility": m.description,
                        "depends_on": m.depends_on,
                        "api_ids": m.related_api_ids,
                        "screen_ids": m.related_screen_ids,
                        "table_ids": m.related_table_ids,
                        "requirement_ids": m.related_requirement_ids,
                    }
                    for m in targets
                ],
                ensure_ascii=False,
            )
            + "\n</modules>",
            "<requirements>\n"
            + json.dumps([_req_json(r) for r in reqs], ensure_ascii=False)[:20000]
            + "\n</requirements>",
            "<apis>\n"
            + json.dumps(
                [
                    a.model_dump(mode="json", exclude={"project_id", "created_at", "updated_at"})
                    for a in apis
                ],
                ensure_ascii=False,
            )[:16000]
            + "\n</apis>",
            "<screens>\n"
            + json.dumps(
                [
                    s.model_dump(mode="json", exclude={"project_id", "created_at", "updated_at"})
                    for s in screens
                ],
                ensure_ascii=False,
            )[:16000]
            + "\n</screens>",
            "<tables>\n"
            + json.dumps(
                [
                    t.model_dump(mode="json", exclude={"project_id", "created_at", "updated_at"})
                    for t in tables
                ],
                ensure_ascii=False,
            )[:12000]
            + "\n</tables>",
            "<context_files>\n" + json.dumps(ctx_files, ensure_ascii=False) + "\n</context_files>",
            "<fixed_files>\n" + json.dumps(fixed, ensure_ascii=False) + "\n</fixed_files>",
        ]
        if prior_errors:
            parts.append(
                "<errors>\n" + "\n".join(f"- {e}" for e in prior_errors[:30]) + "\n</errors>"
            )
        parts.append(
            "위 대상 파일을 완전한 코드로 작성해 files·implementation_map 을 JSON 으로 반환하라."
        )
        return "\n\n".join(parts)

    # --- 테스트 실행 --------------------------------------------------------------------------------------------
    def inspection(self, project: Project) -> dict[str, InspectionResult]:
        return inspect_all(self.workspace(project).snapshot())

    def run_tests(
        self, project: Project, *, actor: str = "user", label: str | None = None
    ) -> TestRunResult:
        inspected = self.inspection(project)
        static_errors = [e for r in inspected.values() for e in r.errors]
        if static_errors:
            raise ValidationError(
                "정적 검사 오류가 있어 테스트를 실행하지 않았습니다.",
                cause="; ".join(static_errors[:8]),
                resolution="코드 생성 결과를 고치거나 수정 루프를 실행하십시오.",
            )
        required = [t.node_id for r in inspected.values() for t in r.tests]
        n = len(self.test_results(project)) + 1
        lbl = label or f"testing#{n}"
        result = self.runner().run(self.app_dir(project), required_tests=required, label=lbl)
        out_dir = self.app_dir(project) / TEST_RESULTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"testing-{n}.json").write_text(
            result.model_dump_json(indent=1), encoding="utf-8"
        )
        req_by_node = {t.node_id: t.requirement_ids for r in inspected.values() for t in r.tests}
        module_by_path = {m.path: m.code for m in self.modules(project)}
        self._testing.record_junit(
            project, result, req_by_node=req_by_node, module_by_path=module_by_path, actor=actor
        )
        self._audit.record(
            project.id,
            "development.tested",
            actor=actor,
            payload={
                "label": lbl,
                "outcome": result.outcome.value,
                "passed": result.passed,
                "failed": result.failed,
                "errors": result.errors,
            },
        )
        return result

    def test_results(self, project: Project) -> list[TestRunResult]:
        out_dir = self.app_dir(project) / TEST_RESULTS_DIR
        results: list[TestRunResult] = []
        if not out_dir.exists():
            return results
        for p in sorted(out_dir.glob("testing-*.json"), key=lambda x: int(x.stem.split("-")[1])):
            try:
                results.append(TestRunResult.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
        return results

    def latest_test_result(self, project: Project) -> TestRunResult | None:
        results = self.test_results(project)
        return results[-1] if results else None

    # --- QA 분석·수정 루프 ------------------------------------------------------------------------------------------
    def qa_fix_round(self, project: Project, *, actor: str = "user") -> str:
        """마지막 테스트가 실패면 code_qa → code_fixer → 재검사 → 재테스트 1회. 요약 문자열을 돌려준다."""
        last = self.latest_test_result(project)
        if last is None:
            raise ValidationError(
                "테스트 결과가 없습니다.", resolution="먼저 테스트를 실행하십시오."
            )
        if last.is_success:
            return "마지막 테스트가 성공이라 수정할 것이 없습니다."
        ws = self.workspace(project)
        snapshot = ws.snapshot()
        reqs = {r.id: r for r in self._repos.requirements.find(project.id)}
        failing_paths = sorted(
            {
                c.node_id.split("::")[0]
                for c in last.failing_cases
                if "::" in c.node_id
                and c.node_id in snapshot
                or c.node_id.split("::")[0] in snapshot
            }
        )
        sources = {p: snapshot[p][:CONTEXT_FILE_CHARS] for p in failing_paths[:MAX_CONTEXT_FILES]}
        if not sources:  # 컴파일 오류 등 — 소스 전체(제한) 제공
            sources = {
                p: snapshot[p][:CONTEXT_FILE_CHARS]
                for p in list(snapshot)[:MAX_CONTEXT_FILES]
                if p not in TEMPLATE_PATHS
            }
        test_block = json.dumps(
            {
                "label": last.label,
                "summary": last.summary(),
                "failing": [
                    {"node_id": c.node_id, "outcome": c.outcome, "message": c.message[:800]}
                    for c in last.failing_cases[:20]
                ],
                "missing_required": last.missing_required[:20],
                "stdout_tail": last.stdout[-4000:],
            },
            ensure_ascii=False,
        )
        rel_req = [r for rid, r in reqs.items() if any(rid in snapshot.get(p, "") for p in sources)]
        req_block = json.dumps([_req_json(r) for r in rel_req[:20]], ensure_ascii=False)
        qa_prompt = (
            f'<test_result label="{last.label}">\n{test_block}\n</test_result>\n\n<sources>\n'
            + json.dumps(sources, ensure_ascii=False)
            + f"\n</sources>\n\n<requirements>\n{req_block}\n</requirements>\n\n실패 원인을 분류하고 파일별 수정 지시를 JSON 으로 반환하라."
        )
        try:
            qa_res = self._steps.run_role(
                project, ROLE_CODE_QA, qa_prompt, actor=actor, include_prior=False
            )
        except (AgentRunError, PWAError) as exc:
            return f"QA 분석 실패: {exc}"
        qa = (
            qa_res.output
            if isinstance(qa_res.output, CodeQaReport)
            else CodeQaReport.model_validate(qa_res.output)
        )
        self._testing.record_qa_analysis(project, last, qa, actor=actor)
        if not qa.fix_recommended:
            return f"QA: 코드 수정으로 해결 불가 — {qa.not_fixable_reason or qa.summary}"
        fix_paths = [
            i.path.replace("\\", "/")
            for i in qa.fix_instructions
            if i.path.replace("\\", "/") in snapshot
        ]
        fix_sources = {p: snapshot[p] for p in fix_paths[:MAX_CONTEXT_FILES]}
        fix_prompt = (
            "<qa_report>\n"
            + qa.model_dump_json()
            + "\n</qa_report>\n\n"
            + f'<test_result label="{last.label}">\n{test_block}\n</test_result>\n\n<sources>\n'
            + json.dumps(fix_sources, ensure_ascii=False)
            + f"\n</sources>\n\n<requirements>\n{req_block}\n</requirements>\n\n수정한 파일의 전체 내용을 edits 로 JSON 반환하라."
        )
        try:
            fix_res = self._steps.run_role(
                project, ROLE_CODE_FIXER, fix_prompt, actor=actor, include_prior=False
            )
        except (AgentRunError, PWAError) as exc:
            return f"수정 에이전트 실패: {exc}"
        fix = (
            fix_res.output
            if isinstance(fix_res.output, CodeFixReport)
            else CodeFixReport.model_validate(fix_res.output)
        )
        errors: list[str] = []
        for e in fix.edits:
            rel = e.path.replace("\\", "/")
            try:
                ws.write(rel, e.content, allow_new=False)
            except PathSecurityError as exc:
                errors.append(str(exc))
        inspected = inspect_all(ws.snapshot())
        known_ids = set(reqs)
        for r in inspected.values():
            errors.extend(r.errors)
            if is_test_file(r.path):
                errors.extend(check_test_rules(r, known_ids))
        if errors:
            ws.restore(snapshot)
            return "수정 결과 정적 검사 실패 — 되돌림: " + "; ".join(errors[:5])
        self._audit.record(
            project.id,
            "development.fixed",
            actor=actor,
            payload={"edits": [e.path for e in fix.edits]},
        )
        result = self.run_tests(project, actor=actor)
        self._testing.record_fix(project, last, result, fix, actor=actor)
        return f"수정 {len(fix.edits)}개 파일 → 재테스트 {result.summary()}"

    def qa_fix_loop(
        self, project: Project, *, actor: str = "user", max_rounds: int | None = None
    ) -> list[str]:
        rounds = max_rounds or self._settings.code_fix_rounds
        notes: list[str] = []
        for i in range(rounds):
            last = self.latest_test_result(project)
            if last is None or last.is_success:
                break
            notes.append(f"{i + 1}회차: " + self.qa_fix_round(project, actor=actor))
        return notes

    def summary(self, project: Project) -> str:
        mods = self.modules(project)
        gen = sum(1 for m in mods if m.status == "generated")
        last = self.latest_test_result(project)
        return f"생성 모듈 {gen}/{len(mods)}, 작업 폴더 {self.app_dir(project).name}, " + (
            f"최근 테스트 {last.label}: {last.summary()}" if last else "테스트 실행 없음"
        )


def _req_json(r: Requirement) -> dict[str, Any]:
    a = r.analysis or {}
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description[:600],
        "acceptance_criteria": r.acceptance_criteria,
        "verification_method": r.verification_method,
        "business_rules": a.get("business_rules", []),
        "io": a.get("inputs_outputs", []),
        "failure_recovery": a.get("failure_recovery", []),
        "mandatory": r.is_mandatory,
        "accepted": r.acceptance_status != AcceptanceStatus.REJECTED,
    }


def now_label() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


__all__ = [
    "ROLE_CODE_FIXER",
    "ROLE_CODE_QA",
    "ROLE_DEVELOPER",
    "DevelopmentService",
    "GenerationOutcome",
]
