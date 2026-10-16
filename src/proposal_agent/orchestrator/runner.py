"""단계 실행기 (Phase 2 범위: 문서 추출 → 요구사항 추출 → 독립 검증).

각 함수는 StepRun을 열고(PipelineService), 서비스를 호출하고, Gate를 **코드로** 평가한 뒤 완료/실패를 기록한다.
Gate 0가 PASS가 아니면 요구사항 추출을 시작하지 않고, Gate 1이 PASS가 아니면 제안서 생성 단계로 갈 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.control import CancellationToken
from proposal_agent.config.errors import PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.chunker import build_chunks
from proposal_agent.ingest.service import GATE0_KEY
from proposal_agent.models import GateStatus, Project, StepRun, StepStatus
from proposal_agent.orchestrator.gates import GateBlockedError, GateState
from proposal_agent.requirements.service import GATE1_KEY, ExtractionSummary, VerificationSummary
from proposal_agent.services.strategy_service import GATEP_KEY
from proposal_agent.validation.qa_service import GATE5_KEY

if TYPE_CHECKING:
    from proposal_agent.services import Services

log = get_logger("orchestrator.runner")

STEP_EXTRACT = "extract"
STEP_REQ_EXTRACT = "req_extract"
STEP_REQ_VERIFY = "req_verify"
GENERATION_STEPS = ("generate_docs", "proposal_ppt", "finalize")


@dataclass
class StepOutcome:
    run: StepRun
    gate: GateState | None = None
    summary: str = ""


class StepRunner:
    def __init__(self, services: Services) -> None:
        self._s = services

    # --- 문서 추출 + Gate 0 ---------------------------------------------------------------
    def run_extraction(
        self, project: Project, *, actor: str = "user", only_missing: bool = False
    ) -> StepOutcome:
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, STEP_EXTRACT, actor=actor)
        try:
            outcomes = self._s.extraction.extract_all(
                project, actor=actor, only_missing=only_missing
            )
            evaluation = self._s.extraction.evaluate_gate0(project, step_run_id=run.id)
            summary = (
                f"문서 {len(outcomes)}건 추출, 성공 {sum(1 for o in outcomes if o.run.ok)}건, "
                f"OCR 페이지 {sum(o.run.ocr_pages for o in outcomes)}쪽 → {GATE0_KEY} {evaluation.status}"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                actor=actor,
                output_refs={"gate0": evaluation.id, "runs": [o.run.id for o in outcomes]},
            )
            gate = self._s.gates.state(project, GATE0_KEY)
            if gate.status == GateStatus.FAIL:
                # 단계 자체는 끝났지만 게이트 실패는 이슈로 남긴다
                log.warning("Gate 0 FAIL: %s", evaluation.reasons)
            return StepOutcome(run=run, gate=gate, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    # --- 요구사항 추출 (Gate 0 필요) -----------------------------------------------------------
    def run_requirement_extraction(
        self, project: Project, *, actor: str = "user"
    ) -> tuple[StepOutcome, ExtractionSummary]:
        pipeline = self._s.pipeline
        self._s.gates.require(project, GATE0_KEY)  # 코드 검사: LLM 선언 무관
        run = pipeline.start_step(project, STEP_REQ_EXTRACT, actor=actor)
        try:
            result = self._s.requirements.extract(project)
            summary = (
                f"요구사항 {len(result.created)}건 생성, {len(result.updated)}건 갱신, 청크 {result.chunks}개, "
                f"미해결 {len(result.unresolved)}건, 출처 불명 제외 {len(result.dropped_missing_source)}건, 비용 ${result.cost_usd:.3f}"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.cost_usd,
                actor=actor,
                output_refs={"created": [r.id for r in result.created]},
            )
            return StepOutcome(run=run, summary=summary), result
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    # --- 독립 검증 + Gate 1 ---------------------------------------------------------------
    def run_verification(
        self, project: Project, *, actor: str = "user"
    ) -> tuple[StepOutcome, VerificationSummary]:
        pipeline = self._s.pipeline
        self._s.gates.require(project, GATE0_KEY)
        run = pipeline.start_step(project, STEP_REQ_VERIFY, actor=actor)
        try:
            result = self._s.requirements.verify(project)
            evaluation = self._s.requirements.evaluate_gate1(project, step_run_id=run.id)
            summary = (
                f"검증 판정 {result.verdicts}건, 지적 {len(result.findings)}건, 커버리지 추정 {result.coverage:.0%}, "
                f"비용 ${result.cost_usd:.3f} → {GATE1_KEY} {evaluation.status}"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.cost_usd,
                actor=actor,
                output_refs={"gate1": evaluation.id},
            )
            return StepOutcome(
                run=run, gate=self._s.gates.state(project, GATE1_KEY), summary=summary
            ), result
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def reevaluate_gate1(self, project: Project) -> GateState:
        """사람 수정 후 Gate 1을 코드로 다시 평가한다."""
        self._s.requirements.evaluate_gate1(project)
        return self._s.gates.state(project, GATE1_KEY)

    # --- 생성 단계 진입 검사 ------------------------------------------------------------------
    def require_generation_allowed(self, project: Project) -> GateState:
        """제안서 최종 생성 단계 진입 조건: Gate 1 PASS. 아니면 GateBlockedError."""
        try:
            return self._s.gates.require(project, GATE1_KEY)
        except GateBlockedError:
            raise

    # --- 역할 에이전트 단계 (Phase 3) -----------------------------------------------------------
    STEP_RFP_ANALYSIS = "rfp_analysis"
    STEP_TECH_RESEARCH = "tech_research"
    STEP_ARCHITECTURE = "architecture"
    STEP_WBS = "wbs_schedule"

    def run_rfp_analysis(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """RFP 분석 에이전트. Gate 0 통과가 필요하다. 첫 청크들을 프롬프트에 넣고 나머지는 MCP 검색 도구로 보게 한다."""
        self._s.gates.require(project, GATE0_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_RFP_ANALYSIS, actor=actor)
        try:
            blocks = self._s.extraction.current_blocks(project, required_only=True)
            chunks = build_chunks(blocks, self._s.ctx.settings.extraction_chunk_chars)
            head = "\n\n".join(c.text for c in chunks[:2])
            prof = self._s.extraction.rfp_profile(project)
            profile_text = (
                f"<rfp_profile>\n{prof.summary_text()}\n</rfp_profile>\n\n"
                if prof and prof.sections
                else ""
            )
            prompt = profile_text + (
                f"프로젝트: {project.name}\n청크 {min(2, len(chunks))}/{len(chunks)}개를 아래에 넣었다. 나머지는 "
                "mcp__pwa__search_source_text 로 검색하라.\n\n<document>\n"
                + head
                + "\n</document>\n\nRFP 분석 결과를 JSON으로 반환하라."
            )
            result = self._s.steps.run_role(
                project, "rfp_analyst", prompt, actor=actor, step_run_id=run.id, cancel=cancel
            )
            summary = f"RFP 분석 저장: {result.output_record.file_path} (비용 ${result.response.cost_usd:.3f})"
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.response.cost_usd,
                actor=actor,
                output_refs={"agent_output": result.output_record.id},
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def run_tech_research(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """기술 조사 에이전트. Gate 1 통과(요구사항 기준선)가 필요하다. 결과는 사람 검토(게이트 2)로 넘어간다."""
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_TECH_RESEARCH, actor=actor)
        try:
            result = self._s.research.run(project, actor=actor, step_run_id=run.id, cancel=cancel)
            summary = (
                f"조사 {len(result.items)}건, 주제 {len(result.topics)}개, 미확인 {result.unverified_count}건, "
                f"비교 {'있음' if result.study else '없음'}, 비용 ${result.cost_usd:.3f}"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.cost_usd,
                actor=actor,
                output_refs={"research_ids": [r.id for r in result.items]},
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    STEP_APPROACH = "impl_approach"
    STEP_STRATEGY = "strategy_brief"
    STEP_DESIGN = "impl_design"
    STEP_DETAIL_DESIGN = "detail_design"
    STEP_WBS_DECOMPOSE = "wbs_decompose"
    STEP_TEST_PLAN = "test_plan"
    STEP_CODE_GENERATION = "code_generation"
    STEP_CODE_TEST = "code_test"
    STEP_CODE_FIX = "code_fix"

    def run_strategy_brief(
        self,
        project: Project,
        *,
        actor: str = "user",
        cancel: CancellationToken | None = None,
        reviewer_comments: str = "",
    ) -> StepOutcome:
        """목차·전략 브리프(strategy_planner) 작성 → Gate P(사람 승인) 대기. Gate 1 통과 필요.

        RFP 분석 후 곧바로 전체 제안서를 쓰지 않도록, 브리프가 승인되어야 제안 문안 작성과 최종 확정이 열린다.
        반려 사유(``reviewer_comments``)를 주면 프롬프트에 넣어 다시 쓴다.
        """
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_STRATEGY, actor=actor)
        try:
            result = self._s.strategy.run(
                project,
                actor=actor,
                step_run_id=run.id,
                cancel=cancel,
                reviewer_comments=reviewer_comments,
            )
            b = result.brief
            summary = (
                f"브리프 작성: 목차 {len(b.toc)}장, 전략 {len(b.strategies)}개, 핵심 기술 {len(b.key_technologies)}건, "
                f"위험 {len(b.risks)}건, 확인 필요 {len(b.open_questions)}건 → {GATEP_KEY} {result.gate.status.value} "
                f"({result.markdown_path}, 비용 ${result.cost_usd:.3f})"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.cost_usd,
                actor=actor,
                output_refs={"markdown": result.markdown_path, "gateP": result.gate.id},
            )
            return StepOutcome(
                run=run, gate=self._s.gates.state(project, GATEP_KEY), summary=summary
            )
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def run_approach_writing(
        self,
        project: Project,
        *,
        actor: str = "user",
        cancel: CancellationToken | None = None,
        only_missing: bool = True,
        requirement_ids: list[str] | None = None,
    ) -> StepOutcome:
        """요구사항별 구현 방안·난이도·검사 기준 작성 에이전트(approach_writer). Gate 1 통과 필요.

        정의서의 '구현방안' 칸을 요구사항마다 채운다(제안서보다 짧은 요약). 에이전트가 빠뜨린 항목은
        조사·구성 요소 데이터로 규칙 초안을 만들어 ``[자동 초안]``으로 표시한다. 사람이 쓴 방안은 유지한다.
        """
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_APPROACH, actor=actor)
        try:
            result = self._s.approach.run(
                project,
                actor=actor,
                step_run_id=run.id,
                cancel=cancel,
                only_missing=only_missing,
                requirement_ids=requirement_ids,
            )
            summary = result.summary
            if result.research_needed:
                summary += " · 추가 조사: " + "; ".join(result.research_needed[:3])
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.cost_usd,
                actor=actor,
                output_refs={
                    "agent": result.agent_filled,
                    "rule": result.rule_filled,
                    "research_created": result.research_created,
                },
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def run_design_writing(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """요구사항 묶음별 구현 설계 에이전트(design_writer). Gate 1 통과 필요 (Phase 23).

        묶음마다 구현 구조·처리 절차·적용 기술(선정 이유·대안·근거)·데이터/인터페이스를 설계한다. 결과는
        제안서 묶음 소절의 도식·표가 되며, 빠진 요구사항·최소 요건 미달·출처 미확인은 요약에 남긴다(QA-CON-13 대상).
        """
        prompt = self._s.design.brief(project)
        outcome = self.run_role_step(
            project,
            self.STEP_DESIGN,
            "design_writer",
            prompt,
            required_gate=GATE1_KEY,
            actor=actor,
            cancel=cancel,
        )
        outcome.summary += " · " + self._s.design.summary(project)
        return outcome

    def run_detail_design(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """화면·DB·API·모듈 상세 설계 에이전트(detail_designer) → 엔티티 저장·추적 연결 (단계 6, 지시문 §12)."""
        prompt = self._s.detail_design.brief(project)
        outcome = self.run_role_step(
            project,
            self.STEP_DETAIL_DESIGN,
            "detail_designer",
            prompt,
            required_gate=GATE1_KEY,
            actor=actor,
            cancel=cancel,
        )
        data = self._s.detail_design.latest(project)
        if data:
            counts = self._s.detail_design.persist(project, data, actor=actor)
            outcome.summary += (
                f" · 저장: 화면 {counts['screens']}·테이블 {counts['tables']}·API {counts['apis']}"
                f"·모듈 {counts['modules']}·규칙 {counts['rules']}·추적 {counts['traces']} · "
                + self._s.detail_design.summary(project)
            )
        return outcome

    def _plain_step(self, project: Project, step_key: str, actor: str, body: Any) -> StepOutcome:
        """에이전트 1회가 아닌 코드 단계(단계 7): StepRun 기록 + 본문 실행."""
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, step_key, actor=actor)
        try:
            summary, refs = body()
            pipeline.complete_step(project, run, summary=summary, actor=actor, output_refs=refs)
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def run_wbs_decompose(self, project: Project, *, actor: str = "user") -> StepOutcome:
        """WBS 를 설계 모듈까지 분해 (단계 7 ①)."""
        from proposal_agent.planning.decompose import decompose_wbs_to_modules

        def body() -> tuple[str, dict[str, Any]]:
            if self._s.planning.plan_missing(project):  # planner 초안이 있으면 계획을 먼저 세운다
                draft_json = self._s.steps.prior_output(project, "planner")
                if draft_json:
                    from proposal_agent.agents.schemas import WBSDraft

                    self._s.planning.build_plan(
                        project,
                        WBSDraft.model_validate(draft_json),
                        self._s.steps.prior_output(project, "rfp_analyst"),
                        actor=actor,
                    )
            added, warnings = decompose_wbs_to_modules(self._s.ctx.repos, project, actor=actor)
            if added:  # 공수가 바뀌었으므로 투입 배정을 다시 만든다 (QA-CON-05 정합)
                self._s.planning.rebuild_allocations(project)
            return (
                f"WBS 분해: 모듈 Task {len(added)}건 추가"
                + (f", 경고 {len(warnings)}건: {warnings[0]}" if warnings else ""),
                {"added": [a.code for a in added], "warnings": warnings},
            )

        return self._plain_step(project, self.STEP_WBS_DECOMPOSE, actor, body)

    def run_test_plan(self, project: Project, *, actor: str = "user") -> StepOutcome:
        """설계·인수 기준에서 테스트 케이스 계획 (단계 7 ③)."""

        def body() -> tuple[str, dict[str, Any]]:
            counts = self._s.testing.plan_from_design(project, actor=actor)
            return (
                f"테스트 계획: 통합 {counts['integration']}·화면 {counts['ui']}·인수 {counts['acceptance']}건",
                dict(counts),
            )

        return self._plain_step(project, self.STEP_TEST_PLAN, actor, body)

    def run_code_generation(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """설계 모듈을 배치로 나눠 developer 에이전트로 생성 → 정적 검사 (단계 7 ⑦, D-22)."""

        def body() -> tuple[str, dict[str, Any]]:
            out = self._s.development.generate(project, actor=actor, cancel=cancel)
            return out.summary(), {
                "files": out.files_written,
                "errors": out.errors,
                "warnings": out.warnings[:20],
            }

        return self._plain_step(project, self.STEP_CODE_GENERATION, actor, body)

    def run_code_test(self, project: Project, *, actor: str = "user") -> StepOutcome:
        """Docker 격리 JUnit 실행 → TC·DEF 반입 (단계 7 ③)."""

        def body() -> tuple[str, dict[str, Any]]:
            result = self._s.development.run_tests(project, actor=actor)
            return f"테스트 {result.label}: {result.summary()}", {
                "label": result.label,
                "outcome": result.outcome.value,
            }

        return self._plain_step(project, self.STEP_CODE_TEST, actor, body)

    def run_code_fix(self, project: Project, *, actor: str = "user") -> StepOutcome:
        """QA 분석·수정·재테스트 루프 (단계 7)."""

        def body() -> tuple[str, dict[str, Any]]:
            notes = self._s.development.qa_fix_loop(project, actor=actor)
            return "수정 루프: " + (" | ".join(notes) if notes else "실행할 것 없음"), {
                "rounds": notes
            }

        return self._plain_step(project, self.STEP_CODE_FIX, actor, body)

    def run_role_step(
        self,
        project: Project,
        step_key: str,
        role_key: str,
        prompt: str,
        *,
        required_gate: str | None = GATE1_KEY,
        actor: str = "user",
        cancel: CancellationToken | None = None,
    ) -> StepOutcome:
        """일반 역할 단계 실행 (architect/planner/proposal_writer/document_generator/qa_reviewer)."""
        if required_gate:
            self._s.gates.require(project, required_gate)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, step_key, actor=actor)
        try:
            result = self._s.steps.run_role(
                project, role_key, prompt, actor=actor, step_run_id=run.id, cancel=cancel
            )
            summary = f"{role_key} 결과 저장: {result.output_record.file_path} (비용 ${result.response.cost_usd:.3f})"
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                cost_usd=result.response.cost_usd,
                actor=actor,
                output_refs={"agent_output": result.output_record.id},
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    # --- 산출물 생성 · QA · 최종 확정 (Phase 4) ------------------------------------------------
    STEP_GENERATE = "generate_docs"
    STEP_PPT = "proposal_ppt"
    STEP_QA = "qa"
    STEP_FINALIZE = "finalize"

    def run_proposal_writing(
        self, project: Project, *, actor: str = "user", cancel: CancellationToken | None = None
    ) -> StepOutcome:
        """제안서 작성 에이전트(proposal_writer). Gate 1 통과 필요. 템플릿 관행·RFP 지정 목차·기준 데이터를 넣는다.

        구현 가능한 내용만 쓰도록 **기술 조사(웹 검색)가 선행**되어야 한다: 조사 기록이 하나도 없으면 거부하고,
        근거 조사가 없는 필수 기능 요구사항이 남아 있으면 경고를 감사 기록·요약에 남긴다(에이전트는 '조사 후 확정'으로 쓴다).
        """
        self._s.gates.require(project, GATE1_KEY)
        self._s.gates.require(project, GATEP_KEY)  # 목차·전략 승인 전에는 전체 문안을 쓰지 않는다
        if not self._s.research.list_research(project):
            raise ValidationError(
                "기술 조사 기록이 없어 제안 문안을 작성할 수 없습니다.",
                cause="구현 방안은 웹 검색 기반 기술 조사 결과에 근거해야 함",
                resolution="에이전트·조사 화면에서 '기술 조사 실행(에이전트, 웹 검색)'을 먼저 수행하십시오.",
            )
        ctx = self._s.generation.build_context(project, actor=actor)
        gaps = self._s.generation.research_gaps(ctx)
        if gaps:
            self._s.audit.record(
                project.id,
                "proposal.writing.research_gaps",
                actor=actor,
                payload={"requirement_ids": gaps[:50], "count": len(gaps)},
            )
        prompt = self._s.generation.proposal_brief(project)
        outcome = self.run_role_step(
            project,
            self.STEP_PPT,
            "proposal_writer",
            prompt,
            required_gate=GATE1_KEY,
            actor=actor,
            cancel=cancel,
        )
        if gaps:
            outcome.summary += (
                f" · 근거 조사 없는 필수 기능 요구사항 {len(gaps)}건 ({', '.join(gaps[:5])})"
            )
        return outcome

    def run_generation(self, project: Project, *, actor: str = "user") -> StepOutcome:
        """Gate 1 통과 프로젝트만. 계획(없으면 기본값)·구성도·Excel 4종·PPT 2종을 생성한다."""
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_GENERATE, actor=actor)
        try:
            # 정의서 '구현방안' 칸이 비지 않도록: 빈 항목은 조사·구성 요소 데이터로 규칙 초안([자동 초안]) 채움
            drafted = self._s.approach.ensure_filled(project, actor=actor)
            result = self._s.generation.generate_all(project, actor=actor)
            if not self._s.gates.state(project, GATEP_KEY).passed:
                result.review_items.append(
                    "목차·전략(Gate P)이 승인되지 않은 상태의 시안입니다. 브리프를 승인한 뒤 재생성하면 승인된 목차·전략이 반영됩니다."
                )
            summary = (
                f"산출물 {len(result.deliverables)}건 생성, 목차 출처 {result.outline[0].source if result.outline else '-'}, "
                f"검토 필요 {len(result.review_items)}건"
                + (f", 오류 {len(result.errors)}건" if result.errors else "")
                + (f", 구현 방안 규칙 초안 {len(drafted)}건(사람 확인 필요)" if drafted else "")
            )
            if result.errors:
                pipeline.fail_step(
                    project,
                    run,
                    PWAError(
                        "일부 산출물 생성 실패",
                        cause="; ".join(result.errors),
                        resolution="오류를 해결하고 다시 생성하십시오.",
                    ),
                    actor=actor,
                )
                raise PWAError(
                    "일부 산출물 생성 실패",
                    cause="; ".join(result.errors),
                    resolution="오류를 해결하고 다시 생성하십시오.",
                )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                actor=actor,
                output_refs={"deliverables": [d.id for d in result.deliverables]},
            )
            ppt_run = pipeline.start_step(project, self.STEP_PPT, actor=actor)
            pipeline.complete_step(
                project,
                ppt_run,
                summary="제출용·발표용 PPT 생성 (generate_docs와 동시)",
                actor=actor,
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            latest = self._s.ctx.repos.step_runs.latest(project.id, self.STEP_GENERATE)
            if latest and latest.id == run.id and latest.status.value == "running":
                pipeline.fail_step(project, run, exc, actor=actor)
            raise

    def run_qa(
        self,
        project: Project,
        *,
        actor: str = "user",
        render_check: bool | None = None,
        categories: set[Any] | None = None,
    ) -> StepOutcome:
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_QA, actor=actor)
        try:
            result = self._s.qa.run(
                project,
                actor=actor,
                step_run_id=run.id,
                render_check=render_check,
                categories=categories,
            )
            c = result.qa_run.counts if result.qa_run else {}
            summary = (
                f"통합 QA 통과 {c.get('pass', 0)}·실패 {c.get('fail', 0)}·검토 필요 {c.get('needs_human_review', 0)}·미실행 {c.get('not_run', 0)}, "
                f"자동 수정 {result.qa_run.fix_rounds if result.qa_run else 0}회 → {GATE5_KEY} {result.gate.status} (보고서 {result.report_path})"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                actor=actor,
                output_refs={
                    "report": result.report_path,
                    "gate5": result.gate.id,
                    "gates": {k: v.id for k, v in result.gates.items()},
                },
            )
            return StepOutcome(
                run=run, gate=self._s.gates.state(project, GATE5_KEY), summary=summary
            )
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    STEP_BID = "bid_assessment"

    def run_bid_assessment(
        self,
        project: Project,
        *,
        actor: str = "user",
        user_ratings: dict[str, tuple[str | None, str]] | None = None,
    ) -> StepOutcome:
        """사업 참여 타당성 평가 (단계 2, 지시문 §6). 코드 평가 + 사용자 판정 → 평가서. 결정은 화면에서 따로 기록."""
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_BID, actor=actor)
        try:
            a = self._s.feasibility.assess(project, actor=actor, user_ratings=user_ratings)
            counts = a.counts()
            summary = (
                f"사업성 평가 v{a.version}: 권고 '{a.recommendation.label}' — 양호 {counts['good']}·주의 {counts['caution']}·"
                f"위험 {counts['risk']}·미확인 {counts['unknown']}, 비용 산정 {a.cost_estimate.get('status', 'unavailable')} ({a.report_path})"
            )
            pipeline.complete_step(
                project,
                run,
                summary=summary,
                actor=actor,
                output_refs={
                    "assessment": a.id,
                    "report": a.report_path,
                    "recommendation": a.recommendation.value,
                },
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=actor)
            raise

    # --- 단계 키 디스패처 (단계 1, 지시문 §16: 특정 단계만·실패한 작업만·선택 범위 실행) --------------
    DISPATCHABLE: tuple[str, ...] = (
        "extract",
        "rfp_analysis",
        "req_extract",
        "req_verify",
        "bid_assessment",
        "tech_research",
        "impl_approach",
        "strategy_brief",
        "architecture",
        "impl_design",
        "detail_design",
        "wbs_schedule",
        "wbs_decompose",
        "test_plan",
        "code_generation",
        "code_test",
        "code_fix",
        "generate_docs",
        "proposal_ppt",
        "qa",
    )

    def run_step(
        self,
        project: Project,
        step_key: str,
        *,
        actor: str = "user",
        cancel: CancellationToken | None = None,
    ) -> StepOutcome:
        """단계 키로 해당 실행 함수를 호출한다. 업로드·인력 계획·최종 확정처럼 사람 입력이 필요한 단계는 거부한다."""
        if step_key == "extract":
            return self.run_extraction(project, actor=actor)
        if step_key == "rfp_analysis":
            return self.run_rfp_analysis(project, actor=actor, cancel=cancel)
        if step_key == "req_extract":
            return self.run_requirement_extraction(project, actor=actor)[0]
        if step_key == "req_verify":
            return self.run_verification(project, actor=actor)[0]
        if step_key == "bid_assessment":
            return self.run_bid_assessment(project, actor=actor)
        if step_key == "tech_research":
            return self.run_tech_research(project, actor=actor, cancel=cancel)
        if step_key == "impl_approach":
            return self.run_approach_writing(project, actor=actor, cancel=cancel)
        if step_key == "strategy_brief":
            return self.run_strategy_brief(project, actor=actor, cancel=cancel)
        if step_key == "architecture":
            return self.run_role_step(
                project,
                self.STEP_ARCHITECTURE,
                "architect",
                "아키텍처 설계",
                actor=actor,
                cancel=cancel,
            )
        if step_key == "impl_design":
            return self.run_design_writing(project, actor=actor, cancel=cancel)
        if step_key == "detail_design":
            return self.run_detail_design(project, actor=actor, cancel=cancel)
        if step_key == "wbs_decompose":
            return self.run_wbs_decompose(project, actor=actor)
        if step_key == "test_plan":
            return self.run_test_plan(project, actor=actor)
        if step_key == "code_generation":
            return self.run_code_generation(project, actor=actor, cancel=cancel)
        if step_key == "code_test":
            return self.run_code_test(project, actor=actor)
        if step_key == "code_fix":
            return self.run_code_fix(project, actor=actor)
        if step_key == "wbs_schedule":
            return self.run_role_step(
                project, self.STEP_WBS, "planner", "WBS 초안", actor=actor, cancel=cancel
            )
        if step_key == "generate_docs":
            return self.run_generation(project, actor=actor)
        if step_key == "proposal_ppt":
            return self.run_proposal_writing(project, actor=actor, cancel=cancel)
        if step_key == "qa":
            return self.run_qa(project, actor=actor)
        raise ValidationError(
            f"단계 '{step_key}' 는 화면에서 사람 입력으로 진행합니다.",
            cause="upload/staffing/finalize 또는 알 수 없는 단계",
            resolution="해당 화면에서 문서 업로드·기간 저장·승인을 수행하십시오.",
        )

    def run_steps(
        self,
        project: Project,
        step_keys: list[str],
        *,
        actor: str = "user",
        cancel: CancellationToken | None = None,
        stop_on_failure: bool = True,
    ) -> list[tuple[str, StepOutcome | None, str]]:
        """선택한 단계를 정의 순서대로 실행한다. 돌려주는 값은 (단계 키, 결과, 메시지). 실패·게이트 대기에서 멈춘다."""
        order = {d.key: d.order for d in self._s.pipeline.definitions(project.mode)}
        keys = sorted(
            (k for k in step_keys if k in self.DISPATCHABLE), key=lambda k: order.get(k, 999)
        )
        out: list[tuple[str, StepOutcome | None, str]] = []
        for key in keys:
            if cancel is not None and cancel.is_cancelled:
                out.append((key, None, "중단 요청으로 실행하지 않음"))
                continue
            try:
                outcome = self.run_step(project, key, actor=actor, cancel=cancel)
            except PWAError as exc:
                out.append((key, None, f"실패: {exc}"))
                if stop_on_failure:
                    break
                continue
            out.append((key, outcome, outcome.summary))
            if outcome.run.status == StepStatus.NEEDS_REVIEW:
                out.append((key, None, "사람 승인(게이트) 대기 — 이후 단계는 승인 뒤 실행"))
                break
        return out

    def rerun_failed(
        self, project: Project, *, actor: str = "user"
    ) -> list[tuple[str, StepOutcome | None, str]]:
        """실패한 단계만 다시 실행한다 (지시문 §16: 실패한 작업만 재실행)."""
        keys = [v.definition.key for v in self._s.pipeline.failed_steps(project)]
        return self.run_steps(project, keys, actor=actor)

    def run_finalize(self, project: Project, *, approver: str, comments: str) -> StepOutcome:
        """Gate 5(최종 독립 QA)가 PASS(사람 승인 포함)여야 최종본 폴더로 복사한다. 필수 검증 실패가 있으면 통과할 수 없다."""
        if project.mode.value == "proposal":
            self._s.gates.require(project, GATEP_KEY)  # 승인된 목차·전략 없이는 최종 확정 불가
        self._s.gates.require(project, GATE5_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_FINALIZE, actor=approver)
        try:
            copied = self._s.generation.finalize(project, approver=approver, comments=comments)
            summary = f"최종본 {len(copied)}건 확정 → 13_Final_Deliverables"
            pipeline.complete_step(
                project, run, summary=summary, actor=approver, output_refs={"files": copied}
            )
            return StepOutcome(run=run, summary=summary)
        except PWAError as exc:
            pipeline.fail_step(project, run, exc, actor=approver)
            raise
