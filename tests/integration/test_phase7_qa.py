"""Phase 7 통합 QA·회귀: 제안 E2E, 구축 E2E(승인·반려·변경 후 정합성), 자동 수정·재검증 한도, 파일 생성 실패 복구,
프로젝트 간 격리, 경로·권한, 게이트 정책(필수 실패 시 최종 완료 불가)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fixtures import builders as bld
from fixtures import excel_builders as xb
from proposal_agent.agents import FakeAgentRunner
from proposal_agent.agents.schemas import QaFinding, QaReport
from proposal_agent.config import PathSecurityError
from proposal_agent.config.paths import ensure_within
from proposal_agent.models import (
    ChangeStatus,
    Deliverable,
    DeliverableKind,
    DocumentKind,
    GateStatus,
    InputKind,
    Project,
    ProjectMode,
    QaResult,
)
from proposal_agent.orchestrator import GateBlockedError, StepRunner
from proposal_agent.services import AppContext, Services
from proposal_agent.validation.independent_qa import gate_status
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok


@pytest.fixture
def services(ctx: AppContext) -> Services:
    return Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
        ),
    )


def _proposal(services: Services, name: str = "제안 E2E") -> Project:
    p = services.projects.create(
        name=name,
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 8, 31),
        client_name="OO기관",
    )
    services.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    r = StepRunner(services)
    r.run_extraction(p)
    r.run_requirement_extraction(p)
    r.run_verification(p)
    return p


def _build(services: Services, name: str = "구축 E2E") -> Project:
    b = services.projects.create(name=name, mode=ProjectMode.BUILD)
    services.documents.register_upload(
        b,
        kind=DocumentKind.REQUIREMENT_SPEC,
        file_name="spec.xlsx",
        data=xb.build_requirement_spec(),
    )
    services.documents.register_upload(
        b, kind=DocumentKind.TRACE_MATRIX, file_name="trace.xlsx", data=xb.build_trace_matrix()
    )
    services.documents.register_upload(
        b, kind=DocumentKind.WBS, file_name="wbs.xlsx", data=xb.build_wbs()
    )
    services.documents.register_upload(
        b, kind=DocumentKind.STAFFING_PLAN, file_name="staff.xlsx", data=xb.build_staffing_plan()
    )
    services.baseline.load(b, actor="t")
    return services.ctx.repos.projects.get(b.id)


def _check(run, check_id: str):  # type: ignore[no-untyped-def]
    return next(c for c in run.checks if c.check_id == check_id)


# --- 제안 단계 전체 흐름 ------------------------------------------------------------------------
def test_proposal_full_flow_independent_qa_gates_and_finalize(services: Services) -> None:
    p = _proposal(services)
    r = StepRunner(services)
    r.run_generation(p)
    out = r.run_qa(p)
    run = services.qa.latest_run(p)
    assert (
        run is not None
        and run.counts["executed"] == 52
        and run.counts["not_run"]
        == 3  # QA-RFP-07(ID 체계 없음), QA-FILE-11(템플릿 미등록), QA-FILE-14(렌더링 꺼짐)
        and run.counts["fail"] == 0
    )
    rfp07 = next(c for c in run.checks if c.check_id == "QA-RFP-07")
    assert rfp07.applicable is False and "ID 체계" in (rfp07.not_run_reason or "")
    file11 = next(c for c in run.checks if c.check_id == "QA-FILE-11")
    assert file11.applicable is False and "템플릿" in (file11.not_run_reason or "")
    # Phase 21: 페이지 제한(모의 RFP '100쪽 이내')은 실행·통과, 렌더링은 설정이 꺼져 있어 미실행(해당 있음), 편집 가능성 10항목 실행
    file13 = next(c for c in run.checks if c.check_id == "QA-FILE-13")
    assert file13.executed and file13.result == QaResult.PASS, file13.issues
    file14 = next(c for c in run.checks if c.check_id == "QA-FILE-14")
    assert not file14.executed and not file14.applicable and "렌더링" in file14.not_run_reason
    edits = [c for c in run.checks if c.check_id.startswith("QA-EDIT-")]
    assert len(edits) == 10 and all(c.executed for c in edits)
    assert not [c for c in edits if c.result == QaResult.FAIL], [
        (c.check_id, c.issues) for c in edits
    ]
    assert "편집 가능성" in run.scope
    assert {c.check_id for c in run.checks} >= {
        "QA-RFP-01",
        "QA-TECH-01",
        "QA-CON-01",
        "QA-FILE-10",
    }
    for c in run.checks:  # 검증 ID·대상·기준·결과 필드가 모두 채워짐
        assert c.check_id and c.target and c.criteria and c.result in QaResult
    assert run.gates == {
        "gate2": "NEEDS_HUMAN_REVIEW",
        "gate3": "PASS",
        "gate4": "PASS",
        "gate5": "NEEDS_HUMAN_REVIEW",
    }
    assert (
        _check(run, "QA-TECH-01").result == QaResult.NEEDS_HUMAN_REVIEW
    )  # 기술 조사 없음 → 사람 검토
    assert (
        _check(run, "QA-CON-04").result == QaResult.PASS
        and _check(run, "QA-FILE-08").result == QaResult.PASS
    )
    report = services.ctx.paths.resolve_output(run.report_path or "")
    text = report.read_text(encoding="utf-8")
    for section in (
        "전체 검증 범위",
        "실제 실행한 테스트",
        "건수",
        "주요 발견 사항",
        "수정 내역",
        "재검증 결과",
        "미해결 위험",
        "승인 필요 항목",
        "최종 판정",
    ):
        assert section in text
    assert "QA-RFP-05" in text and Path(str(report)[:-3] + ".json").exists()
    assert "11_QA_Validation_Reports" in run.report_path
    # Gate 5 사람 승인 전 최종 확정 불가, 승인 후 가능
    with pytest.raises(GateBlockedError):
        r.run_finalize(p, approver="pm", comments="x")
    assert out.gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    services.gates.approve_human_review(p, "gate5", approver="pm", comments="검토 완료")
    with pytest.raises(GateBlockedError):  # Phase 18: 목차·전략(Gate P) 승인 없이는 최종 확정 불가
        r.run_finalize(p, approver="pm", comments="확정")
    services.strategy.evaluate(p)
    services.gates.approve_human_review(p, "gateP", approver="pm", comments="목차·전략 직접 확인")
    r.run_finalize(p, approver="pm", comments="확정")
    final = services.ctx.paths.project_output_dir(p.output_dir) / "13_Final_Deliverables"
    assert len(list(final.iterdir())) == 9


def test_mandatory_failure_blocks_final_state(services: Services) -> None:
    p = _proposal(services)
    r = StepRunner(services)
    r.run_generation(p)
    # 기준 데이터에 없는 요구사항을 PPT가 언급하는 상황을 흉내 내는 대신, 필수 검증 실패를 직접 주입해 게이트 정책을 검증
    run = services.qa.run(p, max_fix_rounds=0)
    checks = list(run.checks)
    bad = _check(run.qa_run, "QA-CON-03")  # type: ignore[arg-type]
    bad.result = QaResult.FAIL
    bad.issues = ["주입된 실패"]
    status, reasons = gate_status(checks, "gate5")
    assert status == "FAIL" and "QA-CON-03" in reasons[0]
    assert gate_status(checks, "gate3")[0] == "FAIL"
    # 비필수 항목 실패는 FAIL이 아니라 검토 필요
    soft = _check(run.qa_run, "QA-CON-08")  # type: ignore[arg-type]
    bad.result = QaResult.PASS
    soft.result = QaResult.FAIL
    assert gate_status(checks, "gate5")[0] == "NEEDS_HUMAN_REVIEW"


# --- 자동 수정·재검증 한도 ---------------------------------------------------------------------
def test_auto_fix_regenerates_missing_deliverable_and_reverifies(services: Services) -> None:
    p = _proposal(services)
    StepRunner(services).run_generation(p)
    # 파일을 지워 '파일 없음' 실패를 만든다 → 재생성으로 복구되어야 한다
    d = services.generation.latest_deliverables(p)[DeliverableKind.TRACE_MATRIX_XLSX]
    services.ctx.paths.resolve_output(d.file_path).unlink()
    run = services.qa.run(p).qa_run
    assert run is not None and run.fix_rounds == 1 and run.fixes
    c = _check(run, "QA-FILE-01")
    assert (
        c.result == QaResult.FAIL
        and c.fix_applied
        and c.reverified == QaResult.PASS
        and c.attempts == 1
    )
    assert run.counts["fixed"] >= 1 and run.gates["gate4"] == "PASS"
    latest = services.generation.latest_deliverables(p)[DeliverableKind.TRACE_MATRIX_XLSX]
    assert services.ctx.paths.resolve_output(
        latest.file_path
    ).exists()  # 폴더 기준 버전명으로 재생성됨


def test_auto_fix_limit_turns_into_human_review(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = _proposal(services)
    StepRunner(services).run_generation(p)
    # 재생성해도 고쳐지지 않는 실패: 기준 요구사항에 가짜 ID 추가 → Excel ID 집합 불일치가 계속됨
    from proposal_agent.models import Requirement, RequirementType

    services.ctx.repos.requirements.insert(
        Requirement(id="FR-999", project_id=p.id, name="유령", type=RequirementType.FUNCTIONAL)
    )
    # FR-999는 재생성하면 Excel에 포함되어 해결된다. 한도 검증을 위해 재생성 자체가 실패하게 만든다.
    monkeypatch.setattr(
        services.generation,
        "generate_all",
        lambda project, *, actor="user": (_ for _ in ()).throw(RuntimeError("생성기 고장")),
    )
    d = services.generation.latest_deliverables(p)[DeliverableKind.SUBMISSION_PPTX]
    services.ctx.paths.resolve_output(d.file_path).unlink()
    with pytest.raises(RuntimeError):
        services.qa.run(p, max_fix_rounds=2)
    monkeypatch.undo()
    # 재생성 결과에 오류가 보고되면 PWAError로 포착되어 보류 처리된다
    from proposal_agent.generators.service import GenerationResult

    monkeypatch.setattr(
        services.generation,
        "generate_all",
        lambda project, *, actor="user": GenerationResult(errors=["모의 오류"]),
    )
    run = services.qa.run(p, max_fix_rounds=2).qa_run
    assert run is not None
    c = _check(run, "QA-FILE-01")
    assert c.result == QaResult.FAIL and c.fix_applied is False and "재생성 실패" in c.fix_detail
    assert run.gates["gate4"] == "FAIL" and run.verdict == "FAIL"
    with pytest.raises(GateBlockedError):
        StepRunner(services).run_finalize(p, approver="pm", comments="x")
    monkeypatch.undo()
    run2 = services.qa.run(p, max_fix_rounds=2).qa_run
    assert (
        run2 is not None
        and run2.fix_rounds == 1
        and _check(run2, "QA-FILE-01").reverified == QaResult.PASS
    )


# --- 파일 생성 실패 복구 -------------------------------------------------------------------------
def test_generation_failure_recovery(services: Services, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _proposal(services)
    import proposal_agent.generators.service as gs

    monkeypatch.setattr(
        gs, "build_wbs_gantt", lambda ctx: (_ for _ in ()).throw(OSError("디스크 오류"))
    )
    r = StepRunner(services)
    with pytest.raises(Exception, match="일부 산출물 생성 실패"):
        r.run_generation(p)
    latest = services.generation.latest_deliverables(p)
    assert (
        DeliverableKind.WBS_GANTT_XLSX not in latest and len(latest) == 8
    )  # 실패 종류만 기록되지 않음
    run_step = services.ctx.repos.step_runs.latest(p.id, "generate_docs")
    assert run_step is not None and run_step.status.value == "failed" and run_step.error
    monkeypatch.undo()
    r.run_generation(p)
    latest = services.generation.latest_deliverables(p)
    assert (
        DeliverableKind.WBS_GANTT_XLSX in latest
        and latest[DeliverableKind.REQUIREMENT_SPEC_XLSX].version == "v1.1"
    )
    run = services.qa.run(p).qa_run
    assert run is not None and _check(run, "QA-FILE-10").result == QaResult.PASS


# --- 구축 단계 전체 흐름: 승인·반려·변경 후 정합성 -------------------------------------------------
def test_build_full_flow_change_approve_reject_and_post_change_qa(services: Services) -> None:
    b = _build(services)
    cr = services.changes.create_request(
        b,
        input_kind=InputKind.NATURAL_LANGUAGE,
        request_text="모바일 앱에서 푸시 알림을 수신하는 기능이 필요하다.\n팩스 접수 기능은 더 이상 필요 없으니 삭제해 주세요.",
        requester="홍",
        reason="r",
    )
    cr = services.changes.analyze(b, cr, use_agent=False)
    for c in cr.candidates:
        services.changes.decide_candidate(b, cr, c.id, decision="accept")
    res = services.changes.approve(b, cr, approver="PM", comments="ok")
    cr2 = services.changes.create_request(
        b,
        input_kind=InputKind.DELETE_BUTTON,
        request_text="",
        requester="홍",
        reason="r",
        selected_ids=["SFR-004"],
    )
    cr2 = services.changes.analyze(b, cr2, use_agent=False)
    cr2 = services.changes.reject(b, cr2, approver="PM", comments="범위 유지")
    assert (
        cr2.status == ChangeStatus.REJECTED
        and services.ctx.repos.requirements.get("SFR-004", b.id).change_state == "none"
    )
    run = services.qa.run(b).qa_run
    assert run is not None and run.mode == "build"
    assert run.counts["fail"] == 0 and run.fix_rounds == 0
    assert _check(run, "QA-CON-07").result == QaResult.PASS  # 변경 이력 ↔ 기준 데이터
    assert (
        _check(run, "QA-CON-02").result == QaResult.PASS
        and _check(run, "QA-FILE-08").result == QaResult.PASS
    )
    assert _check(run, "QA-FILE-07").result == QaResult.PASS  # SFR-/SNR- 혼용 ID 허용
    assert not _check(run, "QA-RFP-01").executed and "미실행" in (
        services.ctx.paths.resolve_output(run.report_path or "").read_text(encoding="utf-8")
    )
    assert run.gates["gate3"] == "PASS" and run.gates["gate4"] == "PASS"
    assert all(d.qa_status.value == "passed" for d in res.deliverables)
    # 변경 이력과 현재 기준이 어긋나면 FAIL: 삭제 반영된 요구사항을 되돌린 상황
    fax = services.ctx.repos.requirements.get("SFR-005", b.id)
    fax.change_state = "none"
    services.ctx.repos.requirements.update(fax)
    run2 = services.qa.run(b).qa_run
    assert (
        run2 is not None
        and _check(run2, "QA-CON-07").result == QaResult.FAIL
        and run2.verdict == "FAIL"
    )


# --- 프로젝트 간 데이터 격리 ---------------------------------------------------------------------
def test_project_isolation(services: Services) -> None:
    a = _build(services, "격리 A")
    b = _build(services, "격리 B")
    assert a.output_dir != b.output_dir
    ids_a = {r.id for r in services.ctx.repos.requirements.find(a.id)}
    ids_b = {r.id for r in services.ctx.repos.requirements.find(b.id)}
    assert ids_a == ids_b == {"SFR-001", "SFR-002", "SFR-003", "SFR-004", "SFR-005", "SNR-001"}
    cr = services.changes.create_request(
        a,
        input_kind=InputKind.ADD_BUTTON,
        request_text="모바일 푸시 알림 수신",
        requester="홍",
        reason="r",
    )
    cr = services.changes.analyze(a, cr, use_agent=False)
    services.changes.decide_candidate(
        a, cr, cr.candidates[0].id, decision="accept", overrides={"effort_md": 4}
    )
    services.changes.approve(a, cr, approver="PM", comments="ok")
    assert services.ctx.repos.requirements.exists(
        "SFR-006", a.id
    ) and not services.ctx.repos.requirements.exists("SFR-006", b.id)
    assert services.changes.list_requests(b) == [] and services.ctx.repos.wbs.count(b.id) == 16
    run_b = services.qa.run(b).qa_run
    assert run_b is not None and all(a.output_dir not in f for c in run_b.checks for f in c.files)
    for d in services.ctx.repos.deliverables.find(a.id):
        assert d.file_path.startswith(a.output_dir)
    # 같은 이름의 산출물 경로가 서로 다른 프로젝트 폴더에 있음
    reports_a = (
        list(
            (services.ctx.paths.project_output_dir(a.output_dir) / "11_QA_Validation_Reports").glob(
                "*.md"
            )
        )
        if (
            services.ctx.paths.project_output_dir(a.output_dir) / "11_QA_Validation_Reports"
        ).exists()
        else []
    )
    reports_b = list(
        (services.ctx.paths.project_output_dir(b.output_dir) / "11_QA_Validation_Reports").glob(
            "*.md"
        )
    )
    assert reports_b and not reports_a


# --- 경로·권한 ----------------------------------------------------------------------------------
def test_path_and_permission_checks(services: Services) -> None:
    b = _build(services)
    root = services.ctx.paths.output_root
    with pytest.raises(PathSecurityError):
        ensure_within(root / b.output_dir, root / b.output_dir / ".." / "other" / "x.xlsx")
    with pytest.raises(PathSecurityError):
        services.ctx.paths.resolve_output("../../etc/passwd")
    # 다른 프로젝트 폴더를 가리키는 산출물 레코드 → QA-FILE-09 FAIL (경로 거부), 자동 수정으로도 통과시키지 않음
    other = services.projects.create(name="타 프로젝트", mode=ProjectMode.BUILD)
    bad = Deliverable(
        project_id=b.id,
        kind=DeliverableKind.REQUIREMENT_SPEC_XLSX,
        file_path=f"{other.output_dir}/09_Excel_Deliverables/x.xlsx",
        version="v9.9",
    )
    services.ctx.repos.deliverables.insert(bad)
    run = services.qa.run(b, max_fix_rounds=0).qa_run
    assert run is not None
    c = _check(run, "QA-FILE-09")
    assert c.result == QaResult.FAIL and any("경로" in i or "파일 없음" in i for i in c.issues)
    assert run.gates["gate4"] == "FAIL" and run.verdict == "FAIL"


# --- 에이전트 독립 검토 덧붙임 (코드 판정은 유지) -------------------------------------------------
def test_agent_review_is_advisory_only(ctx: AppContext) -> None:
    def reviewer(request):  # type: ignore[no-untyped-def]
        assert "<deliverables>" in request.prompt and "code_checks" in request.prompt
        return QaReport(
            findings=[
                QaFinding(
                    target="submission_pptx", level="error", message="과장 문구", suggestion="수정"
                )
            ],
            overall="fail",
            summary="s",
        )

    services = Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {
                "requirement_extractor": extractor_from_text,
                "requirement_verifier": verifier_all_ok,
                "qa_reviewer": reviewer,
            }
        ),
    )
    p = _proposal(services)
    StepRunner(services).run_generation(p)
    run = services.qa.run(p, use_agent=True).qa_run
    assert (
        run is not None
        and run.agent_review
        and run.agent_review["executed"]
        and run.agent_review["findings"] == 1
    )
    ai = _check(run, "QA-AI-01")
    assert (
        ai.result == QaResult.NEEDS_HUMAN_REVIEW
        and not ai.mandatory
        and ai.evaluated_by == "agent:qa_reviewer"
    )
    assert (
        run.counts["fail"] == 0 and run.verdict == "NEEDS_HUMAN_REVIEW"
    )  # 에이전트 'fail'이 코드 판정을 바꾸지 않음
    # 에이전트 실패 시 미실행으로 기록
    services2 = Services.from_context(ctx, runner=FakeAgentRunner({}))
    run2 = services2.qa.run(p, use_agent=True).qa_run
    assert run2 is not None and run2.agent_review and not run2.agent_review["executed"]
