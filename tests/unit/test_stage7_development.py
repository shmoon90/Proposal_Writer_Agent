"""통합 개발 지시문 단계 7 — WBS·개발·테스트·검수·운영 이관 + RFP_JAVA 발췌 이식(D-22).

정적 검사(패키지·import·금지 호출·테스트 ID), 배치 계획(의존 순서·테스트 마지막), 작업 폴더 안전 쓰기, 템플릿,
Developer 구조화 출력 → 쓰기·검사·모듈 상태, surefire 해석 → TC·DEF 반입(실행기 스텁), QA 수정 루프(스텁 에이전트),
테스트 계획·검수 기록·추적 사슬(QA-CON-16)·문서, WBS 설계 분해, 실행 단계 디스패처. Docker 실제 실행은 PWA_RUN_DOCKER_TESTS=1 일 때만."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from proposal_agent.agents import FakeAgentRunner
from proposal_agent.config.errors import PathSecurityError, ValidationError
from proposal_agent.development.constants import APPLICATION_CLASS_PATH, POM_PATH
from proposal_agent.development.inspector import (
    check_test_rules,
    cross_check_imports,
    inspect_all,
    inspect_source,
)
from proposal_agent.development.models import TestRunResult
from proposal_agent.development.plan import dependency_order, generatable_modules, plan_batches
from proposal_agent.development.templates import pom_xml, template_files
from proposal_agent.development.test_runner import (
    DockerSandbox,
    ProcessOutcome,
    TestRunner,
    parse_surefire,
)
from proposal_agent.development.workspace import GeneratedWorkspace
from proposal_agent.models import (
    AcceptanceStatus,
    ApiSpec,
    CodeModule,
    Defect,
    DefectStatus,
    Difficulty,
    Project,
    ProjectMode,
    Requirement,
    RequirementCategory,
    RequirementType,
    Screen,
    TestCaseStatus,
    TestLevel,
    WBSItem,
    WBSLevel,
)
from proposal_agent.models import TestCase as TcModel
from proposal_agent.orchestrator import StepRunner
from proposal_agent.planning.decompose import decompose_wbs_to_modules, module_effort
from proposal_agent.services import AppContext, Services
from proposal_agent.testing.service import trace_chain_issues

SVC = "src/main/java/com/app/calc/CalcService.java"
CTRL = "src/main/java/com/app/calc/CalcController.java"
TEST = "src/test/java/com/app/calc/CalcServiceTest.java"

SVC_CODE = """package com.app.calc;

import java.math.BigDecimal;

/** 계산 엔진 */
public class CalcService {
    public BigDecimal add(BigDecimal a, BigDecimal b) {
        return a.add(b);
    }
}
"""
CTRL_CODE = """package com.app.calc;

import java.math.BigDecimal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 계산 API */
@RestController
public class CalcController {
    private final CalcService service = new CalcService();

