"""요구사항 추출·독립 검증·검토·Gate 1·오케스트레이터 (FakeAgentRunner, 모의 문서)."""

from __future__ import annotations

import re
from typing import Any

import pytest

from fixtures import builders as bld
from proposal_agent.agents import AgentRequest, FakeAgentRunner
from proposal_agent.config import ValidationError
from proposal_agent.models import (
    DocumentKind,
    GateStatus,
    Project,
    ProjectMode,
    RequirementDraft,
    RequirementStatus,
    RequirementType,
    ReviewStatus,
    ScopeClass,
    StepStatus,
    ValidationLevel,
    VerificationStatus,
)
from proposal_agent.orchestrator import GateBlockedError, StepRunner
from proposal_agent.services import AppContext, Services

_BLOCK_RE = re.compile(r'<block id="([^"]+)"[^>]*>\n(.*?)\n</block>', re.DOTALL)


def _blocks_in_prompt(prompt: str) -> list[tuple[str, str]]:
    return _BLOCK_RE.findall(prompt)


def extractor_from_text(request: AgentRequest) -> dict[str, Any]:
    """프롬프트의 block 중 'FR-/NFR-/CON-/SUB-' 항목을 요구사항으로 돌려주는 결정적 모의 추출기."""
    reqs = []
    kinds = {"FR": "functional", "NFR": "non_functional", "CON": "constraint", "SUB": "submission"}
    for bid, text in _blocks_in_prompt(request.prompt):
        m = re.search(r"(?<![A-Z])(FR|NFR|CON|SUB)-[A-Z]\.\s*(.+)", text)
        if not m:
            continue
        reqs.append(
            {
                "name": m.group(2).strip()[:40],
                "description": text.strip(),
                "type": kinds[m.group(1)],
                "scope_class": "mandatory",
                "is_mandatory": True,
                "priority": "high",
                "rfp_quote": text.strip(),
                "source_block_ids": [bid],
                "rationale": "원문 명시",
                "confidence": 0.9,
            }
        )
    return {"requirements": reqs, "unresolved_items": [], "notes": ""}


def verifier_all_ok(request: AgentRequest) -> dict[str, Any]:
    ids = re.findall(r'"id": "([A-Z]+-\d+)"', request.prompt)
    return {
        "verdicts": [{"requirement_id": i, "verdict": "verified", "comment": ""} for i in ids],
        "findings": [],
        "coverage_estimate": 1.0,
        "summary": "이상 없음",
    }


@pytest.fixture
def fake_runner() -> FakeAgentRunner:
    return FakeAgentRunner(
        {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
    )


@pytest.fixture
def services(
    ctx: AppContext, fake_runner: FakeAgentRunner
) -> Services:  # 기본 fixture를 Fake 러너로 덮어씀
    return Services.from_context(ctx, runner=fake_runner)


@pytest.fixture
def ready_project(services: Services) -> Project:
    p = services.projects.create(name="요구사항 테스트", mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    StepRunner(services).run_extraction(p)
    return p


# --- 추출 ---------------------------------------------------------------------------------


def test_extraction_blocked_until_gate0_passes(services: Services) -> None:
    p = services.projects.create(name="게이트 차단", mode=ProjectMode.PROPOSAL)
    with pytest.raises(GateBlockedError) as info:
        StepRunner(services).run_requirement_extraction(p)
    assert "Gate 0" in info.value.message
    assert services.ctx.repos.step_runs.find(p.id) == []  # 단계 시작조차 하지 않음


def test_extraction_creates_ids_sources_and_types(
    services: Services, ready_project: Project, fake_runner: FakeAgentRunner
) -> None:
    outcome, result = StepRunner(services).run_requirement_extraction(ready_project)
    assert outcome.run.status == StepStatus.APPROVED and result.chunks >= 1
    reqs = services.requirements.list_requirements(ready_project)
    ids = sorted(r.id for r in reqs)
    assert ids[:4] == ["CON-001", "CON-002", "FR-001", "FR-002"]
    assert {r.type for r in reqs} == {
        RequirementType.FUNCTIONAL,
        RequirementType.NON_FUNCTIONAL,
        RequirementType.CONSTRAINT,
        RequirementType.SUBMISSION,
    }
    assert len([r for r in reqs if r.type == RequirementType.FUNCTIONAL]) == 4
    for r in reqs:
        assert r.source_refs and r.source_refs[0].block_id and r.source_refs[0].location_label
        assert (
            r.rfp_quote
            and r.status == RequirementStatus.DRAFT
            and r.history[0].action == "extracted"
        )
    assert fake_runner.calls and fake_runner.calls[0].role == "requirement_extractor"
    assert "<document>" in fake_runner.calls[0].prompt


def test_extraction_drops_requirements_with_invalid_source(
    services: Services, ready_project: Project, fake_runner: FakeAgentRunner
) -> None:
    def bad_source(request: AgentRequest) -> dict[str, Any]:
        return {
            "requirements": [
                {
                    "name": "출처 없는 항목",
                    "description": "x",
                    "type": "functional",
                    "source_block_ids": ["blk_nope"],
                    "rfp_quote": "x",
                }
            ],
            "unresolved_items": ["판단 보류 문장"],
            "notes": "",
        }

    fake_runner.responders["requirement_extractor"] = bad_source
    _, result = StepRunner(services).run_requirement_extraction(ready_project)
    assert result.created == [] and result.dropped_missing_source == ["출처 없는 항목"]
    assert result.unresolved == ["판단 보류 문장"]
    warnings = services.ctx.repos.validations.find(ready_project.id, resolved=False)
    assert warnings and warnings[0].rule_id == "extract.missing_source"


def test_reextraction_keeps_ids(services: Services, ready_project: Project) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)
    before = {r.id: r.name for r in services.requirements.list_requirements(ready_project)}
    _, result = runner.run_requirement_extraction(ready_project)
    assert result.created == [] and len(result.updated) == len(before)
    after = {r.id: r.name for r in services.requirements.list_requirements(ready_project)}
    assert before == after
    assert services.ctx.repos.step_runs.latest(ready_project.id, "req_extract").attempt == 2


# --- 검증 + Gate 1 --------------------------------------------------------------------------


def test_verification_all_ok_passes_gate1(services: Services, ready_project: Project) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)
    outcome, vresult = runner.run_verification(ready_project)
    assert outcome.run.status == StepStatus.NEEDS_REVIEW  # 파이프라인 게이트 1은 사람 승인 단계
    assert outcome.gate and outcome.gate.status == GateStatus.PASS
    assert (
        vresult.verdicts >= len(services.requirements.list_requirements(ready_project))
        and vresult.coverage == 1.0
    )
    assert all(
        r.verification_status == VerificationStatus.VERIFIED
        and r.status == RequirementStatus.VERIFIED
        for r in services.requirements.list_requirements(ready_project)
    )
    runner.require_generation_allowed(ready_project)  # 예외 없음


