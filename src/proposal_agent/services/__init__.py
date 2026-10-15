"""애플리케이션 서비스 계층 (UI ↔ 도메인/저장소 사이)."""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.agents.runner import AgentRunner, build_runner
from proposal_agent.changes.baseline_service import BaselineService
from proposal_agent.changes.service import ChangeService
from proposal_agent.generators.service import GenerationService
from proposal_agent.ingest.ocr import OcrEngine
from proposal_agent.ingest.service import ExtractionService
from proposal_agent.orchestrator.gates import GateService
from proposal_agent.planning.service import PlanningService
from proposal_agent.requirements.service import RequirementService
from proposal_agent.research.service import ResearchService
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.audit import AuditService
from proposal_agent.services.context import AppContext
from proposal_agent.services.document_service import DocumentService
from proposal_agent.services.pipeline_service import PipelineService
from proposal_agent.services.project_service import ProjectService
from proposal_agent.validation.qa_service import QaService


@dataclass
class Services:
    ctx: AppContext
    audit: AuditService
    projects: ProjectService
    documents: DocumentService
    pipeline: PipelineService
    extraction: ExtractionService
    requirements: RequirementService
    gates: GateService
    runner: AgentRunner
    steps: AgentStepService
    research: ResearchService
    planning: PlanningService
    generation: GenerationService
    qa: QaService
    baseline: BaselineService
    changes: ChangeService

    @classmethod
    def from_context(
        cls,
        ctx: AppContext,
        *,
        runner: AgentRunner | None = None,
        ocr: OcrEngine | None = None,
    ) -> Services:
        audit = AuditService(ctx.repos.audit)
        runner = runner or build_runner(ctx.settings)
        extraction = ExtractionService(ctx.repos, ctx.paths, ctx.settings, audit, ocr=ocr)
        steps = AgentStepService(ctx.repos, ctx.paths, ctx.settings, audit, runner, ctx.files)
        planning = PlanningService(ctx.repos, ctx.settings, audit)
        generation = GenerationService(
            ctx.repos, ctx.paths, ctx.settings, audit, ctx.files, planning, steps, extraction
        )
        documents = DocumentService(ctx.repos, ctx.files, audit)
        baseline = BaselineService(ctx.repos, ctx.paths, ctx.settings, audit, ctx.files)
        changes = ChangeService(
            ctx.repos,
            ctx.paths,
            ctx.settings,
            audit,
            ctx.files,
            steps,
            baseline,
            documents,
            extraction,
        )
        return cls(
            ctx=ctx,
            audit=audit,
            projects=ProjectService(ctx.repos, ctx.paths, audit),
            documents=documents,
            pipeline=PipelineService(ctx.repos, audit),
            extraction=extraction,
            requirements=RequirementService(ctx.repos, ctx.settings, audit, extraction, runner),
            gates=GateService(ctx.repos, audit),
            runner=runner,
            steps=steps,
            research=ResearchService(ctx.repos, steps),
            planning=planning,
            generation=generation,
            qa=QaService(
                ctx.repos,
                ctx.paths,
                audit,
                ctx.files,
                generation,
                settings=ctx.settings,
                extraction=extraction,
                changes=changes,
                steps=steps,
            ),
            baseline=baseline,
            changes=changes,
        )


__all__ = [
    "AgentStepService",
    "AppContext",
    "AuditService",
    "BaselineService",
    "ChangeService",
    "DocumentService",
    "ExtractionService",
    "GateService",
    "GenerationService",
    "PlanningService",
    "QaService",
    "PipelineService",
    "ProjectService",
    "RequirementService",
    "ResearchService",
    "Services",
]
