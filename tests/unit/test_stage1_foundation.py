"""통합 개발 지시문 단계 1 — 공통 기반·실행 구조.

프로젝트 설정(§3), 공통 객체 ID·엔티티·마이그레이션(§17), 작업 진행률·중단·백그라운드(§15·§16),
실행 계획 미리보기·단계 디스패처·실패만 재실행(§16), 로그 비밀값 마스킹(§15.3)."""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal

import pytest

from proposal_agent.config.errors import ValidationError
from proposal_agent.config.logging import SecretMaskingFilter, mask_secrets
from proposal_agent.models import (
    SETTINGS_KEY,
    ApiSpec,
    CodeModule,
    DbColumn,
    DbTable,
    Decision,
    DecisionKind,
    DecisionStatus,
    Defect,
    DesignItem,
    DocumentKind,
    Negotiation,
    NegotiationStatus,
    Project,
    ProjectSettings,
    ProposalStrategy,
    StepStatus,
    TechSelectionMode,
    TechStack,
    TraceTargetType,
)
from proposal_agent.models import (
    TestCase as TcModel,
)
from proposal_agent.models import (
    TestCaseStatus as TcState,
)
from proposal_agent.orchestrator.runner import StepRunner
from proposal_agent.services import Services
from proposal_agent.storage import MIGRATIONS


# --- §3 프로젝트 설정 -------------------------------------------------------------------------
def test_project_settings_roundtrip_and_change_reason_rule(
    services: Services, proposal_project: Project
) -> None:
    assert services.projects.settings_of(proposal_project) == ProjectSettings()
    settings = ProjectSettings(
        description="민원 접수·처리 시스템 재구축",
        schedule_constraints=["10월 오픈", " "],
        budget_amount=Decimal("450000000"),
        effort_limit_mm=Decimal("40"),
        has_existing_system=True,
        tech_stack=TechStack(language="Java 8", was="JEUS 7", database="Oracle 11.2"),
        rfp_specified_tech=["전자정부 표준프레임워크"],
        deliverable_kinds=["submission_pptx", "requirement_spec_xlsx"],
        cost_rates={"PM": Decimal("12000000")},
        overhead_ratio=Decimal("0.2"),
    )
    updated = services.projects.update_settings(proposal_project, settings, actor="tester")
    assert SETTINGS_KEY in updated.settings
    again = services.projects.settings_of(services.projects.get(proposal_project.id))
    assert again.budget_amount == Decimal("450000000") and again.schedule_constraints == [
        "10월 오픈"
    ]
    assert again.tech_stack.labeled()[0] == ("개발 언어", "Java 8")
    assert any("기술 선택 모드: RFP 지정 기술 준수" in x for x in again.summary_lines())
    # RFP 명시 기술이 있는데 모드를 바꾸면 사유가 필수
    bad = again.model_copy(update={"tech_selection_mode": TechSelectionMode.AI_RECOMMEND})
    with pytest.raises(ValidationError):
        services.projects.update_settings(proposal_project, bad)
    ok = bad.model_copy(update={"tech_selection_reason": "RFP 기술이 EOL — 대안 비교 필요"})
    services.projects.update_settings(proposal_project, ok)
    events = [
        e
        for e in services.ctx.repos.audit.recent(proposal_project.id, limit=10)
        if e.action == "project.settings.updated"
    ]
    assert events and "tech_selection_mode" in (events[0].payload or {}).get("changed", [])
    with pytest.raises(ValueError):
        ProjectSettings(budget_amount=Decimal("-1"))


