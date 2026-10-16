"""애플리케이션 서비스 계층 (UI ↔ 도메인/저장소 사이)."""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.agents.runner import AgentRunner, build_runner
from proposal_agent.changes.baseline_service import BaselineService
from proposal_agent.changes.service import ChangeService
from proposal_agent.decisions.service import DecisionService
from proposal_agent.design.service import DetailDesignService
from proposal_agent.feasibility.service import FeasibilityService
from proposal_agent.generators.service import GenerationService
from proposal_agent.ingest.ocr import OcrEngine
from proposal_agent.ingest.service import ExtractionService
from proposal_agent.orchestrator.gates import GateService
from proposal_agent.planning.service import PlanningService
from proposal_agent.requirements.approach import ApproachService
from proposal_agent.requirements.design import DesignService
from proposal_agent.requirements.service import RequirementService
from proposal_agent.research.service import ResearchService
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.audit import AuditService
from proposal_agent.services.context import AppContext
from proposal_agent.services.document_service import DocumentService
from proposal_agent.services.jobs import JobManager
from proposal_agent.services.pipeline_service import PipelineService
from proposal_agent.services.project_service import ProjectService
from proposal_agent.services.strategy_service import StrategyService
from proposal_agent.services.template_service import TemplateService
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
    templates: TemplateService
    approach: ApproachService
    strategy: StrategyService
    design: DesignService
    jobs: JobManager
    feasibility: FeasibilityService
    decisions: DecisionService
    detail_design: DetailDesignService

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
        templates = TemplateService(ctx.repos, ctx.paths)
        generation = GenerationService(
            ctx.repos,
            ctx.paths,
            ctx.settings,
            audit,
            ctx.files,
            planning,
            steps,
            extraction,
            templates=templates,
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
            pipeline=PipelineService(ctx.repos, audit, ctx.settings),
            extraction=extraction,
            requirements=RequirementService(
                ctx.repos, ctx.settings, audit, extraction, runner, paths=ctx.paths
            ),
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
                templates=templates,
            ),
            baseline=baseline,
            changes=changes,
            templates=templates,
            approach=ApproachService(ctx.repos, audit, steps),
            strategy=StrategyService(
                ctx.repos, ctx.paths, ctx.files, audit, steps, generation, extraction
            ),
            design=DesignService(ctx.repos, steps),
            jobs=JobManager(ctx.repos),
            feasibility=FeasibilityService(ctx.repos, ctx.paths, ctx.files, audit, steps, planning),
            decisions=DecisionService(
                ctx.repos, audit, steps, extraction=extraction, paths=ctx.paths
            ),
            detail_design=DetailDesignService(ctx.repos, audit, steps, ctx.paths, ctx.files),
        )


__all__ = [
    "AgentStepService",
    "TemplateService",
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