def test_gate1_fails_without_verification_and_blocks_generation(
    services: Services, ready_project: Project
) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)
    gate = runner.reevaluate_gate1(ready_project)
    assert gate.status == GateStatus.FAIL and "독립 검증" in gate.evaluation.reasons[0]
    with pytest.raises(GateBlockedError):
        runner.require_generation_allowed(ready_project)


def test_gate1_needs_review_on_error_findings_and_human_approval(
    services: Services, ready_project: Project, fake_runner: FakeAgentRunner
) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)

    def verifier_with_issues(request: AgentRequest) -> dict[str, Any]:
        ids = re.findall(r'"id": "([A-Z]+-\d+)"', request.prompt)
        verdicts = [{"requirement_id": i, "verdict": "verified", "comment": ""} for i in ids]
        findings = []
        if "모드: chunk" in request.prompt and ids:
            findings.append(
                {
                    "kind": "missing_requirement",
                    "severity": "error",
                    "requirement_ids": [],
                    "message": "첨부파일 용량 요구가 누락됨",
                    "evidence_quote": "각 20MB까지",
                    "source_block_ids": [],
                }
            )
            findings.append(
                {
                    "kind": "classification",
                    "severity": "warning",
                    "requirement_ids": [ids[0]],
                    "message": "분류 재검토",
                    "suggested_fix": "scope_class 확인",
                    "suggested_scope_class": "supporting",
                }
            )
        return {
            "verdicts": verdicts,
            "findings": findings,
            "coverage_estimate": 0.8,
            "summary": "누락 의심",
        }

    fake_runner.responders["requirement_verifier"] = verifier_with_issues
    outcome, vresult = runner.run_verification(ready_project)
    assert outcome.gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    assert any(f.level == ValidationLevel.ERROR for f in vresult.findings)
    with pytest.raises(GateBlockedError):
        runner.require_generation_allowed(ready_project)
    # 반려 사유 없이는 승인 불가
    with pytest.raises(ValidationError):
        services.gates.approve_human_review(ready_project, "gate1", approver="pm", comments=" ")
    state = services.gates.approve_human_review(
        ready_project, "gate1", approver="pm", comments="누락 항목은 수동 추가함"
    )
    assert state.status == GateStatus.PASS and state.approved_by == "pm"
    runner.require_generation_allowed(ready_project)
    # error 결과를 해결하고 재평가하면 코드 기준으로도 PASS
    for f in services.requirements.open_findings(ready_project):
        if f.level == ValidationLevel.ERROR:
            services.requirements.resolve_finding(ready_project, f.id, actor="pm")
    assert runner.reevaluate_gate1(ready_project).status == GateStatus.PASS


def test_gate_fail_cannot_be_human_approved(services: Services, ready_project: Project) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)
    runner.reevaluate_gate1(ready_project)  # FAIL (미검증)
    with pytest.raises(ValidationError):
        services.gates.approve_human_review(ready_project, "gate1", approver="pm", comments="강행")


