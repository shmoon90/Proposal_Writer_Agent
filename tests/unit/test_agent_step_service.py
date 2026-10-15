"""역할 실행 서비스·기술 조사·오케스트레이터 (FakeAgentRunner)."""

from __future__ import annotations

import json

import pytest

from fixtures import builders as bld
from proposal_agent.agents import FakeAgentRunner
from proposal_agent.config import AgentRunError
from proposal_agent.models import (
    DocumentKind,
    FeasibilityVerdict,
    GateStatus,
    Project,
    ProjectMode,
    SourceTrust,
    StepStatus,
)
from proposal_agent.orchestrator import GateBlockedError, StepRunner
from proposal_agent.research import ResearchTopic, classify_url
from proposal_agent.services import AppContext, Services
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok

RFP_ANALYSIS = {
    "overview": "민원 통합 플랫폼",
    "client_goals": ["서비스 품질"],
    "scope_summary": "통합",
    "sections": [],
    "constraints": ["표준프레임워크 4.x"],
    "evaluation_criteria": ["기술 90"],
    "schedule_hints": ["10개월"],
    "budget_hints": ["12억"],
    "named_solutions": ["전자정부 표준프레임워크 4.x"],
    "integration_targets": ["행정정보공동이용"],
    "uncertainties": [],
}

RESEARCH = {
    "items": [
        {
            "topic": "명시 솔루션: 전자정부 표준프레임워크 4.x",
            "related_requirement_ids": ["CON-001"],
            "summary": "표준프레임워크 4.x는 Spring Boot 기반",
            "confirmed_facts": ["4.x는 Spring Boot 2.7 기반"],
            "applicability_conditions": ["JDK 17"],
            "unverified_items": [],
            "impact_on_implementation": "Spring 생태계",
            "impact_on_proposal": "표준 준수 강조",
            "feasibility": "feasible",
            "risks": [],
            "recommended_stack": ["Spring Boot"],
            "sources": [
                {
                    "url": "https://www.egovframe.go.kr/home/sub.do?menuNo=41",
                    "title": "eGovFrame",
                    "product": "eGovFrame",
                    "version": "4.2",
                    "trust": "official_doc",
                    "excerpt": "Spring Boot 기반",
                }
            ],
        },
        {
            "topic": "비기능 검증: 응답 시간",
            "related_requirement_ids": ["NFR-001"],
            "summary": "근거 없음",
            "confirmed_facts": ["2초 응답은 흔한 기준"],
            "applicability_conditions": [],
            "unverified_items": [],
            "impact_on_implementation": "",
            "impact_on_proposal": "",
            "feasibility": "feasible",
            "risks": [],
            "recommended_stack": [],
            "sources": [],
        },
        {
            "topic": "커뮤니티 출처",
            "related_requirement_ids": [],
            "summary": "블로그 근거",
            "confirmed_facts": ["x"],
            "applicability_conditions": [],
            "unverified_items": [],
            "impact_on_implementation": "",
            "impact_on_proposal": "",
            "feasibility": "feasible_with_risk",
            "risks": [],
            "recommended_stack": [],
            "sources": [
                {
                    "url": "https://velog.io/@someone/post",
                    "title": "blog",
                    "trust": "official_doc",
                    "excerpt": "...",
                }
            ],
        },
    ],
    "comparisons": [
        {
            "area": "framework",
            "rfp_specified": "전자정부 표준프레임워크 4.x",
            "alternatives": [
                {
                    "name": "Java/Spring Boot",
                    "scores": {"rfp_fit": "상 — 명시", "security": "상"},
                    "license_and_cost": "Apache 2.0",
                }
            ],
            "recommendation": "Java/Spring Boot",
            "rationale": "RFP 명시",
            "unverified_items": [],
        }
    ],
    "notes": "",
}


@pytest.fixture
def fake_runner() -> FakeAgentRunner:
    return FakeAgentRunner(
        {
            "requirement_extractor": extractor_from_text,
            "requirement_verifier": verifier_all_ok,
            "rfp_analyst": RFP_ANALYSIS,
            "tech_researcher": RESEARCH,
            "architect": {
                "components": [
                    {"code": "WEB01", "layer": "web", "name": "Web", "technology": "nginx"}
                ],
                "connections": [],
                "diagram_notes": "",
                "assumptions": [],
                "open_questions": [],
            },
        }
    )


