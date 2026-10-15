"""애플리케이션 서비스 계층 (UI ↔ 도메인/저장소 사이)."""

from __future__ import annotations

from dataclasses import dataclass

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

    @classmethod
    def from_context(cls, ctx: AppContext) -> Services:
        audit = AuditService(ctx.repos.audit)
        return cls(
            ctx=ctx,
            audit=audit,
            projects=ProjectService(ctx.repos, ctx.paths, audit),
            documents=DocumentService(ctx.repos, ctx.files, audit),
            pipeline=PipelineService(ctx.repos, audit),
        )


__all__ = [
    "AppContext",
    "AuditService",
    "DocumentService",
    "PipelineService",
    "ProjectService",
    "Services",
]
