"""산출물 생성 서비스: 공통 데이터 → 다이어그램·Excel·PPT, Deliverable 기록, 최종본 분리.

실행 조건은 오케스트레이터가 검사한다(Gate 1). 이 서비스는 데이터 조립·파일 생성·기록만 담당한다.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
)
from proposal_agent.generators.pptx.outline import ChapterPlan, OutlineSection, plan_chapters
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
from proposal_agent.storage.manifest import record_generation
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.ingest.service import ExtractionService
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService
    from proposal_agent.services.template_service import TemplateHit, TemplateService

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


def research_links(req: Any, research: Any) -> bool:
    """조사 기록이 요구사항을 가리키는가 (내부 ID 또는 RFP 자체 ID)."""
    ids = set(research.related_requirement_ids)
    return req.id in ids or bool(req.rfp_requirement_id and req.rfp_requirement_id in ids)


@dataclass
class GenerationResult:
    chapters: list[ChapterPlan] = field(default_factory=list)
    template_names: dict[str, str] = field(default_factory=dict)
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
        templates: TemplateService | None = None,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._files = files
        self._planning = planning
        self._steps = steps
        self._extraction = extraction
        self._templates = templates

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
        # PPT (템플릿이 등록되어 있으면 그 양식, 없으면 기본 양식)
        rfp_toc = self._extraction.rfp_proposal_toc(project)
        toc_tree = self._extraction.rfp_proposal_toc_tree(project)
        # 목차 트리(장/절)가 있으면 평면 목차를 섹션 키에 다시 매핑하지 않는다 — 트리가 뼈대, 섹션은 데이터 기준
        outline = decide_outline(ctx, [] if toc_tree else rfp_toc)
        result.outline = outline
        sub_hit = self._template_for(project, "submission")
        pres_hit = self._template_for(project, "presentation")
        chapters = plan_chapters(outline, toc_tree, sub_hit.profile.chapters if sub_hit else None)
        result.chapters = chapters
        result.template_names = {
            k: h.document.file_name
            for k, h in (("submission", sub_hit), ("presentation", pres_hit))
            if h
        }
        if sub_hit is None:
            result.review_items.append(
                "제출용 제안서 템플릿이 등록되지 않아 코드 기본 양식(16:9)으로 생성했습니다. "
                "고객 양식이 있으면 프로젝트 화면에서 '제안서 템플릿(PPT)'로 등록 후 재생성하십시오."
            )
            ctx.review_notes.append(
                "제출용 제안서 템플릿이 등록되지 않아 코드 기본 양식(16:9)으로 생성했습니다. "
                "고객 양식이 있으면 프로젝트 화면에서 '제안서 템플릿(PPT)'로 등록 후 재생성하십시오."
            )
        for dk, fn in (
            (
                DeliverableKind.SUBMISSION_PPTX,
                lambda: build_submission_deck(
                    ctx,
                    outline,
                    template_profile=sub_hit.profile if sub_hit else None,
                    template_data=sub_hit.data if sub_hit else None,
                    toc_tree=toc_tree,
                    chapters=chapters,
                ),
            ),
            (
                DeliverableKind.PRESENTATION_PPTX,
                lambda: build_presentation_deck(
                    ctx,
                    outline,
                    template_profile=pres_hit.profile if pres_hit else None,
                    template_data=pres_hit.data if pres_hit else None,
                    toc_tree=toc_tree,
                ),
            ),
        ):
            try:
                result.deliverables.append(self._store(project, dk, fn(), ctx))
            except Exception as exc:  # noqa: BLE001
                log.exception("생성 실패 %s", dk)
                result.errors.append(f"{dk.value} 생성 실패: {type(exc).__name__}: {exc}")
        self._write_outline(
            project, outline, ctx, chapters=chapters, templates=result.template_names
        )
        try:  # manifest.json: 이번 실행의 산출물·보조 파일·오류 (QA 결과는 QA 완료 시 덧붙임)
            record_generation(
                self._paths,
                project,
                result.deliverables,
                run_kind="generation",
                version=ctx.version,
                run_id=f"gen-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                extra_files={
                    k: self._paths.relative_output(v) for k, v in ctx.diagram_paths.items()
                },
                errors=result.errors,
                actor=actor,
            )
        except Exception as exc:  # noqa: BLE001  manifest 실패가 생성을 막지 않는다
            log.warning("manifest 기록 실패: %s", exc)
            result.review_items.append(f"manifest.json 기록 실패: {exc}")
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

    def _template_for(self, project: Project, purpose: str) -> TemplateHit | None:
        if self._templates is None:
            return None
        return self._templates.for_purpose(project, purpose)

    def feasibility_brief(self, ctx: GenerationContext) -> str:
        """필수 요구사항별 구현 방안·근거 조사 요약 (에이전트·QA 공용)."""
        lines: list[str] = []
        missing = 0
        for r in ctx.mandatory_requirements():
            if r.type.value not in ("functional", "non_functional"):
                continue
            linked = [t for t in ctx.research if research_links(r, t)]
            basis = "; ".join(
                f"'{t.topic[:30]}'={t.feasibility.value}(출처 {len(t.sources)})" for t in linked[:3]
            )
            if not linked:
                missing += 1
            lines.append(
                f"- {r.id}{' / ' + r.rfp_requirement_id if r.rfp_requirement_id else ''} {r.name[:40]} | "
                f"구현 방안: {(r.implementation_approach or '미작성')[:100]} | 근거 조사: {basis or '조사 없음'}"
            )
        head = f"필수 기능·비기능 요구사항 {len(lines)}건, 근거 조사 없음 {missing}건"
        return head + "\n" + "\n".join(lines[:150])

    def research_gaps(self, ctx: GenerationContext) -> list[str]:
        """근거 조사가 없는 필수 기능 요구사항 ID."""
        return [
            r.id
            for r in ctx.mandatory_requirements()
            if r.type.value == "functional" and not any(research_links(r, t) for t in ctx.research)
        ]

    def proposal_brief(self, project: Project) -> str:
        """제안서 작성 에이전트 프롬프트: 템플릿 관행 + RFP 지정 목차 + 기준 데이터 요약."""
        ctx = self.build_context(project)
        parts: list[str] = []
        hit = self._template_for(project, "submission")
        if hit is not None:
            parts.append(
                "<proposal_template>\n"
                + f"파일: {hit.document.file_name}\n"
                + hit.profile.summary_text()
                + "\n</proposal_template>"
            )
        else:
            parts.append(
                "<proposal_template>\n등록된 템플릿 없음 — 코드 기본 양식(16:9, 소절당 글머리 8개 이하)\n</proposal_template>"
            )
        tree = self._extraction.rfp_proposal_toc_tree(project)
        if tree:
            lines = []
            for ch in tree:
                lines.append(f"{ch.get('numeral', '')}. {ch.get('title', '')}".strip(". "))
                for i, sec in enumerate(ch.get("sections", []), start=1):
                    guide = "; ".join(sec.get("guide", [])[:3])
                    lines.append(
                        f"  {i}. {sec.get('title', '')}"
                        + (f" — 작성방법: {guide}" if guide else "")
                    )
            parts.append("<rfp_toc>\n" + "\n".join(lines) + "\n</rfp_toc>")
        else:
            parts.append("<rfp_toc>\nRFP에 지정 목차 없음 — 기본 목차 사용\n</rfp_toc>")
        figs = {
            "period": f"{ctx.period_start} ~ {ctx.period_end}"
            if ctx.period_start and ctx.period_end
            else "기간 미정",
            "total_md": str(ctx.total_effort_md),
            "roles": [
                {"role": r.role_name, "headcount": r.headcount_planned, "grade": r.grade or ""}
                for r in ctx.roles[:20]
            ],
        }
        data = {
            "project": {"name": project.name, "client": project.client_name or ""},
            "figures": figs,
            "requirements": [
                {
                    "id": r.id,
                    "rfp_id": r.rfp_requirement_id or "",
                    "name": r.name[:60],
                    "type": r.type.value,
                    "scope": r.scope_class.value,
                    "acceptance": r.acceptance_status.value,
                    "approach": (r.implementation_approach or "")[:120],
                }
                for r in ctx.requirements[:150]
            ],
            "components": [
                {
                    "code": c.id,
                    "layer": c.layer,
                    "name": c.name,
                    "technology": c.technology or "미정",
                }
                for c in ctx.components[:40]
            ],
            "research": [
                {
                    "topic": t.topic[:60],
                    "feasibility": t.feasibility.value,
                    "summary": (t.summary or "")[:160],
                }
                for t in ctx.research[:20]
            ],
            "analysis": {
                k: (ctx.analysis or {}).get(k)
                for k in (
                    "overview",
                    "client_goals",
                    "scope_summary",
                    "constraints",
                    "evaluation_criteria",
                )
                if (ctx.analysis or {}).get(k)
            },
            "wbs_top": [
                {"code": w.code, "name": w.name, "effort_md": str(w.effort_md)}
                for w in ctx.wbs
                if w.parent_id is None
            ][:30],
        }
        parts.append("<feasibility>\n" + self.feasibility_brief(ctx) + "\n</feasibility>")
        parts.append("<data>\n" + json.dumps(data, ensure_ascii=False)[:24000] + "\n</data>")
        parts.append(
            "위 템플릿 관행과 RFP 지정 목차를 따르는 제출용 제안 문안(profile=submission)을 JSON으로 반환하라. "
            "sections[]마다 chapter·section·number·lead_message를 채우고, 표가 적합한 절은 table_headers/table_rows를 쓴다."
        )
        return "\n\n".join(parts)

    def _write_outline(
        self,
        project: Project,
        outline: list[OutlineSection],
        ctx: GenerationContext,
        *,
        chapters: list[ChapterPlan] | None = None,
        templates: dict[str, str] | None = None,
    ) -> None:
        payload = {
            "source": outline[0].source if outline else None,
            "sections": [o.__dict__ for o in outline],
            "chapters": [c.as_dict() for c in chapters or []],
            "templates": templates or {},
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
