"""산출물 생성 서비스: 공통 데이터 → 다이어그램·Excel·PPT, Deliverable 기록, 최종본 분리.

실행 조건은 오케스트레이터가 검사한다(Gate 1). 이 서비스는 데이터 조립·파일 생성·기록만 담당한다.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from proposal_agent.config.errors import PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.diagrams import (
    build_architecture_diagram,
    build_gantt_chart,
    build_staffing_chart,
    default_components,
)
from proposal_agent.generators.excel import (
    build_requirement_spec,
    build_staffing_plan,
    build_trace_matrix,
    build_wbs_gantt,
)
from proposal_agent.generators.pptx import (
    build_presentation_deck,
    build_submission_deck,
    decide_outline,
    rfp_toc_from_blocks,
)
from proposal_agent.generators.pptx.outline import OutlineSection
from proposal_agent.models import (
    ActorKind,
    ArchitectureComponent,
    Deliverable,
    DeliverableKind,
    IntegrityStatus,
    Project,
    QaStatus,
    RequirementStatus,
)
from proposal_agent.models.design import ComponentConnection
from proposal_agent.planning.service import PlanningService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.ingest.service import ExtractionService
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService

log = get_logger("generators.service")

FINAL_SUBDIR = "13_Final_Deliverables"
KIND_TARGETS: dict[DeliverableKind, tuple[str, str, str]] = {
    DeliverableKind.REQUIREMENT_SPEC_XLSX: ("09_Excel_Deliverables", "요구사항정의서", ".xlsx"),
    DeliverableKind.TRACE_MATRIX_XLSX: ("09_Excel_Deliverables", "요구사항추적표", ".xlsx"),
    DeliverableKind.WBS_GANTT_XLSX: ("06_WBS_Effort_Schedule", "WBS_간트", ".xlsx"),
    DeliverableKind.STAFFING_PLAN_XLSX: ("06_WBS_Effort_Schedule", "인력투입계획", ".xlsx"),
    DeliverableKind.SUBMISSION_PPTX: ("07_Submission_Proposal_PPT", "제안서_제출용", ".pptx"),
    DeliverableKind.PRESENTATION_PPTX: ("08_Presentation_PPT", "제안서_발표용", ".pptx"),
    DeliverableKind.SYSTEM_DIAGRAM_PNG: ("10_Diagrams_Charts_Images", "시스템구성도", ".png"),
    DeliverableKind.SW_DIAGRAM_PNG: ("10_Diagrams_Charts_Images", "SW구성도", ".png"),
    DeliverableKind.SERVICE_DIAGRAM_PNG: ("10_Diagrams_Charts_Images", "서비스구성도", ".png"),
}


@dataclass
class GenerationResult:
    deliverables: list[Deliverable] = field(default_factory=list)
    outline: list[OutlineSection] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)
    context: GenerationContext | None = None
    errors: list[str] = field(default_factory=list)


class GenerationService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        settings: Settings,
        audit: AuditService,
        files: FileStore,
        planning: PlanningService,
        steps: AgentStepService,
        extraction: ExtractionService,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._files = files
        self._planning = planning
        self._steps = steps
        self._extraction = extraction

    # --- 데이터 조립 --------------------------------------------------------------------------
    def build_context(self, project: Project, *, actor: str = "user") -> GenerationContext:
        requirements = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
        ]
        if not requirements:
            raise ValidationError(
                "요구사항이 없어 산출물을 만들 수 없습니다.",
                resolution="요구사항 추출·검증을 먼저 완료하십시오.",
            )
        analysis = self._steps.prior_output(project, "rfp_analyst")
        wbs, deps, roles, allocs = self._planning.current_plan(project)
        review: list[str] = []
        if not wbs:
            draft_json = self._steps.prior_output(project, "planner")
            draft = None
            if draft_json:
                from proposal_agent.agents.schemas import WBSDraft

                draft = WBSDraft.model_validate(draft_json)
            plan = self._planning.build_plan(project, draft, analysis, actor=actor)
            wbs, deps, roles, allocs = self._planning.current_plan(project)
            review.extend(plan.review_notes)
        period = self._planning.resolve_period(project, analysis)
        ctx = GenerationContext(
            project=project,
            requirements=requirements,
            wbs=wbs,
            dependencies=deps,
            roles=roles,
            allocations=allocs,
            research=self._repos.research.find(project.id, order_by="created_at"),
            analysis=analysis,
            proposal_content=self._steps.prior_output(project, "proposal_writer"),
            period_start=period.start,
            period_end=period.end,
            review_notes=review,
        )
        ctx.components = self._ensure_components(project, ctx, actor)
        ctx.review_notes.extend(self.review_items(ctx))
        return ctx

    def _ensure_components(
        self, project: Project, ctx: GenerationContext, actor: str
    ) -> list[ArchitectureComponent]:
        existing = self._repos.components.find(project.id, order_by="created_at")
        if existing:
            return existing
        draft = self._steps.prior_output(project, "architect")
        comps: list[ArchitectureComponent] = []
        if draft and draft.get("components"):
            by_code: dict[str, ArchitectureComponent] = {}
            for c in draft["components"]:
                comp = ArchitectureComponent(
                    id=str(c.get("code")),
                    project_id=project.id,
                    layer=str(c.get("layer", "app")),
                    name=str(c.get("name", "")),
                    technology=str(c.get("technology", "")),
                    description=str(c.get("description", "")),
                    diagram_kinds=list(c.get("diagram_kinds", [])),
                    extra={"requirement_ids": list(c.get("related_requirement_ids", []))},
                    created_by=actor,
                )
                by_code[comp.id] = comp
            for conn in draft.get("connections", []):
                src = by_code.get(str(conn.get("from_code")))
                if src and str(conn.get("to_code")) in by_code:
                    src.connections.append(
                        ComponentConnection(
                            to_component_id=str(conn["to_code"]),
                            protocol=str(conn.get("protocol", "")),
                            note=str(conn.get("note", "")),
                        )
                    )
            comps = list(by_code.values())
        else:
            comps = default_components(ctx)
            ctx.review_notes.append(
                "아키텍처 구성 요소가 코드 기본값으로 생성되었습니다 (기술 미정). 아키텍처 에이전트 실행 또는 수동 수정이 필요합니다."
            )
        for comp in comps:
            self._repos.components.insert(comp)
        return comps

    def review_items(self, ctx: GenerationContext) -> list[str]:
        items: list[str] = []
        for t in ctx.research:
            if t.feasibility.value in ("infeasible", "unknown") and t.related_requirement_ids:
                items.append(
                    f"기술 미확인: {t.topic} (요구사항 {', '.join(t.related_requirement_ids)}) — 구현 가능성 {t.feasibility.value}"
                )
            for u in t.unverified_items[:2]:
                items.append(f"미확인 사항 [{t.topic[:20]}]: {u}")
        pending = [
            r.id for r in ctx.requirements if r.acceptance_status.value in ("proposed", "deferred")
        ]
        if pending:
            items.append(
                f"수용 여부 '검토 필요' 요구사항 {len(pending)}건: {', '.join(pending[:8])}"
            )
        if any(w.auto_generated for w in ctx.wbs):
            items.append("WBS 공수가 기본값입니다 — 산정 근거 검토 필요")
        if any((c.extra or {}).get("auto_generated") for c in ctx.components):
            items.append("구성도의 기술 스택이 '미정'입니다 — 아키텍처 확정 필요")
        for claim in (ctx.proposal_content or {}).get("unverified_claims", []) or []:
            items.append(f"제안 문안 확인 필요: {claim}")
        return items

    # --- 생성 -------------------------------------------------------------------------------
    def generate_all(self, project: Project, *, actor: str = "user") -> GenerationResult:
        ctx = self.build_context(project, actor=actor)
        result = GenerationResult(context=ctx, review_items=list(ctx.review_notes))
        font = self._settings.font_path
        # 다이어그램
        for kind, dk in (
            ("system", DeliverableKind.SYSTEM_DIAGRAM_PNG),
            ("sw", DeliverableKind.SW_DIAGRAM_PNG),
            ("service", DeliverableKind.SERVICE_DIAGRAM_PNG),
        ):
            try:
                png = build_architecture_diagram(ctx, kind, font_path=font)
                d = self._store(project, dk, png, ctx)
                ctx.diagram_paths[kind] = str(self._paths.resolve_output(d.file_path))
                result.deliverables.append(d)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{kind} 구성도 생성 실패: {exc}")
        try:
            gantt = build_gantt_chart(ctx, font_path=font)
            stored = self._files.save_bytes(
                project.output_dir,
                "10_Diagrams_Charts_Images",
                self._files.next_version_name(
                    project.output_dir, "10_Diagrams_Charts_Images", "일정차트", ".png"
                ),
                gantt,
            )
            ctx.diagram_paths["gantt"] = str(stored.path)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"일정 차트 생성 실패: {exc}")
        staffing_png = build_staffing_chart(ctx, font_path=font)
        if staffing_png:
            stored = self._files.save_bytes(
                project.output_dir,
                "10_Diagrams_Charts_Images",
                self._files.next_version_name(
                    project.output_dir, "10_Diagrams_Charts_Images", "공수차트", ".png"
                ),
                staffing_png,
            )
            ctx.diagram_paths["staffing"] = str(stored.path)
        # Excel
        traces = self._repos.traces.find(project.id)
        builders = (
            (DeliverableKind.REQUIREMENT_SPEC_XLSX, lambda: build_requirement_spec(ctx)),
            (
                DeliverableKind.TRACE_MATRIX_XLSX,
                lambda: build_trace_matrix(
                    ctx,
                    traces,
                    self._repos.screens.find(project.id),
                    self._repos.unit_tests.find(project.id),
                    self._repos.integration_tests.find(project.id),
                ),
            ),
            (DeliverableKind.WBS_GANTT_XLSX, lambda: build_wbs_gantt(ctx)),
            (DeliverableKind.STAFFING_PLAN_XLSX, lambda: build_staffing_plan(ctx)),
        )
        for dk, fn in builders:
            try:
                result.deliverables.append(self._store(project, dk, fn(), ctx))
            except Exception as exc:  # noqa: BLE001
                log.exception("생성 실패 %s", dk)
                result.errors.append(f"{dk.value} 생성 실패: {type(exc).__name__}: {exc}")
        # PPT
        rfp_toc = rfp_toc_from_blocks(self._extraction.current_blocks(project, required_only=True))
        outline = decide_outline(ctx, rfp_toc)
        result.outline = outline
        for dk, fn in (
            (DeliverableKind.SUBMISSION_PPTX, lambda: build_submission_deck(ctx, outline)),
            (DeliverableKind.PRESENTATION_PPTX, lambda: build_presentation_deck(ctx, outline)),
        ):
            try:
                result.deliverables.append(self._store(project, dk, fn(), ctx))
            except Exception as exc:  # noqa: BLE001
                log.exception("생성 실패 %s", dk)
                result.errors.append(f"{dk.value} 생성 실패: {type(exc).__name__}: {exc}")
        self._write_outline(project, outline, ctx)
        self._audit.record(
            project.id,
            "deliverables.generated",
            actor=actor,
            actor_kind=ActorKind.USER,
            payload={
                "files": [d.file_path for d in result.deliverables],
                "errors": result.errors,
                "review_items": len(result.review_items),
                "outline_source": outline[0].source if outline else None,
            },
        )
        return result

    def _store(
        self, project: Project, kind: DeliverableKind, data: bytes, ctx: GenerationContext
    ) -> Deliverable:
        subdir, stem, suffix = KIND_TARGETS[kind]
        name = self._files.next_version_name(project.output_dir, subdir, stem, suffix)
        stored = self._files.save_bytes(project.output_dir, subdir, name, data)
        version = "v" + name.rsplit("_v", 1)[1].rsplit(".", 1)[0]
        d = Deliverable(
            project_id=project.id,
            kind=kind,
            file_path=stored.relative_path,
            version=version,
            sha256=stored.sha256,
            integrity_status=IntegrityStatus.PENDING,
            qa_status=QaStatus.PENDING,
            created_by="generator",
        )
        self._repos.deliverables.insert(d)
        return d

    def _write_outline(
        self, project: Project, outline: list[OutlineSection], ctx: GenerationContext
    ) -> None:
        payload = {
            "source": outline[0].source if outline else None,
            "sections": [o.__dict__ for o in outline],
            "review_items": ctx.review_notes,
        }
        name = self._files.next_version_name(
            project.output_dir, "07_Submission_Proposal_PPT", "목차결정", ".json"
        )
        self._files.save_bytes(
            project.output_dir,
            "07_Submission_Proposal_PPT",
            name,
            json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"),
        )

    # --- 조회·최종본 --------------------------------------------------------------------------
    def latest_deliverables(self, project: Project) -> dict[DeliverableKind, Deliverable]:
        out: dict[DeliverableKind, Deliverable] = {}
        for d in self._repos.deliverables.find(project.id, order_by="created_at"):
            out[d.kind] = d
        return out

    def finalize(self, project: Project, *, approver: str, comments: str) -> list[str]:
        """QA 통과·사람 승인 후 최신 산출물을 13_Final_Deliverables로 복사한다 (원본은 그대로 둔다)."""
        latest = self.latest_deliverables(project)
        blocked = [
            d
            for d in latest.values()
            if d.integrity_status != IntegrityStatus.PASSED or d.qa_status == QaStatus.FAILED
        ]
        if blocked:
            raise ValidationError(
                "무결성 검사를 통과하지 못했거나 QA 실패인 산출물이 있어 최종본으로 확정할 수 없습니다.",
                cause=", ".join(d.file_path for d in blocked),
                resolution="QA를 다시 실행하고 오류를 해결하십시오.",
            )
        final_dir = self._paths.subdir(project.output_dir, FINAL_SUBDIR)
        final_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for d in latest.values():
            src = self._paths.resolve_output(d.file_path)
            dst = final_dir / src.name
            if dst.exists():
                raise PWAError(
                    f"최종본이 이미 존재합니다: {dst.name}",
                    resolution="새 버전을 생성한 뒤 확정하십시오.",
                )
            shutil.copy2(src, dst)
            copied.append(self._paths.relative_output(dst))
        self._audit.record(
            project.id,
            "deliverables.finalized",
            actor=approver,
            actor_kind=ActorKind.USER,
            payload={"files": copied, "comments": comments},
        )
        return copied
