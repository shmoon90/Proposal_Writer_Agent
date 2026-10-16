"""테스트 케이스(TC)·결함(DEF)·검수·운영 이관 서비스 (단계 7).

- 테스트 계획: 설계 객체(API·화면 기능)와 요구사항 인수 기준에서 TC 를 만든다(상태 draft). 실행 결과는 JUnit(Docker) 결과에서
  들어오며 **실행하지 못한 TC 는 unverified 로 남고 완료로 보지 않는다**(지시문 §14).
- 결함: 실패 테스트마다 DEF(재현·원인·수정·재테스트·회귀), 통과하면 closed.
- 검수: 요구사항별 인수 TC(level=acceptance) 의 판정을 사람이 기록한다.
- 운영 이관: 설계·결정·테스트 데이터에서 체크리스트를 만든다(사람이 채울 항목은 비워 둔다).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from proposal_agent.config.errors import ValidationError
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.development.models import TestRunResult
from proposal_agent.models import (
    AcceptanceStatus,
    CodeModule,
    Defect,
    DefectStatus,
    Project,
    Requirement,
    TestCase,
    TestCaseStatus,
    TestLevel,
    utcnow,
)
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

QA_SUBDIR = "11_QA_Validation_Reports"
FINAL_SUBDIR = "13_Final_Deliverables"
_LEVEL_LABEL = {
    TestLevel.UNIT: "단위",
    TestLevel.INTEGRATION: "통합",
    TestLevel.UI: "화면",
    TestLevel.PERFORMANCE: "성능",
    TestLevel.SECURITY: "보안",
    TestLevel.ACCEPTANCE: "인수",
    TestLevel.REGRESSION: "회귀",
}


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


class TestingService:
    def __init__(
        self, repos: Repositories, audit: AuditService, paths: ProjectPaths, files: FileStore
    ) -> None:
        self._repos = repos
        self._audit = audit
        self._paths = paths
        self._files = files

    # --- 조회 ------------------------------------------------------------------------------------------
    def test_cases(self, project: Project) -> list[TestCase]:
        return self._repos.test_cases.find(project.id, order_by="code")

    def defects(self, project: Project) -> list[Defect]:
        return self._repos.defects.find(project.id, order_by="code")

    def _upsert_tc(
        self, project: Project, name: str, payload: dict[str, Any], *, actor: str
    ) -> TestCase:
        existing = next(
            (t for t in self._repos.test_cases.find(project.id) if _norm(t.name) == _norm(name)),
            None,
        )
        if existing is None:
            tc = TestCase(
                project_id=project.id,
                code=self._repos.next_code(project.id, "TC"),
                name=name,
                created_by=actor,
                **payload,
            )
            self._repos.test_cases.insert(tc)
            return tc
        for k, v in payload.items():
            setattr(existing, k, v)
        existing.version += 1
        existing.touch()
        self._repos.test_cases.update(existing)
        return existing

    # --- 테스트 계획 -------------------------------------------------------------------------------------
    def plan_from_design(self, project: Project, *, actor: str = "user") -> dict[str, int]:
        """API → 통합 TC(정상 + 오류 코드), 화면 기능 → 화면 TC, 요구사항 인수 기준 → 인수 TC. 이미 있는 이름은 갱신."""
        counts = {"integration": 0, "ui": 0, "acceptance": 0}
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.acceptance_status != AcceptanceStatus.REJECTED and r.change_state != "deleted"
        ]
        modules = {
            m.code: m for m in self._repos.code_modules.find(project.id) if m.status != "dropped"
        }
        for a in self._repos.api_specs.find(project.id, order_by="code"):
            if a.status == "dropped":
                continue
            mods = [m.code for m in modules.values() if a.code in m.related_api_ids]
            self._upsert_tc(
                project,
                f"{a.code} {a.name} 정상 호출",
                {
                    "level": TestLevel.INTEGRATION,
                    "purpose": f"{a.method} {a.path} 정상 입력 → 응답",
                    "preconditions": [f"인증: {a.auth or '없음'}"],
                    "input_data": "; ".join(a.request_schema.get("fields", [])),
                    "procedure": [f"{a.method} {a.path} 호출", "응답 코드·본문 확인"],
                    "expected_result": a.response_schema.get("description", ""),
                    "status": TestCaseStatus.DRAFT,
                    "related_requirement_ids": list(a.related_requirement_ids),
                    "related_api_ids": [a.code],
                    "related_screen_ids": list(a.related_screen_ids),
                    "related_module_ids": mods,
                },
                actor=actor,
            )
            counts["integration"] += 1
            for ec in a.error_codes[:6]:
                self._upsert_tc(
                    project,
                    f"{a.code} {a.name} 오류 {ec.split(':')[0].strip()}",
                    {
                        "level": TestLevel.INTEGRATION,
                        "purpose": f"오류 조건: {ec}",
                        "procedure": [
                            f"{a.method} {a.path} 를 오류 조건으로 호출",
                            "오류 코드·메시지 확인",
                        ],
                        "expected_result": ec,
                        "status": TestCaseStatus.DRAFT,
                        "related_requirement_ids": list(a.related_requirement_ids),
                        "related_api_ids": [a.code],
                        "related_module_ids": mods,
                    },
                    actor=actor,
                )
                counts["integration"] += 1
        for s in self._repos.screens.find(project.id):
            if getattr(s, "status", "") == "dropped":
                continue
            for fn in getattr(s, "functions", []) or []:
                self._upsert_tc(
                    project,
                    f"{s.code or s.id} {s.name} — {fn.get('name', '')}",
                    {
                        "level": TestLevel.UI,
                        "purpose": fn.get("process", ""),
                        "preconditions": [f"계기: {fn.get('trigger', '')}"],
                        "input_data": "; ".join(fn.get("inputs", [])),
                        "procedure": [fn.get("trigger", "화면 진입"), "입력 후 처리 확인"],
                        "expected_result": "; ".join(fn.get("outputs", [])) or "설계대로 표시",
                        "status": TestCaseStatus.DRAFT,
                        "related_requirement_ids": list(
                            fn.get("requirement_ids", [])
                            or getattr(s, "related_requirement_ids", [])
                        ),
                        "related_screen_ids": [s.code or s.id],
                    },
                    actor=actor,
                )
                counts["ui"] += 1
        for r in reqs:
            if (
                r.type.value not in ("functional", "non_functional")
                or not (r.acceptance_criteria or "").strip()
            ):
                continue
            self._upsert_tc(
                project,
                f"{r.id} 인수: {r.name}",
                {
                    "level": TestLevel.ACCEPTANCE,
                    "purpose": f"검수 기준: {r.acceptance_criteria}",
                    "procedure": [f"검증 방법: {r.verification_method or '시연'}"],
                    "expected_result": r.acceptance_criteria,
                    "status": TestCaseStatus.DRAFT,
                    "related_requirement_ids": [r.id],
                },
                actor=actor,
            )
            counts["acceptance"] += 1
        self._audit.record(project.id, "testing.planned", actor=actor, payload=counts)
        return counts

    # --- 실행 결과 반입 ---------------------------------------------------------------------------------------
    def record_junit(
        self,
        project: Project,
        result: TestRunResult,
        *,
        req_by_node: dict[str, list[str]] | None = None,
        module_by_path: dict[str, str] | None = None,
        actor: str = "system",
    ) -> dict[str, int]:
        counts = {"passed": 0, "failed": 0, "skipped": 0, "defects_opened": 0, "defects_closed": 0}
        req_by_node = req_by_node or {}
        module_by_path = module_by_path or {}
        now = utcnow()
        for c in result.cases:
            path = c.node_id.split("::")[0]
            status = {
                "passed": TestCaseStatus.PASSED,
                "failed": TestCaseStatus.FAILED,
                "error": TestCaseStatus.FAILED,
            }.get(c.outcome, TestCaseStatus.UNVERIFIED)
            tc = self._upsert_tc(
                project,
                c.node_id,
                {
                    "level": TestLevel.UNIT,
                    "purpose": "JUnit (Docker 격리 실행)",
                    "actual_result": c.message[:500] if c.outcome != "passed" else "통과",
                    "status": status,
                    "error_detail": c.message[:1000] if c.outcome in ("failed", "error") else "",
                    "executed_at": now,
                    "executed_by": f"docker:{result.label}",
                    "related_requirement_ids": list(req_by_node.get(c.node_id, [])),
                    "related_module_ids": [module_by_path[path]] if path in module_by_path else [],
                },
                actor=actor,
            )
            key = (
                "passed"
                if status == TestCaseStatus.PASSED
                else "failed"
                if status == TestCaseStatus.FAILED
                else "skipped"
            )
            counts[key] += 1
            counts.update(self._sync_defect(project, tc, c.outcome, c.message, actor=actor))
        for node in result.missing_required:
            self._upsert_tc(
                project,
                node,
                {
                    "level": TestLevel.UNIT,
                    "status": TestCaseStatus.UNVERIFIED,
                    "actual_result": "실행되지 않음",
                    "executed_by": f"docker:{result.label}",
                },
                actor=actor,
            )
            counts["skipped"] += 1
        self._audit.record(
            project.id, "testing.recorded", actor=actor, payload={"label": result.label, **counts}
        )
        return counts

    def _sync_defect(
        self, project: Project, tc: TestCase, outcome: str, message: str, *, actor: str
    ) -> dict[str, int]:
        out = {"defects_opened": 0, "defects_closed": 0}
        existing = next(
            (d for d in self._repos.defects.find(project.id) if d.found_in_test_case_id == tc.id),
            None,
        )
        if outcome in ("failed", "error"):
            if existing is None:
                d = Defect(
                    project_id=project.id,
                    code=self._repos.next_code(project.id, "DEF"),
                    title=f"{tc.name} 실패"[:120],
                    severity="high" if outcome == "error" else "medium",
                    status=DefectStatus.OPEN,
                    reproduction=message[:800],
                    found_in_test_case_id=tc.id,
                    related_requirement_ids=list(tc.related_requirement_ids),
                    related_module_ids=list(tc.related_module_ids),
                    created_by=actor,
                )
                self._repos.defects.insert(d)
                tc.defect_ids.append(d.id)
                self._repos.test_cases.update(tc)
                out["defects_opened"] += 1
            elif existing.status in (DefectStatus.RETEST, DefectStatus.FIXING):
                existing.status = DefectStatus.OPEN
                existing.retest_result = "재테스트 실패: " + message[:300]
                existing.touch()
                self._repos.defects.update(existing)
        elif (
            outcome == "passed" and existing is not None and existing.status != DefectStatus.CLOSED
        ):
            existing.status = DefectStatus.CLOSED
            existing.retest_result = "재테스트 통과"
            existing.resolved_at = utcnow()
            existing.touch()
            self._repos.defects.update(existing)
            out["defects_closed"] += 1
        return out

    def record_qa_analysis(
        self, project: Project, result: TestRunResult, qa: Any, *, actor: str = "system"
    ) -> None:
        by_node = {t.name: t for t in self._repos.test_cases.find(project.id)}
        for fa in qa.failures:
            for node in fa.test_node_ids:
                tc = by_node.get(node)
                if tc is None:
                    continue
                d = next(
                    (
                        x
                        for x in self._repos.defects.find(project.id)
                        if x.found_in_test_case_id == tc.id
                    ),
                    None,
                )
                if d is None:
                    continue
                d.cause = f"[{fa.category}] {fa.root_cause}"[:800]
                d.reproduction = d.reproduction or fa.reproduction[:800]
                d.fix_plan = "; ".join(
                    i.instruction[:200]
                    for i in qa.fix_instructions
                    if node in i.related_test_node_ids
                )[:800]
                d.status = DefectStatus.ANALYZING if qa.fix_recommended else DefectStatus.OPEN
                d.touch()
                self._repos.defects.update(d)

    def record_fix(
        self,
        project: Project,
        before: TestRunResult,
        after: TestRunResult,
        fix: Any,
        *,
        actor: str = "system",
    ) -> None:
        failed_before = {c.node_id for c in before.failing_cases}
        by_node = {t.name: t for t in self._repos.test_cases.find(project.id)}
        for node in failed_before:
            tc = by_node.get(node)
            if tc is None:
                continue
            d = next(
                (
                    x
                    for x in self._repos.defects.find(project.id)
                    if x.found_in_test_case_id == tc.id
                ),
                None,
            )
            if d is None:
                continue
            d.fix_note = "; ".join(f"{e.path}: {e.change_reason[:120]}" for e in fix.edits)[:800]
            if d.status != DefectStatus.CLOSED:
                d.status = (
                    DefectStatus.RETEST
                    if any(c.node_id == node for c in after.failing_cases)
                    else d.status
                )
            d.regression_note = f"재테스트 {after.label}: {after.summary()}"[:300]
            d.touch()
            self._repos.defects.update(d)

    # --- 검수 -----------------------------------------------------------------------------------------------
    def record_acceptance(
        self,
        project: Project,
        tc_id: str,
        *,
        passed: bool,
        note: str,
        inspector: str,
        actor: str | None = None,
    ) -> TestCase:
        tc = self._repos.test_cases.get(tc_id, project.id)
        if tc.level != TestLevel.ACCEPTANCE:
            raise ValidationError(f"{tc.code}: 인수 테스트 케이스가 아닙니다.")
        if not inspector.strip():
            raise ValidationError("검수자를 입력하십시오.")
        if not passed and not note.strip():
            raise ValidationError("불합격에는 사유가 필요합니다.")
        tc.status = TestCaseStatus.PASSED if passed else TestCaseStatus.FAILED
        tc.actual_result = note[:500] or ("합격" if passed else "")
        tc.executed_at = utcnow()
        tc.executed_by = inspector.strip()
        tc.version += 1
        tc.touch()
        self._repos.test_cases.update(tc)
        self._audit.record(
            project.id,
            "testing.acceptance",
            actor=actor or inspector,
            entity_type="TestCase",
            entity_id=tc.id,
            payload={"passed": passed},
        )
        return tc

    # --- 문서 -----------------------------------------------------------------------------------------------
    def test_plan_markdown(self, project: Project) -> str:
        tcs = self.test_cases(project)
        lines = [
            f"# 테스트 계획서 — {project.name}",
            "",
            f"총 {len(tcs)}건 (단계별 계획: 단위 → 통합 → 화면 → 인수). 실행하지 못한 케이스는 '미검증' 으로 남으며 완료로 보지 않는다.",
            "",
        ]
        for level in (
            TestLevel.UNIT,
            TestLevel.INTEGRATION,
            TestLevel.UI,
            TestLevel.ACCEPTANCE,
            TestLevel.PERFORMANCE,
            TestLevel.SECURITY,
            TestLevel.REGRESSION,
        ):
            rows = [t for t in tcs if t.level == level]
            if not rows:
                continue
            lines += [
                f"## {_LEVEL_LABEL[level]} 테스트 ({len(rows)}건)",
                "",
                "| ID | 이름 | 목적 | 사전 조건 | 입력 | 절차 | 기대 결과 | 요구사항 | 상태 |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
            for t in rows:
                lines.append(
                    f"| {t.code} | {t.name} | {t.purpose} | {'; '.join(t.preconditions)} | {t.input_data} | {' → '.join(t.procedure)} | {t.expected_result} | {', '.join(t.related_requirement_ids)} | {t.status.value} |"
                )
            lines.append("")
        return "\n".join(lines) + "\n"

    def test_report_markdown(self, project: Project, results: list[TestRunResult]) -> str:
        tcs = self.test_cases(project)
        defects = self.defects(project)
        lines = [f"# 테스트 결과서 — {project.name}", ""]
        if results:
            lines += [
                "## 실행 이력 (Docker 격리 JUnit)",
                "",
                "| 실행 | 결과 | 통과 | 실패 | 오류 | 건너뜀 | 미실행 필수 | 시간(초) |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for r in results:
                lines.append(
                    f"| {r.label} | {r.outcome.value} | {r.passed} | {r.failed} | {r.errors} | {r.skipped} | {len(r.missing_required)} | {r.duration_seconds} |"
                )
            lines.append("")
        counts = {s.value: sum(1 for t in tcs if t.status == s) for s in TestCaseStatus}
        lines += (
            ["## 테스트 케이스 현황", "", "| 상태 | 건수 |", "|---|---|"]
            + [f"| {k} | {v} |" for k, v in counts.items()]
            + [""]
        )
        lines += [
            "| ID | 이름 | 수준 | 상태 | 실제 결과 | 실행 | 요구사항 | 결함 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        dcode = {d.id: d.code for d in defects}
        for t in tcs:
            lines.append(
                f"| {t.code} | {t.name} | {_LEVEL_LABEL[t.level]} | {t.status.value} | {t.actual_result[:80]} | {t.executed_by} | {', '.join(t.related_requirement_ids)} | {', '.join(dcode.get(x, x) for x in t.defect_ids)} |"
            )
        lines += [
            "",
            "## 결함",
            "",
            "| ID | 제목 | 심각도 | 상태 | 재현 | 원인 | 수정 | 재테스트 | 회귀 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for d in defects:
            lines.append(
                f"| {d.code} | {d.title} | {d.severity} | {d.status.value} | {d.reproduction[:80]} | {d.cause[:80]} | {d.fix_note[:80]} | {d.retest_result[:60]} | {d.regression_note[:60]} |"
            )
        return "\n".join(lines) + "\n"

    def acceptance_markdown(self, project: Project) -> str:
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.change_state != "deleted"
        ]
        tcs = {
            t.related_requirement_ids[0]: t
            for t in self.test_cases(project)
            if t.level == TestLevel.ACCEPTANCE and t.related_requirement_ids
        }
        lines = [
            f"# 검수 결과서 — {project.name}",
            "",
            "| 요구사항 | 이름 | 검수 기준 | 검증 방법 | 판정 | 검수자 | 일시 | 비고 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in reqs:
            if r.type.value not in ("functional", "non_functional"):
                continue
            t = tcs.get(r.id)
            verdict = (
                {TestCaseStatus.PASSED: "합격", TestCaseStatus.FAILED: "불합격"}.get(
                    t.status, "미검수"
                )
                if t
                else "인수 TC 없음"
            )
            lines.append(
                f"| {r.id} | {r.name} | {r.acceptance_criteria} | {r.verification_method or ''} | {verdict} | {t.executed_by if t else ''} | {t.executed_at.strftime('%Y-%m-%d') if t and t.executed_at else ''} | {t.actual_result[:60] if t else ''} |"
            )
        lines += [
            "",
            "판정은 사람(검수자)이 기록한 것만 유효하며, 미검수 항목은 완료로 보지 않는다.",
        ]
        return "\n".join(lines) + "\n"

    def handover_checklist_markdown(
        self, project: Project, *, decisions: list[Any] | None = None
    ) -> str:
        tables = [
            t
            for t in self._repos.db_tables.find(project.id, order_by="code")
            if t.status != "dropped"
        ]
        apis = [
            a
            for a in self._repos.api_specs.find(project.id, order_by="code")
            if a.status != "dropped"
        ]
        modules = [
            m
            for m in self._repos.code_modules.find(project.id, order_by="code")
            if m.status != "dropped"
        ]
        open_defects = [d for d in self.defects(project) if d.status != DefectStatus.CLOSED]
        unverified = [
            t
            for t in self.test_cases(project)
            if t.status in (TestCaseStatus.UNVERIFIED, TestCaseStatus.DRAFT)
        ]
        lines = [
            f"# 운영 이관 체크리스트 — {project.name}",
            "",
            f"작성 기준일 {date.today()}. [ ] 항목은 담당자가 확인 후 채운다.",
            "",
        ]
        lines += (
            ["## 1. 시스템 구성·배포", ""]
            + [
                f"- [ ] 모듈 배포 확인: {m.code} {m.path or m.name} (상태 {m.status})"
                for m in modules
            ]
            + ["- [ ] 배포 절차·롤백 절차 문서 전달", ""]
        )
        lines += (
            ["## 2. 데이터·백업", ""]
            + [
                f"- [ ] {t.code} {t.name}: 보존 정책 '{t.retention_policy or '(미정)'}', 개인정보 컬럼 {', '.join(c.name for c in t.columns if c.is_personal_data) or '없음'} — 백업·파기 주기 확인"
                for t in tables
            ]
            + [""]
        )
        lines += (
            ["## 3. 연계·모니터링", ""]
            + [
                f"- [ ] {a.code} {a.method} {a.path}: 로깅·감사 '{a.logging_audit or '(미정)'}', 타임아웃·재시도 '{a.timeout_retry or '(미정)'}' — 모니터링 항목 등록"
                for a in apis
            ]
            + [""]
        )
        lines += ["## 4. 미결 사항", ""]
        lines += [
            f"- [ ] 미해결 결함 {d.code} {d.title} ({d.status.value})" for d in open_defects
        ] or ["- 미해결 결함 없음"]
        lines += [f"- [ ] 미검증 테스트 {t.code} {t.name}" for t in unverified[:30]] or [
            "- 미검증 테스트 없음"
        ]
        for d in decisions or []:
            lines.append(f"- [ ] 미결 결정·조치 {getattr(d, 'code', '')} {getattr(d, 'title', '')}")
        lines += [
            "",
            "## 5. 교육·문서",
            "",
            "- [ ] 운영자 매뉴얼·사용자 매뉴얼 전달",
            "- [ ] 운영 담당자 교육 실시·기록",
            "- [ ] 설계서·테스트 결과서·검수 결과서 최종본 전달",
            "- [ ] 안정화 기간 지원 범위·연락 체계 합의",
        ]
        return "\n".join(lines) + "\n"

    def write_documents(
        self,
        project: Project,
        results: list[TestRunResult],
        *,
        decisions: list[Any] | None = None,
        actor: str = "user",
    ) -> list[str]:
        out = []
        for subdir, stem, text in (
            (QA_SUBDIR, "테스트계획서", self.test_plan_markdown(project)),
            (QA_SUBDIR, "테스트결과서", self.test_report_markdown(project, results)),
            (FINAL_SUBDIR, "검수결과서", self.acceptance_markdown(project)),
            (
                FINAL_SUBDIR,
                "운영이관체크리스트",
                self.handover_checklist_markdown(project, decisions=decisions),
            ),
        ):
            name = self._files.next_version_name(project.output_dir, subdir, stem, ".md")
            stored = self._files.save_bytes(project.output_dir, subdir, name, text.encode("utf-8"))
            out.append(stored.relative_path)
        self._audit.record(project.id, "testing.documents", actor=actor, payload={"files": out})
        return out


def trace_chain_issues(
    requirements: list[Requirement],
    modules: list[CodeModule],
    test_cases: list[TestCase],
    defects: list[Defect],
) -> tuple[list[str], list[str]]:
    """QA-CON-16 요구 → 설계·모듈 → 테스트 → 결함 추적 사슬.

    실패: TC·결함이 존재하지 않는 요구를 가리킴, 결함이 가리키는 TC 없음, 통과(passed) 상태인데 실행 기록(executed_at) 없음.
    검토: 수용된 필수 기능 요구에 TC 없음, 미검증·초안 TC(실행 안 됨), 미해결 결함, 생성된 모듈에 연결된 TC 없음.
    """
    fails: list[str] = []
    revs: list[str] = []
    req_ids = {r.id for r in requirements if r.change_state != "deleted"}
    tc_ids = {t.id for t in test_cases}
    covered: set[str] = set()
    for t in test_cases:
        for rid in t.related_requirement_ids:
            if rid not in req_ids:
                fails.append(f"{t.code} 가 존재하지 않는 요구 {rid} 를 가리킴")
            covered.add(rid)
        if t.status == TestCaseStatus.PASSED and t.executed_at is None:
            fails.append(f"{t.code}: 통과 상태인데 실행 기록 없음")
        if t.status in (TestCaseStatus.UNVERIFIED, TestCaseStatus.DRAFT):
            revs.append(
                f"{t.code} {t.name[:40]}: 실행되지 않음({t.status.value}) — 완료로 볼 수 없음"
            )
    for d in defects:
        if d.found_in_test_case_id and d.found_in_test_case_id not in tc_ids:
            fails.append(f"{d.code}: 발견 TC {d.found_in_test_case_id} 없음")
        for rid in d.related_requirement_ids:
            if rid not in req_ids:
                fails.append(f"{d.code} 가 존재하지 않는 요구 {rid} 를 가리킴")
        if d.status != DefectStatus.CLOSED:
            revs.append(f"{d.code} {d.title[:40]}: 미해결({d.status.value})")
    for r in requirements:
        if (
            r.change_state == "deleted"
            or r.acceptance_status == AcceptanceStatus.REJECTED
            or r.type.value != "functional"
        ):
            continue
        if r.is_mandatory and r.id not in covered:
            revs.append(f"{r.id} {r.name[:40]}: 테스트 케이스 없음")
    tc_modules = {mid for t in test_cases for mid in t.related_module_ids}
    for m in modules:
        if m.status == "generated" and m.code not in tc_modules:
            revs.append(f"{m.code} {m.path or m.name}: 생성된 모듈에 연결된 테스트 없음")
    return fails, revs


__all__ = ["FINAL_SUBDIR", "QA_SUBDIR", "TestingService", "trace_chain_issues"]
