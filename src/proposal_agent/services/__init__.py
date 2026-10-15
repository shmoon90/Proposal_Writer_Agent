"""애플리케이션 서비스 계층 (UI ↔ 도메인/저장소 사이)."""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.agents.runner import AgentRunner, build_runner
from proposal_agent.ingest.ocr import OcrEngine
from proposal_agent.ingest.service import ExtractionService
from proposal_agent.orchestrator.gates import GateService
from proposal_agent.requirements.service import RequirementService
from proposal_agent.services.audit import AuditService
from proposal_agent.services.context import AppContext
from proposal_agent.services.document_service import DocumentService
from proposal_agent.services.pipeline_service import PipelineService
from proposal_agent.services.project_service import ProjectService


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
        return cls(
            ctx=ctx,
            audit=audit,
            projects=ProjectService(ctx.repos, ctx.paths, audit),
            documents=DocumentService(ctx.repos, ctx.files, audit),
            pipeline=PipelineService(ctx.repos, audit),
            extraction=extraction,
            requirements=RequirementService(ctx.repos, ctx.settings, audit, extraction, runner),
            gates=GateService(ctx.repos, audit),
            runner=runner,
        )


__all__ = [
    "AppContext",
    "AuditService",
    "DocumentService",
    "ExtractionService",
    "GateService",
    "PipelineService",
    "ProjectService",
    "RequirementService",
    "Services",
]