# --- §17 공통 객체 ID·엔티티·마이그레이션 ----------------------------------------------------------
def test_stage1_entities_persist_with_project_unique_codes(
    services: Services, proposal_project: Project
) -> None:
    repos = services.ctx.repos
    assert MIGRATIONS[-1].version >= 8
    pid = proposal_project.id
    assert repos.next_code(pid, "STR") == "STR-001" and repos.next_code(pid, "STR") == "STR-002"
    assert repos.next_code(pid, "TC") == "TC-001"  # 접두사별 독립 시퀀스
    strat = ProposalStrategy(
        project_id=pid,
        code="STR-001",
        title="상태 기반 워크플로",
        related_requirement_ids=["FR-001"],
    )
    repos.strategies.insert(strat)
    assert repos.strategies.get_by_code(pid, "STR-001").title == "상태 기반 워크플로"
    table = DbTable(
        project_id=pid,
        code="TBL-001",
        name="CASE_REQUEST",
        columns=[
            DbColumn(
                code="COL-001",
                name="REQ_ID",
                data_type="VARCHAR2",
                length="20",
                is_pk=True,
                nullable=False,
            )
        ],
        db_engine="Oracle 11.2",
    )
    repos.db_tables.insert(table)
    api = ApiSpec(
        project_id=pid,
        code="API-001",
        name="접수 등록",
        path="/api/cases",
        method="POST",
        related_table_ids=[table.id],
    )
    repos.api_specs.insert(api)
    repos.design_items.insert(
        DesignItem(project_id=pid, code="DSG-001", name="알림 배치", category="batch")
    )
    repos.code_modules.insert(
        CodeModule(project_id=pid, code="MOD-001", name="case-service", related_api_ids=[api.id])
    )
    tc = TcModel(project_id=pid, code="TC-001", name="접수 등록 정상", related_api_ids=[api.id])
    repos.test_cases.insert(tc)
    assert tc.status == TcState.DRAFT  # 실행 전에는 통과로 보지 않음
    repos.defects.insert(
        Defect(
            project_id=pid, code="DEF-001", title="필수값 누락 허용", found_in_test_case_id=tc.id
        )
    )
    assert [d.code for d in repos.defects.find(pid, status="open")] == ["DEF-001"]
    # 같은 프로젝트에서 코드 중복은 거부, 다른 프로젝트는 허용
    other = services.projects.create(name="다른 사업", mode=proposal_project.mode, created_by="t")
    repos.strategies.insert(
        ProposalStrategy(project_id=other.id, code="STR-001", title="다른 전략")
    )
    from proposal_agent.config.errors import StorageError

    with pytest.raises(StorageError):
        repos.strategies.insert(ProposalStrategy(project_id=pid, code="STR-001", title="중복"))
    # 추적 대상 종류 확장
    assert {
        TraceTargetType.STRATEGY,
        TraceTargetType.API,
        TraceTargetType.DB_TABLE,
        TraceTargetType.TEST_CASE,
    } <= set(TraceTargetType)


def test_decision_and_negotiation_binding_rules(
    services: Services, proposal_project: Project
) -> None:
    pid = proposal_project.id
    d = Decision(
        project_id=pid,
        code="DEC-001",
        title="알림 채널은 알림톡",
        kind=DecisionKind.CUSTOMER_REQUEST,
        status=DecisionStatus.APPROVED,
        approved_by="고객 PM",
    )
    assert not d.is_binding  # 고객 요청은 회의에서 나왔어도 결정이 아니다
    d2 = d.model_copy(update={"kind": DecisionKind.OFFICIAL_DECISION, "authority_confirmed": False})
    assert not d2.is_binding  # 권한 미확인
    d3 = d2.model_copy(update={"authority_confirmed": True})
    assert d3.is_binding
    services.ctx.repos.decisions.insert(d3)
    assert (
        services.ctx.repos.decisions.find(pid, kind=str(DecisionKind.OFFICIAL_DECISION))[0].code
        == "DEC-001"
    )
    n = Negotiation(
        project_id=pid,
        code="NEG-001",
        title="OTP 채널 변경",
        status=NegotiationStatus.AGREED,
        customer_agreed=None,
    )
    assert not n.can_apply_to_baseline  # 고객 합의 미확인·미승인
    assert n.model_copy(update={"customer_agreed": True, "approved_by": "PM"}).can_apply_to_baseline
    services.ctx.repos.negotiations.insert(n)


