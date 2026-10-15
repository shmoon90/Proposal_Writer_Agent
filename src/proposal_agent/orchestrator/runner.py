"""단계 실행기 (Phase 2 범위: 문서 추출 → 요구사항 추출 → 독립 검증).

각 함수는 StepRun을 열고(PipelineService), 서비스를 호출하고, Gate를 **코드로** 평가한 뒤 완료/실패를 기록한다.
Gate 0가 PASS가 아니면 요구사항 추출을 시작하지 않고, Gate 1이 PASS가 아니면 제안서 생성 단계로 갈 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from proposal_agent.config.errors import PWAError
from proposal_agent.config.logging import get_logger
from proposal_agent.ingest.service import GATE0_KEY
from proposal_agent.models import GateStatus, Project, StepRun
from proposal_agent.orchestrator.gates import GateBlockedError, GateState
from proposal_agent.requirements.service import GATE1_KEY, ExtractionSummary, VerificationSummary

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
