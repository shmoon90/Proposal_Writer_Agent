"""요구사항 추출·독립 검증·검토·Gate 1 서비스 (Phase 2).

LLM은 청크 단위로 요구사항 초안과 검증 보고를 만들고, 다음은 모두 코드가 결정한다:
ID 발급, 출처(block) 검증과 SourceRef 생성, 중복 병합, 상태 전이, 검증 결과 저장, Gate 1 판정.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from proposal_agent.agents import AgentRequest, AgentRunner, load_prompt
from proposal_agent.agents.roles import get_role
from proposal_agent.agents.schemas import RequirementExtraction
from proposal_agent.config.errors import AgentRunError, NotFoundError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.ingest.chunker import Chunk, build_chunks
from proposal_agent.ingest.service import ExtractionService
from proposal_agent.models import (
    ActorKind,
    ExtractedBlock,
    GateEvaluation,
    GateStatus,
    Project,
    Requirement,
    RequirementDraft,
    RequirementStatus,
    RequirementType,
    ReviewStatus,
    ScopeClass,
    SourceRef,
    ValidationLevel,
    ValidationResult,
    ValidationTargetType,
    VerificationReport,
    VerificationStatus,
)
from proposal_agent.requirements.id_policy import RequirementIdPolicy, normalize_text
from proposal_agent.requirements.optimizer import (
    CROSS_CHECK_MAX_ITEMS,
    ChunkCache,
    RunPlan,
    build_windows,
    chunk_key,
    compact_items,
    dumps_compact,
    has_signal,
)
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("requirements.service")

GATE1_KEY = "gate1"
ROLE_EXTRACTOR = "requirement_extractor"
ROLE_VERIFIER = "requirement_verifier"
LOW_CONFIDENCE = 0.6

EDITABLE_FIELDS = {
    "name",
    "description",
    "type",
    "category",
    "scope_class",
    "is_mandatory",
    "priority",
    "implementation_approach",
    "acceptance_status",
    "verification_method",
    "notes",
    "impact_note",
    "linked_deliverables",
    "tags",
    "rfp_quote",
}


@dataclass
class ExtractionSummary:
    created: list[Requirement] = field(default_factory=list)
    updated: list[Requirement] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    dropped_missing_source: list[str] = field(default_factory=list)
    chunks: int = 0
    cost_usd: float = 0.0
    turns: int = 0
    calls: int = 0
    skipped_chunks: int = 0
    cached_chunks: int = 0
    input_chars: int = 0
    uncovered_rfp_ids: list[str] = field(default_factory=list)


@dataclass
class VerificationSummary:
    findings: list[ValidationResult] = field(default_factory=list)
    verdicts: int = 0
    coverage: float = 0.0
    chunks: int = 0
    cost_usd: float = 0.0
    summaries: list[str] = field(default_factory=list)
    calls: int = 0
    skipped_chunks: int = 0
    cached_chunks: int = 0
    input_chars: int = 0


class RequirementService:
    def __init__(
        self,
        repos: Repositories,
        settings: Settings,
        audit: AuditService,
        extraction: ExtractionService,
        runner: AgentRunner,
        paths: ProjectPaths | None = None,
    ) -> None:
        self._repos = repos
        self._settings = settings
        self._audit = audit
        self._extraction = extraction
        self._runner = runner
        self._paths = paths or ProjectPaths()

    # --- 조회 -------------------------------------------------------------------------
    def id_policy(self, project: Project) -> RequirementIdPolicy:
        prefixes = {**self._settings.id_prefixes, **(project.settings.get("id_prefixes") or {})}
        return RequirementIdPolicy(self._repos.sequences, prefixes, self._settings.id_width)

    def list_requirements(
        self, project: Project, *, include_deleted: bool = False
    ) -> list[Requirement]:
        reqs = self._repos.requirements.find(project.id, order_by="id")
        if include_deleted:
            return reqs
        return [r for r in reqs if r.status != RequirementStatus.DELETED]

    def get(self, project: Project, req_id: str) -> Requirement:
        return self._repos.requirements.get(req_id, project.id)

    def open_findings(self, project: Project, req_id: str | None = None) -> list[ValidationResult]:
        rows = self._repos.validations.find(
            project.id, target_type=str(ValidationTargetType.REQUIREMENT), resolved=False
        )
        if req_id is None:
            return rows
        return [
            v
            for v in rows
            if v.target_id == req_id or req_id in v.detail.get("requirement_ids", [])
        ]

    # --- 추출 -------------------------------------------------------------------------
    # --- 실행 계획·상한 -------------------------------------------------------------------
    def project_cost(self, project: Project) -> float:
        return round(sum(r.cost_usd for r in self._repos.step_runs.find(project.id)), 4)

    def _cache(self, project: Project) -> ChunkCache:
        ws = self._paths.ensure_workspace(project.workspace_dir or project.id)
        return ChunkCache(ws / "cache", enabled=self._settings.chunk_cache)

    def plan_extraction(self, project: Project) -> RunPlan:
        blocks = self._extraction.current_blocks(project, required_only=True)
        chunks = build_chunks(blocks, self._settings.extraction_chunk_chars)
        return self._plan(
            "extract",
            project,
            chunks,
            blocks,
            ROLE_EXTRACTOR,
            load_prompt(ROLE_EXTRACTOR),
            cross_check=False,
        )

    def plan_verification(self, project: Project) -> RunPlan:
        blocks = self._extraction.current_blocks(project, required_only=True)
        windows = build_windows(
            build_chunks(blocks, self._settings.extraction_chunk_chars),
            self._settings.verification_chunk_chars,
        )
        reqs = self.list_requirements(project)
        plan = self._plan(
            "verify",
            project,
            windows,
            blocks,
            ROLE_VERIFIER,
            load_prompt(ROLE_VERIFIER),
            cross_check=len(windows) > 1 and len(reqs) > 1,
            reqs=reqs,
        )
        return plan

    def _plan(
        self,
        kind: str,
        project: Project,
        chunks: list[Chunk],
        blocks: list[ExtractedBlock],
        role_key: str,
        system_prompt: str,
        *,
        cross_check: bool,
        reqs: list[Requirement] | None = None,
    ) -> RunPlan:
        by_id = {b.id: b for b in blocks}
        cache = self._cache(project)
        role = get_role(role_key)
        plan = RunPlan(
            kind=kind,
            chunks_total=len(chunks),
            cross_check=cross_check,
            max_cost_per_call=min(role.max_budget_usd, self._settings.max_budget_usd_per_step * 3),
            max_calls=self._settings.max_agent_calls_per_step,
            project_cost_so_far=self.project_cost(project),
            project_budget=self._settings.max_budget_usd_per_project,
        )
        for ch in chunks:
            if kind == "verify":
                ids = set(ch.block_ids)
                in_scope = [
                    r for r in (reqs or []) if any(ref.block_id in ids for ref in r.source_refs)
                ]
                if (
                    self._settings.skip_low_signal_chunks
                    and not in_scope
                    and not has_signal(ch, by_id)
                ):
                    plan.skipped.append(ch.index)
                    continue
                prompt = self._verification_prompt(project, ch, in_scope)
            else:
                if self._settings.skip_low_signal_chunks and not has_signal(ch, by_id):
                    plan.skipped.append(ch.index)
                    continue
                prompt = self._extraction_prompt(project, ch)
            if (
                cache.get(chunk_key(role_key, system_prompt, prompt, self._settings.model_primary))
                is not None
            ):
                plan.cached.append(ch.index)
                continue
            plan.to_call.append(ch.index)
            plan.input_chars += len(prompt)
        return plan

    def _call(
        self,
        project: Project,
        role_key: str,
        system_prompt: str,
        prompt: str,
        schema: type[Any],
        cache: ChunkCache,
        stats: Any,
    ) -> tuple[Any, bool]:
        """캐시 우선 호출. (출력, 캐시 적중) 반환. 호출 전 누적 예산을 다시 검사한다."""
        key = chunk_key(role_key, system_prompt, prompt, self._settings.model_primary)
        hit = cache.get(key)
        if hit is not None:
            stats.cached_chunks += 1
            return schema.model_validate(hit["output"]), True
        role = get_role(role_key)
        budget = self._settings.max_budget_usd_per_project
        if budget > 0 and self.project_cost(project) + stats.cost_usd > budget:
            raise ValidationError(
                "프로젝트 누적 비용 상한에 도달해 중단합니다.",
                cause=f"누적 ${self.project_cost(project) + stats.cost_usd:.2f} ≥ 상한 ${budget:.2f}",
                resolution="PWA_MAX_BUDGET_USD_PER_PROJECT를 올리거나 실행을 나누십시오. 지금까지 처리한 결과는 저장되어 있습니다.",
            )
        if (
            self._settings.max_agent_calls_per_step
            and stats.calls >= self._settings.max_agent_calls_per_step
        ):
            raise ValidationError(
                f"에이전트 호출 상한({self._settings.max_agent_calls_per_step}회)에 도달해 중단합니다.",
                resolution="PWA_MAX_AGENT_CALLS_PER_STEP을 올리거나 문서를 나누어 처리하십시오.",
            )
        response = self._runner.run_structured(
            AgentRequest(
                role=role_key,
                system_prompt=system_prompt,
                prompt=prompt,
                max_turns=role.max_turns,
                max_budget_usd=min(role.max_budget_usd, self._settings.max_budget_usd_per_step * 3),
                model=self._settings.model_primary,
                effort=role.effort,
            ),
            schema,
        )
        stats.calls += 1
        stats.cost_usd += response.cost_usd
        stats.turns = getattr(stats, "turns", 0) + response.num_turns
        stats.input_chars += len(prompt)
        cache.put(
            key,
            response.output.model_dump(mode="json"),
            cost_usd=response.cost_usd,
            turns=response.num_turns,
        )
        return response.output, False

    def _check_rfp_coverage(self, project: Project, reqs: list[Requirement]) -> list[str]:
        """RFP가 부여한 요구사항 ID마다 추출된 요구사항이 하나 이상 연결되었는지 (코드 검사)."""
        prof = self._extraction.rfp_profile(project)
        if prof is None or not prof.requirement_index:
            return []
        covered_ids = {r.rfp_requirement_id for r in reqs if r.rfp_requirement_id}
        covered_blocks = {ref.block_id for r in reqs for ref in r.source_refs if ref.block_id}
        uncovered = [
            e.rfp_id
            for e in prof.requirement_index
            if e.rfp_id not in covered_ids and not (set(e.block_ids) & covered_blocks)
        ]
        for rid in uncovered:
            entry = next(e for e in prof.requirement_index if e.rfp_id == rid)
            self._repos.validations.insert(
                ValidationResult(
                    project_id=project.id,
                    target_type=ValidationTargetType.REQUIREMENT,
                    target_id=rid,
                    rule_id="rfp.uncovered_id",
                    level=ValidationLevel.WARNING,
                    message=f"RFP 요구사항 {rid} '{entry.name}'에 연결된 추출 요구사항이 없음",
                    detail={
                        "resolution": "해당 절을 확인해 요구사항을 수동 추가하거나 재추출하십시오.",
                        "page": entry.page,
                    },
                    validator="code:rfp_profile",
                )
            )
        return uncovered

    # --- 추출 -------------------------------------------------------------------------------
    def extract(
        self, project: Project, *, actor: str = "agent:requirement_extractor"
    ) -> ExtractionSummary:
        blocks = self._extraction.current_blocks(project, required_only=True)
        if not blocks:
            raise ValidationError(
                "추출된 문서 블록이 없습니다.",
                cause="필수 문서 추출 미실행 또는 실패",
                resolution="문서 추출 단계를 먼저 실행하고 Gate 0을 확인하십시오.",
            )
        chunks = build_chunks(blocks, self._settings.extraction_chunk_chars)
        block_map = {b.id: b for b in blocks}
        plan = self._plan(
            "extract",
            project,
            chunks,
            blocks,
            ROLE_EXTRACTOR,
            load_prompt(ROLE_EXTRACTOR),
            cross_check=False,
        )
        plan.require_within_limits()
        policy = self.id_policy(project)
        existing = self.list_requirements(project, include_deleted=True)
        summary = ExtractionSummary(chunks=len(chunks), skipped_chunks=len(plan.skipped))
        system_prompt = load_prompt(ROLE_EXTRACTOR)
        cache = self._cache(project)
        seen_in_batch: list[Requirement] = []
        skipped = set(plan.skipped)

        for chunk in chunks:
            if chunk.index in skipped:
                continue
            prompt = self._extraction_prompt(project, chunk)
            try:
                output, _cached = self._call(
                    project,
                    ROLE_EXTRACTOR,
                    system_prompt,
                    prompt,
                    RequirementExtraction,
                    cache,
                    summary,
                )
            except AgentRunError as exc:
                self._audit.record_error(
                    project.id,
                    "requirements.extract_chunk_failed",
                    exc,
                    actor=actor,
                    payload={"chunk": chunk.index},
                )
                raise
            summary.unresolved.extend(output.unresolved_items)
            chunk_ids = set(chunk.block_ids)
            for draft in output.requirements:
                valid_ids = [bid for bid in draft.source_block_ids if bid in chunk_ids]
                if not valid_ids:
                    summary.dropped_missing_source.append(draft.name)
                    self._repos.validations.insert(
                        ValidationResult(
                            project_id=project.id,
                            target_type=ValidationTargetType.REQUIREMENT,
                            target_id="(미생성)",
                            rule_id="extract.missing_source",
                            level=ValidationLevel.WARNING,
                            message=f"출처 블록이 유효하지 않아 생성하지 않음: {draft.name}",
                            detail={
                                "draft": draft.model_dump(mode="json"),
                                "chunk": chunk.index,
                                "resolution": "원문 위치를 확인한 뒤 수동으로 추가하십시오.",
                            },
                            validator=f"code:{ROLE_EXTRACTOR}",
                        )
                    )
                    continue
                refs = [self._source_ref(block_map[bid], draft.rfp_quote) for bid in valid_ids]
                req_id, matched = policy.resolve(
                    project.id,
                    draft.type,
                    name=draft.name,
                    rfp_quote=draft.rfp_quote,
                    existing=[*existing, *seen_in_batch],
                )
                if matched:
                    current = next(r for r in [*existing, *seen_in_batch] if r.id == req_id)
                    if current.status == RequirementStatus.DRAFT:
                        self._merge_draft(current, draft, refs, actor)
                        self._repos.requirements.update(current)
                        summary.updated.append(current)
                    continue
                req = Requirement.from_draft(
                    draft, id=req_id, project_id=project.id, created_by=actor, source_refs=refs
                )
                if not req.rfp_requirement_id:
                    req.rfp_requirement_id = next(
                        (
                            block_map[bid].rfp_requirement_id
                            for bid in valid_ids
                            if block_map[bid].rfp_requirement_id
                        ),
                        None,
                    )
                req.add_history(actor, "extracted", note=f"chunk {chunk.index}")
                if draft.confidence < LOW_CONFIDENCE:
                    req.review_status = ReviewStatus.PENDING
                self._repos.requirements.insert(req)
                seen_in_batch.append(req)
                summary.created.append(req)

        summary.uncovered_rfp_ids = self._check_rfp_coverage(project, [*existing, *summary.created])
        self._audit.record(
            project.id,
            "requirements.extracted",
            actor=actor,
            actor_kind=ActorKind.AGENT,
            payload={
                "created": len(summary.created),
                "updated": len(summary.updated),
                "chunks": summary.chunks,
                "calls": summary.calls,
                "skipped": summary.skipped_chunks,
                "cached": summary.cached_chunks,
                "input_chars": summary.input_chars,
                "unresolved": len(summary.unresolved),
                "dropped": len(summary.dropped_missing_source),
                "cost_usd": round(summary.cost_usd, 4),
                "turns": summary.turns,
            },
        )
        return summary

    def _extraction_prompt(self, project: Project, chunk: Chunk) -> str:
        ids = sorted({m for m in re.findall(r'rfp_id="([^"]+)"', chunk.text)})
        kinds = sorted({m for m in re.findall(r'section="([^"]+)"', chunk.text)})
        hint = ""
        if kinds:
            hint += f"절 종류: {', '.join(kinds)}\n"
        if ids:
            hint += (
                f"이 청크의 RFP 요구사항 ID: {', '.join(ids)} — block의 rfp_id 속성을 각 항목의 rfp_requirement_id에 적고, "
                "ID 아래 1) 2) / -. 세부 항목은 각각 별도 요구사항으로 추출하라.\n"
            )
        return (
            f"프로젝트: {project.name}\n청크 {chunk.index + 1} / 섹션: {', '.join(chunk.sections) or '(없음)'}\n{hint}\n"
            f"<document>\n{chunk.text}\n</document>\n\n"
            "위 원문에서 요구사항을 추출해 JSON으로 반환하라. source_block_ids에는 위 block id만 사용하라."
        )

    @staticmethod
    def _source_ref(block: ExtractedBlock, quote: str) -> SourceRef:
        return SourceRef(
            document_id=block.source_document_id,
            block_id=block.id,
            page=block.location.page,
            section=block.location.section,
            location_label=block.source_label
            + (f" · {block.rfp_requirement_id}" if block.rfp_requirement_id else ""),
            quote=quote or block.text[:300],
        )

    @staticmethod
    def _merge_draft(
        current: Requirement, draft: RequirementDraft, refs: list[SourceRef], actor: str
    ) -> None:
        known = {r.block_id for r in current.source_refs}
        current.source_refs.extend(r for r in refs if r.block_id not in known)
        if len(draft.description) > len(current.description):
            current.description = draft.description
        current.confidence = max(current.confidence, draft.confidence)
        current.add_history(actor, "re-extracted", note="기존 ID 유지, 출처 병합")

    # --- 독립 검증 -------------------------------------------------------------------
    def verify(
        self, project: Project, *, actor: str = "agent:requirement_verifier"
    ) -> VerificationSummary:
        reqs = self.list_requirements(project)
        if not reqs:
            raise ValidationError(
                "검증할 요구사항이 없습니다.", resolution="요구사항 추출을 먼저 실행하십시오."
            )
        blocks = self._extraction.current_blocks(project, required_only=True)
        windows = build_windows(
            build_chunks(blocks, self._settings.extraction_chunk_chars),
            self._settings.verification_chunk_chars,
        )
        system_prompt = load_prompt(ROLE_VERIFIER)
        cross = len(windows) > 1 and len(reqs) > 1
        plan = self._plan(
            "verify",
            project,
            windows,
            blocks,
            ROLE_VERIFIER,
            system_prompt,
            cross_check=cross,
            reqs=reqs,
        )
        plan.require_within_limits()
        summary = VerificationSummary(chunks=len(windows), skipped_chunks=len(plan.skipped))
        req_by_id = {r.id: r for r in reqs}
        verdict_counts: dict[str, int] = {}
        coverages: list[float] = []
        cache = self._cache(project)
        skipped = set(plan.skipped)

        def run(prompt: str, label: str) -> VerificationReport:
            output, _cached = self._call(
                project, ROLE_VERIFIER, system_prompt, prompt, VerificationReport, cache, summary
            )
            report: VerificationReport = output
            if report.summary:
                summary.summaries.append(f"[{label}] {report.summary}")
            return report

        for window in windows:
            if window.index in skipped:
                continue
            window_ids = set(window.block_ids)
            in_scope = [r for r in reqs if any(ref.block_id in window_ids for ref in r.source_refs)]
            report = run(
                self._verification_prompt(project, window, in_scope), f"window {window.index + 1}"
            )
            coverages.append(report.coverage_estimate)
            self._apply_report(
                project, report, req_by_id, verdict_counts, summary, actor, window.index
            )

        if cross:
            report = run(self._cross_check_prompt(project, reqs), "cross_check")
            self._apply_report(project, report, req_by_id, verdict_counts, summary, actor, None)

        for req in reqs:
            self._repos.requirements.update(req)
        summary.verdicts = sum(verdict_counts.values())
        summary.coverage = round(sum(coverages) / len(coverages), 3) if coverages else 0.0
        self._audit.record(
            project.id,
            "requirements.verified",
            actor=actor,
            actor_kind=ActorKind.AGENT,
            payload={
                "findings": len(summary.findings),
                "verdicts": verdict_counts,
                "coverage": summary.coverage,
                "windows": summary.chunks,
                "calls": summary.calls,
                "skipped": summary.skipped_chunks,
                "cached": summary.cached_chunks,
                "input_chars": summary.input_chars,
                "cost_usd": round(summary.cost_usd, 4),
            },
        )
        return summary

    def _apply_report(
        self,
        project: Project,
        report: VerificationReport,
        req_by_id: dict[str, Requirement],
        verdict_counts: dict[str, int],
        summary: VerificationSummary,
        actor: str,
        chunk_index: int | None,
    ) -> None:
        for v in report.verdicts:
            req = req_by_id.get(v.requirement_id)
            if req is None:
                continue
            status = {
                "verified": VerificationStatus.VERIFIED,
                "needs_revision": VerificationStatus.NEEDS_REVISION,
                "rejected": VerificationStatus.REJECTED,
            }.get(v.verdict)
            if status is None:
                continue
            # 더 나쁜 판정이 우선 (청크 검증 후 교차 검증에서 강등 가능)
            rank = {
                VerificationStatus.VERIFIED: 0,
                VerificationStatus.NEEDS_REVISION: 1,
                VerificationStatus.REJECTED: 2,
            }
            if req.verification_status == VerificationStatus.UNVERIFIED or rank[status] >= rank.get(
                req.verification_status, 0
            ):
                req.verification_status = status
            if status == VerificationStatus.VERIFIED and req.status == RequirementStatus.DRAFT:
                req.status = RequirementStatus.VERIFIED
            elif status != VerificationStatus.VERIFIED and req.status == RequirementStatus.VERIFIED:
                req.status = RequirementStatus.DRAFT
            if v.comment:
                req.add_history(actor, f"verdict:{v.verdict}", note=v.comment)
            verdict_counts[v.verdict] = verdict_counts.get(v.verdict, 0) + 1
        for f in report.findings:
            level = {"error": ValidationLevel.ERROR, "warning": ValidationLevel.WARNING}.get(
                f.severity, ValidationLevel.INFO
            )
            target = (
                f.requirement_ids[0]
                if f.requirement_ids and f.requirement_ids[0] in req_by_id
                else "(요구사항 집합)"
            )
            result = ValidationResult(
                project_id=project.id,
                target_type=ValidationTargetType.REQUIREMENT,
                target_id=target,
                rule_id=f"verify.{f.kind}",
                level=level,
                message=f.message,
                detail={
                    "requirement_ids": f.requirement_ids,
                    "evidence_quote": f.evidence_quote,
                    "source_block_ids": f.source_block_ids,
                    "suggested_fix": f.suggested_fix,
                    "suggested_scope_class": str(f.suggested_scope_class)
                    if f.suggested_scope_class
                    else None,
                    "chunk": chunk_index,
                    "resolution": f.suggested_fix or "검토 후 수정하거나 해결 처리하십시오.",
                },
                validator=f"agent:{ROLE_VERIFIER}",
            )
            self._repos.validations.insert(result)
            summary.findings.append(result)

    def _verification_prompt(self, project: Project, chunk: Chunk, reqs: list[Requirement]) -> str:
        items = compact_items(reqs, with_sources=True)
        return (
            f"모드: chunk\n프로젝트: {project.name}\n창 {chunk.index + 1}\n\n"
            f"<document>\n{chunk.text}\n</document>\n\n"
            f"<requirements>\n{dumps_compact(items)}\n</requirements>\n\n"
            "원문과 요구사항 목록을 대조해 검증 보고를 JSON으로 반환하라."
        )

    def _cross_check_prompt(self, project: Project, reqs: list[Requirement]) -> str:
        items = compact_items(reqs[:CROSS_CHECK_MAX_ITEMS], with_sources=False)
        note = f" (상위 {CROSS_CHECK_MAX_ITEMS}건만)" if len(reqs) > CROSS_CHECK_MAX_ITEMS else ""
        return (
            f"모드: cross_check\n프로젝트: {project.name}{note}\n\n"
            f"<requirements>\n{dumps_compact(items)}\n</requirements>\n\n"
            "전체 요구사항 목록에서 중복·모순·분류 불일치만 검사해 JSON으로 반환하라. verdicts는 비워도 된다."
        )

    # --- 사람 검토 ----------------------------------------------------------------------
    def update_requirement(
        self, project: Project, req_id: str, changes: dict[str, Any], *, actor: str, note: str = ""
    ) -> Requirement:
        req = self.get(project, req_id)
        if req.status == RequirementStatus.DELETED:
            raise ValidationError(
                f"삭제된 요구사항은 수정할 수 없습니다: {req_id}",
                resolution="복원 후 수정하십시오.",
            )
        applied: dict[str, Any] = {}
        for key, value in changes.items():
            if key not in EDITABLE_FIELDS:
                raise ValidationError(
                    f"수정할 수 없는 필드: {key}", cause=f"허용: {sorted(EDITABLE_FIELDS)}"
                )
            before = getattr(req, key)
            setattr(req, key, value)
            if getattr(req, key) != before:
                applied[key] = {
                    "before": before if not hasattr(before, "value") else before.value,
                    "after": value,
                }
        if applied:
            req.review_status = ReviewStatus.MODIFIED
            req.add_history(actor, "edited", changes=applied, note=note)
            self._repos.requirements.update(req)
            self._audit.record(
                project.id,
                "requirement.edited",
                actor=actor,
                actor_kind=ActorKind.USER,
                entity_type="Requirement",
                entity_id=req.id,
                payload={"changes": list(applied)},
            )
        return req

    def set_review(
        self, project: Project, req_id: str, status: ReviewStatus, *, actor: str, note: str = ""
    ) -> Requirement:
        req = self.get(project, req_id)
        req.review_status = status
        req.add_history(actor, f"review:{status}", note=note)
        self._repos.requirements.update(req)
        self._audit.record(
            project.id,
            "requirement.reviewed",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="Requirement",
            entity_id=req.id,
            payload={"status": str(status), "note": note},
        )
        return req

    def mark_deleted(
        self, project: Project, req_id: str, *, actor: str, reason: str
    ) -> Requirement:
        req = self.get(project, req_id)
        if not reason.strip():
            raise ValidationError("삭제 사유를 입력하십시오.")
        req.status = RequirementStatus.DELETED
        req.review_status = ReviewStatus.REJECTED
        req.add_history(actor, "deleted", note=reason)
        self._repos.requirements.update(req)
        self._audit.record(
            project.id,
            "requirement.deleted",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="Requirement",
            entity_id=req.id,
            payload={"reason": reason},
        )
        return req

    def add_manual(
        self,
        project: Project,
        draft: RequirementDraft,
        *,
        actor: str,
        scope_class: ScopeClass | None = None,
    ) -> Requirement:
        """사용자가 직접 추가 (부가 제안 등). 출처가 없으면 출처 없음으로 기록하고 검토 상태를 유지한다."""
        effective_scope = scope_class or draft.scope_class
        if effective_scope == ScopeClass.OPTIONAL_PROPOSAL and not draft.impact_note:
            raise ValidationError("부가 제안은 비용·일정·운영 영향(impact_note)을 적어야 합니다.")
        policy = self.id_policy(project)
        req_id = policy.allocate(project.id, draft.type)  # 검증 통과 후에만 ID 소비
        req = Requirement.from_draft(draft, id=req_id, project_id=project.id, created_by=actor)
        req.scope_class = effective_scope
        req.review_status = ReviewStatus.MODIFIED
        req.add_history(actor, "added_manually")
        self._repos.requirements.insert(req)
        self._audit.record(
            project.id,
            "requirement.added",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="Requirement",
            entity_id=req.id,
        )
        return req

    def resolve_finding(
        self, project: Project, validation_id: str, *, actor: str
    ) -> ValidationResult:
        v = self._repos.validations.get(validation_id)
        v.resolved = True
        self._repos.validations.update(v)
        self._audit.record(
            project.id,
            "validation.resolved",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ValidationResult",
            entity_id=v.id,
        )
        return v

    # --- Gate 1 ---------------------------------------------------------------------------
    def evaluate_gate1(self, project: Project, *, step_run_id: str | None = None) -> GateEvaluation:
        """요구사항 추출·독립 검증 게이트. 코드가 결정한다."""
        reqs = self.list_requirements(project)
        reasons: list[str] = []
        status = GateStatus.PASS
        metrics: dict[str, Any] = {"requirements": len(reqs)}
        if not reqs:
            return self._save_gate(
                project, GateStatus.FAIL, ["추출된 요구사항이 없습니다."], metrics, step_run_id
            )

        unverified = [r for r in reqs if r.verification_status == VerificationStatus.UNVERIFIED]
        if unverified:
            status = GateStatus.FAIL
            reasons.append(f"독립 검증을 거치지 않은 요구사항 {len(unverified)}건.")
        open_findings = self.open_findings(project)
        errors = [f for f in open_findings if f.level == ValidationLevel.ERROR]
        warnings = [f for f in open_findings if f.level == ValidationLevel.WARNING]
        metrics.update({"open_errors": len(errors), "open_warnings": len(warnings)})
        if errors:
            status = GateStatus.NEEDS_HUMAN_REVIEW if status != GateStatus.FAIL else status
            reasons.append(f"미해결 error 검증 결과 {len(errors)}건 (누락·왜곡·출처 오류).")
        rejected = [r for r in reqs if r.verification_status == VerificationStatus.REJECTED]
        revise = [r for r in reqs if r.verification_status == VerificationStatus.NEEDS_REVISION]
        if rejected:
            status = GateStatus.NEEDS_HUMAN_REVIEW if status != GateStatus.FAIL else status
            reasons.append(
                f"검증에서 기각된 요구사항 {len(rejected)}건: {', '.join(r.id for r in rejected[:5])}."
            )
        mandatory_uncertain = [
            r
            for r in reqs
            if r.is_mandatory
            and (
                r.confidence < LOW_CONFIDENCE
                or r.verification_status == VerificationStatus.NEEDS_REVISION
            )
        ]
        if mandatory_uncertain:
            status = GateStatus.NEEDS_HUMAN_REVIEW if status != GateStatus.FAIL else status
            reasons.append(
                f"필수 요구사항 중 해석이 불확실한 항목 {len(mandatory_uncertain)}건: {', '.join(r.id for r in mandatory_uncertain[:5])}."
            )
        elif revise:
            status = GateStatus.NEEDS_HUMAN_REVIEW if status != GateStatus.FAIL else status
            reasons.append(f"수정이 필요한 요구사항 {len(revise)}건.")
        no_source = [
            r
            for r in reqs
            if not r.source_refs and r.scope_class in (ScopeClass.MANDATORY, ScopeClass.SUPPORTING)
        ]
        if no_source:
            status = GateStatus.NEEDS_HUMAN_REVIEW if status != GateStatus.FAIL else status
            reasons.append(f"원본 출처가 없는 필수/지원 요구사항 {len(no_source)}건.")
        pending_review = [
            r
            for r in reqs
            if r.review_status == ReviewStatus.PENDING and r.confidence < LOW_CONFIDENCE
        ]
        if pending_review and status == GateStatus.PASS:
            status = GateStatus.NEEDS_HUMAN_REVIEW
            reasons.append(f"저신뢰 추출 항목 {len(pending_review)}건이 검토되지 않았습니다.")
        if status == GateStatus.PASS:
            reasons.append("모든 요구사항이 독립 검증을 통과했고 미해결 error가 없습니다.")
        metrics.update(
            {"rejected": len(rejected), "needs_revision": len(revise), "no_source": len(no_source)}
        )
        return self._save_gate(project, status, reasons, metrics, step_run_id)

    def _save_gate(
        self,
        project: Project,
        status: GateStatus,
        reasons: list[str],
        metrics: dict[str, Any],
        step_run_id: str | None,
    ) -> GateEvaluation:
        ev = GateEvaluation(
            project_id=project.id,
            gate_key=GATE1_KEY,
            status=status,
            reasons=reasons,
            metrics=metrics,
            evaluated_by="code:requirements.evaluate_gate1",
            step_run_id=step_run_id,
        )
        self._repos.gate_evaluations.insert(ev)
        self._audit.record(
            project.id,
            "gate.evaluated",
            entity_type="GateEvaluation",
            entity_id=ev.id,
            payload={"gate": GATE1_KEY, "status": str(status), "reasons": reasons},
        )
        return ev

    # --- 비교 보조 (테스트·UI) ----------------------------------------------------------------
    @staticmethod
    def names_normalized(reqs: list[Requirement]) -> set[str]:
        return {normalize_text(r.name) for r in reqs}

    @staticmethod
    def type_of(req_type: str | RequirementType) -> RequirementType:
        return RequirementType(req_type)

    def ensure_exists(self, project: Project, req_id: str) -> Requirement:
        try:
            return self.get(project, req_id)
        except NotFoundError as exc:
            raise NotFoundError(
                f"요구사항 없음: {req_id}", resolution="목록에서 ID를 확인하십시오."
            ) from exc
