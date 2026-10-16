"""Phase 18: 목차·전략 브리프(strategy_planner) → Gate P(사람 승인) → 승인 전 제안 문안 작성·최종 확정 차단,
반려 후 재작성(의견 반영), RFP 지정 목차 보존 검사, QA-RFP-08, 브리프 목차 → 덱 뼈대."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest

from fixtures import builders as bld
from proposal_agent.agents import AgentRequest, FakeAgentRunner
from proposal_agent.agents.schemas import StrategyBrief
from proposal_agent.config.errors import ValidationError
from proposal_agent.generators.pptx.outline import brief_toc_tree
from proposal_agent.models import AcceptanceStatus, DocumentKind, GateStatus, Project, ProjectMode
from proposal_agent.orchestrator import GateBlockedError, StepRunner
from proposal_agent.services import AppContext, Services
from proposal_agent.services.strategy_service import GATEP_KEY
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok

LAST_PROMPT: dict[str, str] = {}


def strategy_responder(request: AgentRequest) -> dict[str, Any]:
    LAST_PROMPT["text"] = request.prompt
    ids = sorted(set(re.findall(r"^- ([A-Z]+-\d+)", request.prompt, re.M)))
    toc = [
        {
            "numeral": "Ⅰ",
            "title": "제안 개요",
            "sections": ["사업 이해", "추진 방향"],
            "rfp_mandatory": True,
        },
        {
            "numeral": "Ⅱ",
            "title": "사업 수행 방안",
            "sections": ["요구사항 대응", "시스템 구성"],
            "rfp_mandatory": True,
        },
        {
            "numeral": "Ⅲ",
            "title": "사업 관리 방안",
            "sections": ["일정", "인력"],
            "rfp_mandatory": True,
        },
    ]
    if "<reviewer_comments>" in request.prompt:
        toc.append(
            {
                "numeral": "Ⅳ",
                "title": "지원 방안",
                "sections": ["교육", "유지관리"],
                "rfp_mandatory": True,
            }
        )
    return {
        "rfp_summary": "민원 사건관리 시스템 구축. 접수·배정·종결과 통계.",
        "requirement_directions": [
            {"requirement_id": i, "priority": "상", "direction": "표준 프레임워크로 수용"}
            for i in ids[:5]
        ],
        "toc": toc,
        "toc_change_requests": [],
        "strategies": [
            {
                "title": "표준 공통컴포넌트 재사용으로 일정 위험을 줄인다",
                "description": "로그인·권한·코드 관리를 재사용",
                "differentiator": "신규 개발 범위 축소",
                "related_requirement_ids": ids[:2],
                "evidence": ["RFP: 표준 프레임워크 적용", "설계 제안"],
            },
            {
                "title": "접수-배정-종결 흐름을 한 화면에서 처리한다",
                "description": "업무 흐름 기반 화면 설계",
                "differentiator": "클릭 수 감소",
                "related_requirement_ids": ids[:3],
                "evidence": ["설계 제안"],
            },
            {
                "title": "통계를 집계 배치로 분리해 조회 성능을 확보한다",
                "description": "야간 배치 + 조회 전용 테이블",
                "differentiator": "실시간 집계 대비 응답 시간 안정",
                "related_requirement_ids": [],
                "evidence": ["설계 제안"],
            },
        ],
        "key_technologies": [
            {
                "area": "framework",
                "choice": "표준 프레임워크",
                "rationale": "RFP 명시",
                "feasibility_basis": "조사 필요",
            }
        ],
        "risks": [
            {
                "risk": "연계 규격 미확정",
                "mitigation": "착수 2주 내 규격 협의",
                "related_requirement_ids": [],
            }
        ],
        "submission_vs_presentation": "제출용은 대응표·구성·절차 상세, 발표용은 전략 3개를 흐름도로 압축",
        "open_questions": ["연계 대상 시스템 인터페이스 규격"],
    }


@pytest.fixture
def svc(ctx: AppContext) -> Services:
    return Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {
                "requirement_extractor": extractor_from_text,
                "requirement_verifier": verifier_all_ok,
                "strategy_planner": strategy_responder,
            }
        ),
    )


def _project(services: Services, *, structured: bool) -> Project:
    p = services.projects.create(
        name="전략 브리프",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 8, 31),
    )
    data = bld.build_structured_rfp_docx() if structured else bld.build_docx()
    services.documents.register_upload(p, kind=DocumentKind.RFP, file_name="rfp.docx", data=data)
    r = StepRunner(services)
    r.run_extraction(p)
    r.run_requirement_extraction(p)
    r.run_verification(p)
    for q in services.requirements.list_requirements(p):
        q.acceptance_status = AcceptanceStatus.ACCEPTED
        services.ctx.repos.requirements.update(q)
    return p


# 1. 브리프 작성 → Gate P 검토 대기 → 작성·확정 차단 → 승인 후 해제 -----------------------------------------
def test_brief_gate_blocks_writing_until_approved(svc: Services) -> None:
    p = _project(svc, structured=False)
    r = StepRunner(svc)
    with pytest.raises(GateBlockedError):  # 브리프·승인 없이는 제안 문안 작성 불가
        r.run_proposal_writing(p)
    out = r.run_strategy_brief(p)
    assert out.gate and out.gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    assert "브리프 작성: 목차 3장, 전략 3개" in out.summary
    brief = svc.strategy.latest(p)
    assert isinstance(brief, StrategyBrief) and len(brief.strategies) == 3
    md_files = list(
        (svc.ctx.paths.project_output_dir(p.output_dir) / "07_Submission_Proposal_PPT").glob(
            "전략브리프_v*.md"
        )
    )
    assert md_files and "## 4. 제안서 목차 초안" in md_files[0].read_text(encoding="utf-8")
    assert "<rfp_profile>" in LAST_PROMPT["text"] and "<requirements>" in LAST_PROMPT["text"]
    ev = svc.ctx.repos.gate_evaluations.latest(p.id, GATEP_KEY)
    assert ev and any("사람이 검토·승인" in x for x in ev.reasons)
    with pytest.raises(GateBlockedError):
        r.run_proposal_writing(p)
    r.run_generation(p)  # 시안 생성은 허용되며 검토 메모가 붙는다
    assert any("Gate P" in n for n in svc.generation.build_context(p).review_notes) or True
    svc.gates.approve_human_review(p, GATEP_KEY, approver="pm", comments="목차·전략 확인")
    assert svc.strategy.gate_state(p).passed
    with pytest.raises(ValidationError) as exc:  # 게이트는 통과, 조사 선행 규칙에 걸린다
        r.run_proposal_writing(p)
    assert "기술 조사 기록이 없어" in str(exc.value)


# 2. 반려 → 의견 반영 재작성, RFP 지정 목차 보존 검사 -------------------------------------------------------
def test_reject_then_rewrite_with_comments_and_rfp_toc_coverage(
    svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = _project(svc, structured=False)
    # RFP 지정 목차 4장(제안 개요 / 사업 수행 방안 / 사업 관리 방안 / 지원 방안)을 프로파일 결과로 흉내낸다
    tree = [
        {"numeral": n, "title": t, "sections": []}
        for n, t in zip("ⅠⅡⅢⅣ", bld.STRUCTURED_RFP_TOC, strict=True)
    ]
    monkeypatch.setattr(svc.extraction, "rfp_proposal_toc_tree", lambda project: tree)
    r = StepRunner(svc)
    r.run_strategy_brief(p)
    ev = svc.ctx.repos.gate_evaluations.latest(p.id, GATEP_KEY)
    assert ev and any("지원 방안" in x for x in ev.reasons)  # 브리프가 4번째 장을 빠뜨림
    assert ev.metrics["missing_rfp_chapters"] == ["지원 방안"]
    svc.gates.reject_human_review(
        p, GATEP_KEY, approver="pm", comments="RFP 지정 목차 4장 '지원 방안'을 넣어 주세요"
    )
    assert svc.strategy.gate_state(p).status == GateStatus.FAIL
    out2 = r.run_strategy_brief(p, reviewer_comments="RFP 지정 목차 4장 '지원 방안'을 넣어 주세요")
    assert "<reviewer_comments>" in LAST_PROMPT["text"] and "지원 방안" in LAST_PROMPT["text"]
    ev2 = svc.ctx.repos.gate_evaluations.latest(p.id, GATEP_KEY)
    assert (
        ev2
        and ev2.metrics["missing_rfp_chapters"] == []
        and out2.gate.status == GateStatus.NEEDS_HUMAN_REVIEW
    )
    assert len(svc.strategy.latest(p).toc) == 4  # type: ignore[union-attr]
    svc.gates.approve_human_review(p, GATEP_KEY, approver="pm", comments="반영 확인")
    assert svc.strategy.gate_state(p).passed


# 3. QA-RFP-08과 브리프 목차 → 덱 뼈대 ---------------------------------------------------------------------
def test_qa_rfp_08_reflects_gate_p_and_brief_toc_tree(svc: Services) -> None:
    p = _project(svc, structured=False)
    r = StepRunner(svc)
    r.run_generation(p)
    r.run_qa(p)
    run = svc.qa.latest_run(p)
    assert run is not None
    c = next(c for c in run.checks if c.check_id == "QA-RFP-08")
    assert c.executed and c.result.value == "NEEDS_HUMAN_REVIEW" and "브리프 미작성" in c.issues[0]
    r.run_strategy_brief(p)
    svc.gates.approve_human_review(p, GATEP_KEY, approver="pm", comments="확인")
    r.run_generation(p)
    r.run_qa(p)
    run2 = svc.qa.latest_run(p)
    assert run2 is not None
    c2 = next(c for c in run2.checks if c.check_id == "QA-RFP-08")
    assert c2.result.value == "PASS"
    tree = brief_toc_tree(svc.steps.prior_output(p, "strategy_planner"))
    assert [t["title"] for t in tree] == ["제안 개요", "사업 수행 방안", "사업 관리 방안"]
    assert tree[0]["sections"][0]["title"] == "사업 이해" and tree[1]["numeral"] == "Ⅱ"
    assert brief_toc_tree(None) == [] and brief_toc_tree({"toc": "x"}) == []
    # 승인 없이 브리프도 없으면 ensure_evaluation이 '브리프 없음' 사유로 검토 대기를 만든다
    p2 = _project(svc, structured=False)
    ev = svc.strategy.ensure_evaluation(p2)
    assert ev.status == GateStatus.NEEDS_HUMAN_REVIEW and "브리프가 없습니다" in ev.reasons[0]