@pytest.fixture
def services(ctx: AppContext, fake_runner: FakeAgentRunner) -> Services:
    return Services.from_context(ctx, runner=fake_runner)


@pytest.fixture
def baseline_project(services: Services) -> Project:
    p = services.projects.create(name="에이전트 단계", mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    runner = StepRunner(services)
    runner.run_extraction(p)
    runner.run_requirement_extraction(p)
    runner.run_verification(p)
    assert services.gates.state(p, "gate1").status == GateStatus.PASS
    return p


def test_rfp_analysis_requires_gate0_and_saves_versioned_output(
    services: Services, fake_runner: FakeAgentRunner
) -> None:
    p = services.projects.create(name="게이트 전", mode=ProjectMode.PROPOSAL)
    with pytest.raises(GateBlockedError):
        StepRunner(services).run_rfp_analysis(p)
    services.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    StepRunner(services).run_extraction(p)
    outcome = StepRunner(services).run_rfp_analysis(p)
    assert outcome.run.status == StepStatus.APPROVED
    rec = services.ctx.repos.agent_outputs.latest(p.id, "rfp_analyst")
    assert (
        rec
        and rec.version == "v1.0"
        and rec.file_path.endswith("02_RFP_Analysis/rfp_analysis_v1.0.json")
    )
    saved = json.loads(services.ctx.paths.resolve_output(rec.file_path).read_text(encoding="utf-8"))
    assert saved["named_solutions"] == ["전자정부 표준프레임워크 4.x"]
    req = fake_runner.calls[-1]
    assert (
        req.role == "rfp_analyst"
        and "<document>" in req.prompt
        and "mcp__pwa__search_source_text" in req.allowed_tools
    )
    assert "pwa" in req.mcp_servers and req.mcp_servers["pwa"]["type"] == "sdk"
    assert req.builtin_tools == () and req.timeout_s == 600
    StepRunner(services).run_rfp_analysis(p)
    assert (
        services.ctx.repos.agent_outputs.latest(p.id, "rfp_analyst").version == "v1.1"
    )  # 덮어쓰기 없이 새 버전


def test_prior_outputs_are_reused_in_prompt(
    services: Services, baseline_project: Project, fake_runner: FakeAgentRunner
) -> None:
    runner = StepRunner(services)
    runner.run_rfp_analysis(baseline_project)
    runner.run_tech_research(baseline_project)
    research_req = next(c for c in fake_runner.calls if c.role == "tech_researcher")
    assert (
        '<prior role="rfp_analyst">' in research_req.prompt
        and "전자정부 표준프레임워크" in research_req.prompt
    )
    assert (
        research_req.builtin_tools == ("WebSearch", "WebFetch")
        and "WebFetch" in research_req.allowed_tools
    )
    rec = services.ctx.repos.agent_outputs.latest(baseline_project.id, "tech_researcher")
    assert rec and rec.inputs_used == ["rfp_analyst"]
    outcome = runner.run_role_step(baseline_project, "architecture", "architect", "설계하라")
    arch_req = fake_runner.calls[-1]
    assert (
        '<prior role="tech_researcher">' in arch_req.prompt
        and '<prior role="rfp_analyst">' in arch_req.prompt
    )
    assert outcome.run.status == StepStatus.APPROVED


def test_tech_research_requires_gate1_and_records_sources_and_unverified(
    services: Services, baseline_project: Project
) -> None:
    runner = StepRunner(services)
    outcome = runner.run_tech_research(baseline_project)
    assert outcome.run.status == StepStatus.NEEDS_REVIEW  # 게이트 2: 조사 결과 사람 검토
    items = services.research.list_research(baseline_project)
    assert len(items) == 3
    by_topic = {t.topic: t for t in items}
    official = by_topic["명시 솔루션: 전자정부 표준프레임워크 4.x"]
    assert (
        official.sources[0].trust == SourceTrust.OFFICIAL_DOC
        and official.sources[0].trust_by_rule == SourceTrust.OFFICIAL_DOC
    )
    assert official.confirmed_facts and official.feasibility == FeasibilityVerdict.FEASIBLE
    assert (
        official.sources[0].product == "eGovFrame"
        and official.sources[0].version == "4.2"
        and official.investigated_at
    )
    nosrc = by_topic["비기능 검증: 응답 시간"]
    assert nosrc.confirmed_facts == [] and nosrc.feasibility == FeasibilityVerdict.UNKNOWN
    assert any("출처 없음" in u for u in nosrc.unverified_items)
    community = by_topic["커뮤니티 출처"]
    assert (
        community.sources[0].trust == SourceTrust.COMMUNITY
    )  # 규칙이 블로그를 공식 문서로 올리지 못하게 함
    study = services.research.latest_study(baseline_project)
    assert (
        study
        and study.comparisons[0].rfp_specified
        and any("미평가 기준" in u for u in study.comparisons[0].unverified_items)
    )


def test_tech_research_blocked_without_gate1(services: Services) -> None:
    p = services.projects.create(name="조사 차단", mode=ProjectMode.PROPOSAL)
    with pytest.raises(GateBlockedError):
        StepRunner(services).run_tech_research(p)
    assert services.ctx.repos.step_runs.find(p.id) == []


def test_identify_topics_is_deterministic(services: Services, baseline_project: Project) -> None:
    topics = services.research.identify_topics(baseline_project, RFP_ANALYSIS)
    names = [t.topic for t in topics]
    assert "명시 솔루션: 전자정부 표준프레임워크 4.x" in names
    assert any(t.startswith("연계 대상 인터페이스") for t in names)
    assert any(t.startswith("비기능 검증") and t for t in names)
    assert any(t.startswith("제약 기술 검토") for t in names)
    again = [t.topic for t in services.research.identify_topics(baseline_project, RFP_ANALYSIS)]
    assert names == again
    assert isinstance(topics[0], ResearchTopic)


def test_agent_failure_recovery(
    services: Services, baseline_project: Project, fake_runner: FakeAgentRunner
) -> None:
    fake_runner.responders["rfp_analyst"] = AgentRunError(
        "rate", subtype="success", detail={"category": "rate_limit"}
    )
    with pytest.raises(AgentRunError):
        StepRunner(services).run_rfp_analysis(baseline_project)
    run = services.ctx.repos.step_runs.latest(baseline_project.id, "rfp_analysis")
    assert run.status == StepStatus.FAILED and run.error["resolution"]
    errors = services.ctx.repos.audit.recent(baseline_project.id, errors_only=True)
    assert any(
        e.action == "agent.rfp_analyst.failed" and e.payload["category"] == "rate_limit"
        for e in errors
    )
    assert any(e.action == "step.failed" for e in errors)
    fake_runner.responders["rfp_analyst"] = RFP_ANALYSIS
    outcome = StepRunner(services).run_rfp_analysis(baseline_project)
    assert outcome.run.attempt == 2 and outcome.run.status == StepStatus.APPROVED


def test_audit_payload_has_tool_calls_and_no_secrets(
    services: Services, baseline_project: Project
) -> None:
    StepRunner(services).run_rfp_analysis(baseline_project)
    ev = next(
        e
        for e in services.ctx.repos.audit.recent(baseline_project.id)
        if e.action == "agent.rfp_analyst.completed"
    )
    assert (
        "tool_calls" in ev.payload
        and "cost_usd" in ev.payload
        and "sk-" not in json.dumps(ev.payload)
    )


def test_classify_url_rules() -> None:
    assert classify_url("https://learn.microsoft.com/dotnet") == SourceTrust.OFFICIAL_DOC
    assert classify_url("https://www.ietf.org/rfc/rfc9110") == SourceTrust.STANDARD
    assert classify_url("https://stackoverflow.com/q/1") == SourceTrust.COMMUNITY
    assert classify_url("https://vendor.example/docs/guide") == SourceTrust.VENDOR_GUIDE
    assert classify_url("https://unknown.example/page") == SourceTrust.UNKNOWN
    assert classify_url("not a url") == SourceTrust.UNKNOWN


def test_generation_steps_blocked_until_gate1(services: Services) -> None:
    p = services.projects.create(name="생성 차단", mode=ProjectMode.PROPOSAL)
    with pytest.raises(GateBlockedError):
        StepRunner(services).run_role_step(p, "proposal_ppt", "proposal_writer", "작성")
    with pytest.raises(GateBlockedError):
        StepRunner(services).require_generation_allowed(p)