# --- §15·§16 작업 진행률·중단·백그라운드 -------------------------------------------------------
def test_step_progress_cancel_and_background_job(
    services: Services, proposal_project: Project
) -> None:
    pipeline = services.pipeline
    run = pipeline.start_step(proposal_project, "extract", actor="tester")
    pipeline.update_progress(run, 0.4, "청크 4/10 처리", resume_point={"chunk": 4})
    fresh = services.ctx.repos.step_runs.get(run.id)
    assert (
        fresh.progress == 0.4
        and fresh.progress_note.startswith("청크")
        and fresh.resume_point == {"chunk": 4}
    )
    assert fresh.heartbeat_at is not None
    rows = pipeline.plan_preview(proposal_project)
    extract_row = next(r for r in rows if r.key == "extract")
    assert extract_row.progress == 0.4 and "이미 실행 중" in extract_row.blockers
    # 백그라운드 작업: 생존 신호를 보내다가 중단 요청을 보고 멈춘다
    started = threading.Event()

    def work(cancel):  # type: ignore[no-untyped-def]
        started.set()
        for i in range(200):
            if cancel.is_cancelled or services.jobs.is_cancel_requested(run):
                return f"stopped at {i}"
            services.jobs.heartbeat(run, progress=min(0.4 + i * 0.01, 0.99), note=f"반복 {i}")
            time.sleep(0.01)
        return "finished"

    job = services.jobs.submit(proposal_project, run, work)
    assert started.wait(2.0)
    assert services.jobs.running(proposal_project.id)
    services.jobs.request_cancel(run, actor="tester")
    job.thread.join(3.0)  # type: ignore[union-attr]
    assert job.done and str(job.result).startswith("stopped")
    fresh = services.ctx.repos.step_runs.get(run.id)
    assert fresh.cancel_requested and fresh.background and "중단 요청됨" in fresh.progress_note
    # 끊긴 작업 정리: 실행 중인데 스레드가 없고 생존 신호가 오래된 경우
    from datetime import timedelta

    fresh.heartbeat_at = fresh.heartbeat_at - timedelta(minutes=30)  # type: ignore[operator]
    services.ctx.repos.step_runs.update(fresh)
    services.jobs._jobs.clear()  # 프로세스 재시작을 흉내낸다
    stale = services.jobs.stale_runs(proposal_project)
    assert [r.id for r in stale] == [run.id]
    services.jobs.mark_interrupted(proposal_project, stale[0], actor="tester")
    assert services.ctx.repos.step_runs.get(run.id).status == StepStatus.FAILED
    assert [v.definition.key for v in pipeline.failed_steps(proposal_project)] == ["extract"]


# --- §16 실행 계획·디스패처·실패만 재실행 ----------------------------------------------------------
def test_plan_preview_dispatcher_and_rerun_failed(
    services: Services, proposal_project: Project
) -> None:
    runner = StepRunner(services)
    rows = services.pipeline.plan_preview(proposal_project, ["extract", "qa"])
    by_key = {r.key: r for r in rows}
    assert by_key["extract"].selected and by_key["qa"].selected and not by_key["upload"].selected
    assert "선행 단계 미완료" in by_key["qa"].blockers and not by_key["qa"].runnable
    with pytest.raises(ValidationError):
        runner.run_step(proposal_project, "upload")
    # Gate 0 통과 전 요구사항 추출은 게이트 차단 → 실패 메시지와 함께 멈춘다(stop_on_failure)
    results = runner.run_steps(proposal_project, ["req_extract", "req_verify"])
    assert results[0][0] == "req_extract" and results[0][1] is None and "실패" in results[0][2]
    assert len(results) == 1
    # 실패로 기록된 단계(추출)를 만든다 — 실제 실패 경로(fail_step)와 같은 상태
    failed_run = services.pipeline.start_step(proposal_project, "extract", actor="tester")
    services.pipeline.fail_step(proposal_project, failed_run, ValidationError("추출 실패 재현"))
    # RFP 를 올린 뒤 실패 단계만 재실행하면 추출이 완료된다
    services.documents.register_upload(
        proposal_project,
        kind=DocumentKind.RFP,
        file_name="rfp.txt",
        data="1. 사업 개요\n본 사업은 민원 접수 시스템을 구축한다.\n2. 요구사항\n시스템은 접수 화면을 제공하여야 한다.\n".encode(),
        actor="tester",
    )
    failed_keys = [v.definition.key for v in services.pipeline.failed_steps(proposal_project)]
    assert failed_keys == ["extract"]
    rerun = runner.rerun_failed(proposal_project)
    assert rerun and rerun[0][0] == "extract" and rerun[0][1] is not None
    assert services.pipeline.failed_steps(proposal_project) == []


# --- §15.3 로그 비밀값 마스킹 -----------------------------------------------------------------
def test_secret_masking_filter() -> None:
    assert mask_secrets("key sk-ant-api03-ABCDEFGH12345678 used") == "key sk-ant-*** used"
    assert mask_secrets("ANTHROPIC_API_KEY=abcd1234efgh") == "ANTHROPIC_API_KEY=***"
    assert mask_secrets("Authorization: Bearer-xyz-1234") == "Authorization: ***"
    rec = logging.LogRecord(
        "t", logging.INFO, "f", 1, "token=%s path=%s", ("sk-ant-secretvalue123", "/x"), None
    )
    assert SecretMaskingFilter().filter(rec)
    assert rec.getMessage() == "token=sk-ant-*** path=/x"