def test_gate_human_reject_turns_to_fail(
    services: Services, ready_project: Project, fake_runner: FakeAgentRunner
) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)

    def verifier_reject(request: AgentRequest) -> dict[str, Any]:
        ids = re.findall(r'"id": "([A-Z]+-\d+)"', request.prompt)
        return {
            "verdicts": [
                {
                    "requirement_id": i,
                    "verdict": "rejected" if n == 0 else "verified",
                    "comment": "근거 없음",
                }
                for n, i in enumerate(ids)
            ],
            "findings": [],
            "coverage_estimate": 0.9,
            "summary": "",
        }

    fake_runner.responders["requirement_verifier"] = verifier_reject
    outcome, _ = runner.run_verification(ready_project)
    assert outcome.gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    rejected = [
        r
        for r in services.requirements.list_requirements(ready_project)
        if r.verification_status == VerificationStatus.REJECTED
    ]
    assert rejected and rejected[0].status == RequirementStatus.DRAFT
    state = services.gates.reject_human_review(
        ready_project, "gate1", approver="pm", comments="재추출 필요"
    )
    assert state.status == GateStatus.FAIL


# --- 사람 검토 ------------------------------------------------------------------------------


def test_human_edit_review_delete_and_manual_add(
    services: Services, ready_project: Project
) -> None:
    runner = StepRunner(services)
    runner.run_requirement_extraction(ready_project)
    req = services.requirements.list_requirements(ready_project)[0]
    updated = services.requirements.update_requirement(
        ready_project,
        req.id,
        {"name": "수정된 이름", "scope_class": ScopeClass.SUPPORTING, "priority": "low"},
        actor="pm",
        note="검토 중 수정",
    )
    assert (
        updated.name == "수정된 이름"
        and updated.review_status == ReviewStatus.MODIFIED
        and updated.version == 3
    )
    assert updated.history[-1].changes["name"]["after"] == "수정된 이름"
    with pytest.raises(ValidationError):
        services.requirements.update_requirement(
            ready_project, req.id, {"id": "FR-999"}, actor="pm"
        )
    services.requirements.set_review(ready_project, req.id, ReviewStatus.APPROVED, actor="pm")
    assert services.requirements.get(ready_project, req.id).review_status == ReviewStatus.APPROVED

    with pytest.raises(ValidationError):
        services.requirements.mark_deleted(ready_project, req.id, actor="pm", reason="")
    deleted = services.requirements.mark_deleted(ready_project, req.id, actor="pm", reason="중복")
    assert deleted.status == RequirementStatus.DELETED
    assert req.id not in {r.id for r in services.requirements.list_requirements(ready_project)}
    assert req.id in {
        r.id for r in services.requirements.list_requirements(ready_project, include_deleted=True)
    }
    with pytest.raises(ValidationError):
        services.requirements.update_requirement(ready_project, req.id, {"name": "x"}, actor="pm")

    with pytest.raises(ValidationError):  # 부가 제안은 영향 메모 필수
        services.requirements.add_manual(
            ready_project,
            RequirementDraft(
                name="챗봇",
                description="민원 챗봇",
                type="functional",
                scope_class="optional_proposal",
                confidence=1.0,
            ),
            actor="pm",
        )
    added = services.requirements.add_manual(
        ready_project,
        RequirementDraft(
            name="챗봇",
            description="민원 챗봇",
            type="functional",
            scope_class="optional_proposal",
            impact_note="개발 2M/M 추가, 일정 +2주",
            confidence=1.0,
        ),
        actor="pm",
    )
    assert (
        added.id == "FR-005"
        and added.scope_class == ScopeClass.OPTIONAL_PROPOSAL
        and not added.source_refs
    )
    # 출처 없는 부가 제안은 Gate 1 '출처 없음' 조건에 걸리지 않는다 (필수/지원만 검사)
    runner.run_verification(ready_project)
    gate = runner.reevaluate_gate1(ready_project)
    assert "원본 출처가 없는" not in " ".join(gate.evaluation.reasons)


def test_custom_id_prefixes_from_project_settings(
    services: Services, ready_project: Project
) -> None:
    ready_project.settings["id_prefixes"] = {"functional": "SFR", "non_functional": "SNFR"}
    services.ctx.repos.projects.update(ready_project)
    StepRunner(services).run_requirement_extraction(ready_project)
    ids = {r.id for r in services.requirements.list_requirements(ready_project)}
    assert "SFR-001" in ids and "SNFR-001" in ids and "CON-001" in ids
    policy = services.requirements.id_policy(ready_project)
    assert policy.validate_format("SFR-001") == RequirementType.FUNCTIONAL
    with pytest.raises(ValidationError):
        policy.validate_format("FR-001")


def test_agent_failure_marks_step_failed_with_audit(
    services: Services, ready_project: Project, fake_runner: FakeAgentRunner
) -> None:
    from proposal_agent.config import AgentRunError

    fake_runner.responders["requirement_extractor"] = AgentRunError(
        "예산 초과", subtype="error_max_budget_usd"
    )
    with pytest.raises(AgentRunError):
        StepRunner(services).run_requirement_extraction(ready_project)
    run = services.ctx.repos.step_runs.latest(ready_project.id, "req_extract")
    assert (
        run.status == StepStatus.FAILED and run.error["detail"]["subtype"] == "error_max_budget_usd"
    )
    assert any(
        e.action == "step.failed"
        for e in services.ctx.repos.audit.recent(ready_project.id, errors_only=True)
    )
