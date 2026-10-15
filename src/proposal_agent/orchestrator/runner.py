"""단계 실행기 (Phase 2 범위: 문서 추출 → 요구사항 추출 → 독립 검증).

각 함수는 StepRun을 열고(PipelineService), 서비스를 호출하고, Gate를 **코드로** 평가한 뒤 완료/실패를 기록한다.
Gate 0가 PASS가 아니면 요구사항 추출을 시작하지 않고, Gate 1이 PASS가 아니면 제안서 생성 단계로 갈 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from proposal_agent.agents.control import CancellationToken
from proposal_agent.config.errors import PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.chunker import build_chunks
from proposal_agent.ingest.service import GATE0_KEY
from proposal_agent.models import GateStatus, Project, StepRun
from proposal_agent.orchestrator.gates import GateBlockedError, GateState
from proposal_agent.requirements.service import GATE1_KEY, ExtractionSummary, VerificationSummary
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
            result = self._s.generation.generate_all(project, actor=actor)
            summary = (
                f"산출물 {len(result.deliverables)}건 생성, 목차 출처 {result.outline[0].source if result.outline else '-'}, "
                f"검토 필요 {len(result.review_items)}건"
                + (f", 오류 {len(result.errors)}건" if result.errors else "")
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

    def run_qa(self, project: Project, *, actor: str = "user") -> StepOutcome:
        self._s.gates.require(project, GATE1_KEY)
        pipeline = self._s.pipeline
        run = pipeline.start_step(project, self.STEP_QA, actor=actor)
        try:
            result = self._s.qa.run(project, actor=actor, step_run_id=run.id)
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

    def run_finalize(self, project: Project, *, approver: str, comments: str) -> StepOutcome:
        """Gate 5(최종 독립 QA)가 PASS(사람 승인 포함)여야 최종본 폴더로 복사한다. 필수 검증 실패가 있으면 통과할 수 없다."""
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