    @GetMapping("/api/calc")
    public String calc(@RequestParam String a, @RequestParam String b) {
        return service.add(new BigDecimal(a), new BigDecimal(b)).toPlainString();
    }
}
"""
TEST_CODE = """package com.app.calc;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class CalcServiceTest {
    @Test
    @DisplayName("FR-002 TC-001: 1 + 2 = 3")
    void addsNumbers() {
        assertEquals(new BigDecimal("3"), new CalcService().add(new BigDecimal("1"), new BigDecimal("2")));
    }
}
"""


def _project() -> Project:
    return Project(
        name="개발",
        mode=ProjectMode.PROPOSAL,
        output_dir="Project_s7",
        workspace_dir="ws_s7",
        start_date=date(2026, 11, 2),
        end_date=date(2027, 4, 30),
        created_by="t",
    )


def _req(p: Project, rid: str, name: str, **kw: object) -> Requirement:
    data: dict[str, object] = {
        "id": rid,
        "project_id": p.id,
        "name": name,
        "description": name,
        "type": RequirementType.FUNCTIONAL,
        "category": RequirementCategory.BUSINESS,
        "created_by": "t",
        "acceptance_status": AcceptanceStatus.ACCEPTED,
        "acceptance_criteria": "결과가 정확하다",
        "verification_method": "시험",
        "difficulty": Difficulty("medium"),
    }
    data.update(kw)
    return Requirement(**data)  # type: ignore[arg-type]


def _modules(p: Project) -> list[CodeModule]:
    return [
        CodeModule(
            project_id=p.id,
            code="MOD-001",
            name="CalcController.java",
            path=CTRL,
            layer="controller",
            description="API",
            depends_on=[SVC],
            related_requirement_ids=["FR-002"],
            related_api_ids=["API-001"],
        ),
        CodeModule(
            project_id=p.id,
            code="MOD-002",
            name="CalcService.java",
            path=SVC,
            layer="service",
            description="엔진",
            depends_on=[],
            related_requirement_ids=["FR-002"],
        ),
        CodeModule(
            project_id=p.id,
            code="MOD-003",
            name="CalcServiceTest.java",
            path=TEST,
            layer="test",
            description="단위 테스트",
            depends_on=[SVC],
            related_requirement_ids=["FR-002"],
        ),
        CodeModule(
            project_id=p.id,
            code="MOD-004",
            name="calc.py",
            path="app/api/calc.py",
            layer="controller",
            description="규칙 밖",
            related_requirement_ids=["FR-002"],
        ),
    ]


# --- 정적 검사·배치·작업 폴더·템플릿 -----------------------------------------------------------------------------


def test_inspector_rules_and_test_ids() -> None:
    ok = inspect_source(SVC, SVC_CODE)
    assert ok.ok and "CalcService.add" in ok.symbols
    bad = inspect_source(
        SVC,
        SVC_CODE.replace("package com.app.calc;", "package com.other;").replace(
            "import java.math.BigDecimal;", "import java.math.BigDecimal;\nimport java.net.Socket;"
        )
        + "class X { void f() { Runtime.getRuntime(); } ",
    )
    msgs = "\n".join(bad.errors)
    assert (
        "package 선언" in msgs
        and "금지된 import: java.net" in msgs
        and "프로세스 실행" in msgs
        and "중괄호" in msgs
    )
    t = inspect_source(TEST, TEST_CODE)
    assert (
        t.tests
        and t.tests[0].requirement_ids == ["FR-002"]
        and t.tests[0].node_id == f"{TEST}::addsNumbers"
    )
    assert check_test_rules(t, {"FR-002"}) == [] and check_test_rules(t, {"FR-001"})[0].endswith(
        "존재하지 않는 요구사항 ID: FR-002"
    )
    no_id = inspect_source(
        TEST,
        TEST_CODE.replace('@DisplayName("FR-002 TC-001: 1 + 2 = 3")', '@DisplayName("더하기")'),
    )
    assert "요구사항 ID 가 없습니다" in check_test_rules(no_id, {"FR-002"})[0]
    results = inspect_all({CTRL: CTRL_CODE, SVC: SVC_CODE})
    assert cross_check_imports(results) == []
    orphan = inspect_all(
        {
            CTRL: CTRL_CODE.replace(
                "import java.math.BigDecimal;",
                "import java.math.BigDecimal;\nimport com.app.calc.Missing;",
            )
        }
    )
    assert any("생성되지 않은 내부 클래스" in w for w in cross_check_imports(orphan))
    js = inspect_source(
        "src/main/resources/static/app.js",
        "function go(){ eval('x'); fetch('https://evil.example') }",
    )
    assert len(js.errors) == 2 and "go" in js.symbols


def test_plan_batches_dependency_order_and_filtering() -> None:
    p = _project()
    ok, warnings = generatable_modules(_modules(p))
    assert (
        [m.code for m in ok] == ["MOD-001", "MOD-002", "MOD-003"]
        and warnings
        and "MOD-004" in warnings[0]
    )
    assert dependency_order(ok) == [SVC, CTRL]  # 의존 대상(서비스)이 먼저
    batches = plan_batches(ok, max_files=1)
    assert [b.kind for b in batches] == ["source", "source", "tests"] and batches[
        -1
    ].target_paths == (TEST,)
    assert batches[0].module_codes == ("MOD-002",)
    assert len(plan_batches(ok, max_files=5)) == 2


def test_workspace_safety_and_templates(tmp_path: Path) -> None:
    ws = GeneratedWorkspace(tmp_path / "app")
    res = ws.write(SVC, SVC_CODE)
    assert res.change_type == "CREATED" and ws.read(SVC) == SVC_CODE
    assert ws.write(SVC, SVC_CODE).change_type == "UNCHANGED"
    for bad in (
        "../x.java",
        "C:/x.java",
        "src/main/java/com/other/A.java",
        "src/main/java/com/app/a.exe",
        "src/main/resources/static/../app.js",
    ):
        with pytest.raises(PathSecurityError):
            ws.write(bad, "x")
    with pytest.raises(PathSecurityError):
        ws.write(CTRL, CTRL_CODE, allowed={SVC})
    with pytest.raises(PathSecurityError):
        ws.write(CTRL, CTRL_CODE, allow_new=False)
    with pytest.raises(PathSecurityError):
        ws.write(SVC, "x" * (200 * 1024 + 1))
    snap = ws.snapshot()
    ws.write(CTRL, CTRL_CODE)
    assert set(ws.restore(snap)) == {CTRL} and ws.read(CTRL) is None
    files = template_files(
        "샘플",
        _modules(_project())[:2],
        [ApiSpec(project_id="p", code="API-001", name="계산", method="GET", path="/api/calc")],
    )
    assert set(files) == {
        POM_PATH,
        APPLICATION_CLASS_PATH,
        "src/main/resources/application.properties",
        "README.md",
    }
    assert (
        "spring-boot-starter-validation" in pom_xml()
        and "3.4.5" in pom_xml()
        and "package com.app;" in files[APPLICATION_CLASS_PATH]
    )
    assert "GET /api/calc" in files["README.md"] and "납품 코드가 아니" in files["README.md"]


# --- 생성 → 검사 → 테스트 반입 (에이전트·실행기 스텁) ------------------------------------------------------------


def _developer(request):  # type: ignore[no-untyped-def]
    import json
    import re

    m = re.search(r"target_paths=(\[[^\]]*\])", request.prompt)
    targets = json.loads(m.group(1)) if m else []
    files = [
        {"path": path, "content": code, "purpose": "구현", "requirement_ids": ["FR-002"]}
        for path, code in ((SVC, SVC_CODE), (CTRL, CTRL_CODE), (TEST, TEST_CODE))
        if path in targets
    ]
    return {
        "files": files,
        "implementation_map": [
            {
                "requirement_id": "FR-002",
                "path": f["path"],
                "symbols": ["CalcService.add"] if f["path"] == SVC else [],
                "description": "d",
            }
            for f in files
        ],
        "notes": [],
    }


def _fake_surefire(out_dir: Path, passed: bool) -> None:
    sf = out_dir / "surefire"
    sf.mkdir(parents=True, exist_ok=True)
    body = (
        "" if passed else '<failure message="expected 3 but was 4">AssertionFailedError</failure>'
    )
    (sf / "TEST-com.app.calc.CalcServiceTest.xml").write_text(
        f'<?xml version="1.0"?><testsuite name="com.app.calc.CalcServiceTest" tests="1"><testcase classname="com.app.calc.CalcServiceTest" name="addsNumbers">{body}</testcase></testsuite>',
        encoding="utf-8",
    )


def _stub_runner(passed: bool) -> TestRunner:
    def process(cmd, *, cwd, env, timeout, stdout_path, stderr_path, on_timeout=None):  # type: ignore[no-untyped-def]
        _fake_surefire(cwd / "out", passed)
        stdout_path.write_text("Tests run: 1, Failures: 0, Errors: 0, Skipped: 0", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return ProcessOutcome(exit_code=0 if passed else 1)

    class ReadySandbox(DockerSandbox):
        def status(self):  # type: ignore[no-untyped-def]
            from proposal_agent.development.test_runner import DockerStatus

            return DockerStatus(True, True, True, "stub")

    return TestRunner(process_runner=process, docker=ReadySandbox("stub:1", executable="docker"))


def test_generate_test_and_fix_loop_with_stubs(ctx: AppContext, proposal_project: Project) -> None:
    p = proposal_project
    qa_report = {
        "summary": "덧셈 결과 오류",
        "failures": [
            {
                "test_node_ids": [f"{TEST}::addsNumbers"],
                "category": "CODE_BUG",
                "root_cause": "add 가 잘못 계산",
                "reproduction": "1+2",
                "related_requirement_ids": ["FR-002"],
            }
        ],
        "fix_recommended": True,
        "fix_instructions": [
            {
                "path": SVC,
                "instruction": "add 를 a.add(b) 로",
                "reason": "r",
                "related_test_node_ids": [f"{TEST}::addsNumbers"],
                "requirement_ids": ["FR-002"],
            }
        ],
        "not_fixable_reason": "",
        "risks": [],
    }
    fix_report = {
        "edits": [
            {
                "path": SVC,
                "content": SVC_CODE.replace("/** 계산 엔진 */", "/** 계산 엔진 (수정) */"),
                "change_reason": "덧셈 수정",
                "requirement_ids": ["FR-002"],
            }
        ],
        "implementation_map": [],
        "notes": [],
    }
    runner = FakeAgentRunner(
        {"developer": _developer, "code_qa": qa_report, "code_fixer": fix_report}, cost_per_call=0.0
    )
    s = Services.from_context(ctx, runner=runner)
    repos = s.ctx.repos
    repos.requirements.insert(_req(p, "FR-002", "덧셈"))
    for m in _modules(p):
        repos.code_modules.insert(m)
    dev = s.development
    batches, warnings = dev.plan(p, max_files=2)
    assert len(batches) == 2 and warnings
    out = dev.generate(p, actor="t", max_files=2)
    assert (
        out.errors == [] and out.batches_done == 2 and set(out.files_written) == {SVC, CTRL, TEST}
    )
    assert dev.workspace(p).read(POM_PATH) is not None  # 템플릿 자동 준비
    mods = {m.code: m for m in dev.modules(p)}
    assert mods["MOD-002"].status == "generated" and mods["MOD-002"].implementation_map[0][
        "symbols"
    ] == ["CalcService.add"]
    assert mods["MOD-004"].status != "generated"
    # 실패하는 실행기 스텁 → TC 실패 + DEF 생성 → 수정 루프(통과 스텁) → DEF 종료
    dev._runner = _stub_runner(passed=False)
    result = dev.run_tests(p, actor="t")
    assert result.failed == 1 and not result.is_success and result.label == "testing#1"
    tcs = s.testing.test_cases(p)
    tc = next(t for t in tcs if t.name == f"{TEST}::addsNumbers")
    assert (
        tc.status == TestCaseStatus.FAILED
        and tc.related_requirement_ids == ["FR-002"]
        and tc.related_module_ids == ["MOD-003"]
    )
    defects = s.testing.defects(p)
    assert (
        len(defects) == 1
        and defects[0].status == DefectStatus.OPEN
        and defects[0].found_in_test_case_id == tc.id
    )
    dev._runner = _stub_runner(passed=True)
    note = dev.qa_fix_round(p, actor="t")
    assert "재테스트" in note and "(수정)" in (dev.workspace(p).read(SVC) or "")
    d = s.testing.defects(p)[0]
    assert d.status == DefectStatus.CLOSED and "덧셈 수정" in d.fix_note and "CODE_BUG" in d.cause
    assert dev.latest_test_result(p) is not None and dev.latest_test_result(p).is_success  # type: ignore[union-attr]
    assert len(dev.test_results(p)) == 2
    # 정적 오류가 있으면 테스트를 돌리지 않는다
    dev.workspace(p).write(SVC, SVC_CODE.replace("package com.app.calc;", "package com.wrong;"))
    with pytest.raises(ValidationError):
        dev.run_tests(p, actor="t")


def test_surefire_parse_and_outcome(tmp_path: Path) -> None:
    _fake_surefire(tmp_path, passed=False)
    cases = parse_surefire(tmp_path / "surefire", {TEST})
    assert cases and cases[0].node_id == f"{TEST}::addsNumbers" and cases[0].outcome == "failed"
    r = TestRunResult(
        label="x",
        started_at=__import__("datetime").datetime.now(),
        exit_code=1,
        failed=1,
        cases=cases,
    )
    assert r.outcome.value == "failed" and r.failing_cases
    r2 = TestRunResult(
        label="y",
        started_at=__import__("datetime").datetime.now(),
        exit_code=0,
        passed=1,
        missing_required=["a"],
    )
    assert r2.outcome.value == "incomplete"
    assert (
        TestRunResult(
            label="z",
            started_at=__import__("datetime").datetime.now(),
            exit_code=None,
            runner_error="no docker",
        ).outcome.value
        == "runner_error"
    )


# --- 테스트 계획·검수·추적 사슬·문서·WBS 분해 ---------------------------------------------------------------------


def test_test_plan_acceptance_chain_and_documents(
    services: Services, proposal_project: Project
) -> None:
    p = proposal_project
    repos = services.ctx.repos
    repos.requirements.insert(_req(p, "FR-001", "접수"))
    repos.requirements.insert(_req(p, "FR-002", "덧셈", acceptance_criteria=""))
    repos.api_specs.insert(
        ApiSpec(
            project_id=p.id,
            code="API-001",
            name="접수 API",
            method="POST",
            path="/api/cases",
            error_codes=["C001: 제목 누락", "C002: 권한 없음"],
            related_requirement_ids=["FR-001"],
        )
    )
    repos.screens.insert(
        Screen(
            project_id=p.id,
            code="SCR-001",
            name="접수 화면",
            source="design",
            related_requirement_ids=["FR-001"],
            functions=[
                {
                    "name": "접수",
                    "trigger": "버튼",
                    "inputs": ["title"],
                    "process": "검증 → 저장",
                    "outputs": ["번호"],
                    "requirement_ids": ["FR-001"],
                }
            ],
        )
    )
    counts = services.testing.plan_from_design(p, actor="t")
    assert counts == {"integration": 3, "ui": 1, "acceptance": 1}
    assert services.testing.plan_from_design(p, actor="t") == counts  # 재실행해도 중복 없음
    tcs = services.testing.test_cases(p)
    assert len(tcs) == 5 and all(t.status == TestCaseStatus.DRAFT for t in tcs)
    acc = next(t for t in tcs if t.level == TestLevel.ACCEPTANCE)
    with pytest.raises(ValidationError):
        services.testing.record_acceptance(p, acc.id, passed=False, note="", inspector="검수자")
    with pytest.raises(ValidationError):
        services.testing.record_acceptance(p, tcs[0].id, passed=True, note="", inspector="검수자")
    acc = services.testing.record_acceptance(
        p, acc.id, passed=True, note="시연 확인", inspector="고객 검수자"
    )
    assert acc.status == TestCaseStatus.PASSED and acc.executed_by == "고객 검수자"
    fails, revs = trace_chain_issues(
        repos.requirements.find(p.id), [], services.testing.test_cases(p), []
    )
    assert (
        fails == []
        and any("FR-002" in r and "테스트 케이스 없음" in r for r in revs)
        and any("실행되지 않음" in r for r in revs)
    )
    bad_tc = TcModel(
        project_id=p.id,
        code="TC-099",
        name="x",
        status=TestCaseStatus.PASSED,
        related_requirement_ids=["FR-404"],
    )
    bad_def = Defect(project_id=p.id, code="DEF-099", title="y", found_in_test_case_id="nope")
    f2, _ = trace_chain_issues(repos.requirements.find(p.id), [], [bad_tc], [bad_def])
    assert (
        any("FR-404" in x for x in f2)
        and any("실행 기록 없음" in x for x in f2)
        and any("발견 TC nope 없음" in x for x in f2)
    )
    md = services.testing.acceptance_markdown(p)
    assert "| FR-001 | 접수 |" in md and "합격" in md and "FR-002" in md
    paths = services.testing.write_documents(p, [], decisions=[], actor="t")
    assert len(paths) == 4 and all(services.ctx.paths.resolve_output(x).exists() for x in paths)
    plan_md = services.testing.test_plan_markdown(p)
    assert "## 통합 테스트 (3건)" in plan_md and "## 인수 테스트 (1건)" in plan_md
    hand = services.testing.handover_checklist_markdown(p)
    assert "## 2. 데이터·백업" in hand and "API-001 POST /api/cases" in hand


def test_wbs_decompose_to_modules(services: Services, proposal_project: Project) -> None:
    p = proposal_project
    repos = services.ctx.repos
    repos.requirements.insert(_req(p, "FR-002", "덧셈", difficulty=Difficulty("high")))
    phase = WBSItem(project_id=p.id, code="2", level=WBSLevel.PHASE, name="구축", created_by="t")
    repos.wbs.insert(phase)
    act = WBSItem(
        project_id=p.id,
        code="2.1",
        parent_id=phase.id,
        level=WBSLevel.ACTIVITY,
        name="구현",
        created_by="t",
    )
    repos.wbs.insert(act)
    task = WBSItem(
        project_id=p.id,
        code="2.1.1",
        parent_id=act.id,
        level=WBSLevel.TASK,
        name="계산 기능 개발",
        related_requirement_ids=["FR-002"],
        effort_md=__import__("decimal").Decimal("5"),
        created_by="t",
    )
    repos.wbs.insert(task)
    for m in _modules(p)[:2]:
        repos.code_modules.insert(m)
    added, warnings = decompose_wbs_to_modules(repos, p, actor="t")
    assert [a.code for a in added] == ["2.1.2", "2.1.3"] and all(
        a.level == WBSLevel.TASK and a.parent_id == act.id for a in added
    )
    assert (
        added[0].related_requirement_ids == ["FR-002"] and "난이도 high" in added[0].estimate_basis
    )
    md, _ = module_effort(
        _modules(p)[1], {"FR-002": _req(p, "FR-002", "덧셈", difficulty=Difficulty("high"))}
    )
    assert md == __import__("decimal").Decimal("4.5")  # service 3MD × 1.5
    act2 = next(i for i in repos.wbs.tree(p.id) if i.code == "2.1")
    assert act2.effort_md == __import__("decimal").Decimal("5") + sum(a.effort_md for a in added)
    assert decompose_wbs_to_modules(repos, p, actor="t")[0] == []  # 재실행 중복 없음
    outcome = StepRunner(services).run_test_plan(p, actor="t")
    assert "테스트 계획" in outcome.summary and "wbs_decompose" in StepRunner.DISPATCHABLE


@pytest.mark.skipif(
    os.environ.get("PWA_RUN_DOCKER_TESTS") != "1",
    reason="Docker 격리 실행은 PWA_RUN_DOCKER_TESTS=1 일 때만",
)
def test_docker_junit_real_run(tmp_path: Path) -> None:
    ws = GeneratedWorkspace(tmp_path / "app")
    for rel, content in template_files("docker", [], []).items():
        ws.write(rel, content)
    ws.write(SVC, SVC_CODE)
    ws.write(TEST, TEST_CODE)
    runner = TestRunner()
    status = runner.docker.status()
    if not status.ready:
        pytest.skip(status.message)
    result = runner.run(tmp_path / "app", required_tests=[f"{TEST}::addsNumbers"], label="docker#1")
    assert result.is_success, result.summary() + result.stdout[-1500:]


def test_inspector_nested_generic_methods() -> None:
    code = SVC_CODE.replace(
        "public BigDecimal add(BigDecimal a, BigDecimal b) {",
        "public java.util.List<java.util.Map<String, Object>> list(String k, int page) {"
        + chr(10)
        + "        return java.util.List.of();"
        + chr(10)
        + "    }"
        + chr(10)
        + "    public BigDecimal add(BigDecimal a, BigDecimal b) {",
    )
    generic = inspect_source(SVC, code)
    assert (
        generic.ok
        and "CalcService.list" in generic.symbols
        and "CalcService.add" in generic.symbols
    )
