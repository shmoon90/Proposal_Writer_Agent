"""변경 요청 생애주기: 접수 → 분석(규칙 + 선택적 AI) → 사용자 확인 → 승인/반려 → 기준 반영 → 문서 재생성.

원칙
- 승인 전에는 기준 데이터(요구사항·WBS·추적·인력)를 바꾸지 않는다. 분석 결과는 ``ChangeRequest`` 안에만 저장한다.
- 사용자가 확정한 값(``user_decision``/``user_override``/``user_edits``)과 규칙·AI 추론(``source``)을 구분해 저장한다.
- 반영은 DB 트랜잭션 안에서 수행한다. 오류가 나면 롤백하고 요청 상태를 ``error``로 남겨 재시도할 수 있게 한다.
- 기존 ID는 유지하고 새 ID는 승인 후에만 발급한다. 삭제는 상태 표시만 한다(물리 삭제 없음). 추적 링크는 자동 삭제하지 않고 '재검토 필요'로 표시한다.
- 새 문서는 ``<종류>_YYYYMMDDHHMM.xlsx``로 저장하고 같은 이름이 있으면 ``_1`` 접미사를 붙인다. 변경 전 파일·CR·승인·변경 후 파일을 Revision으로 연결한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.schemas import SemanticDiffDraft
from proposal_agent.changes.baseline_service import REVISION_SUBDIR, BaselineService
from proposal_agent.changes.impact import SimPlan, analyze_impact, simulate
from proposal_agent.changes.semantic import aspect_labels, classify_request, split_items
from proposal_agent.config.errors import AgentRunError, PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.excel import (
    build_requirement_spec,
    build_staffing_plan,
    build_trace_matrix,
    build_wbs_gantt,
)
from proposal_agent.models import (
    ActorKind,
    Approval,
    ApprovalDecision,
    ApprovalTarget,
    ChangeStatus,
    Deliverable,
    DeliverableKind,
    Dependency,
    Difficulty,
    DocumentKind,
    IntegrityStatus,
    Project,
    QaStatus,
    Requirement,
    RequirementStatus,
    RequirementTrace,
    RequirementType,
    ReviewStatus,
    Revision,
    StaffingAllocation,
    StaffRole,
    TraceTargetType,
    VerificationStatus,
    WBSItem,
    WBSLevel,
    utcnow,
)
from proposal_agent.models.change import (
    CandidateClass,
    ChangeCandidate,
    ChangeImpact,
    ChangeRequest,
    InputKind,
)
from proposal_agent.models.planning import TaskStatus
from proposal_agent.planning.calendar import BusinessCalendar, parse_holidays
from proposal_agent.planning.staffing import distribute_by_month
from proposal_agent.requirements.id_policy import LegacyIdScheme, RequirementIdPolicy
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.document_service import DocumentService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories
from proposal_agent.validation.deliverables import QaOutcome, check_xlsx

if TYPE_CHECKING:
    from proposal_agent.ingest.service import ExtractionService
    from proposal_agent.services.audit import AuditService

log = get_logger("changes.service")

GATE5_KEY = "gate5"
ATTACHMENT_MAX_CHARS = 6000
FILE_STEMS: dict[DeliverableKind, tuple[str, str]] = {
    DeliverableKind.REQUIREMENT_SPEC_XLSX: ("09_Excel_Deliverables", "Requirements_Definition"),
    DeliverableKind.TRACE_MATRIX_XLSX: ("09_Excel_Deliverables", "Traceability_Matrix"),
    DeliverableKind.WBS_GANTT_XLSX: ("06_WBS_Effort_Schedule", "WBS_Gantt"),
    DeliverableKind.STAFFING_PLAN_XLSX: ("06_WBS_Effort_Schedule", "Staffing_Plan"),
}
from proposal_agent.generators.excel.requirement_spec import CHANGE_LOG_HEADERS  # noqa: E402  (재노출)


@dataclass
class ApplyResult:
    request: ChangeRequest
    revision: Revision
    deliverables: list[Deliverable] = field(default_factory=list)
    new_ids: dict[str, str] = field(default_factory=dict)
    qa_errors: list[str] = field(default_factory=list)


class ChangeService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        settings: Settings,
        audit: AuditService,
        files: FileStore,
        steps: AgentStepService,
        baseline: BaselineService,
        documents: DocumentService,
        extraction: ExtractionService,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._files = files
        self._steps = steps
        self._baseline = baseline
        self._documents = documents
        self._extraction = extraction

    # --- 조회 ----------------------------------------------------------------------------------
    def list_requests(self, project: Project) -> list[ChangeRequest]:
        return self._repos.change_requests.find(project.id, order_by="created_at")

    def get(self, project: Project, cr_id: str) -> ChangeRequest:
        return self._repos.change_requests.get(cr_id, project.id)

    def active_requirements(self, project: Project) -> list[Requirement]:
        return [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
        ]

    def calendar(self) -> BusinessCalendar:
        return BusinessCalendar(parse_holidays(self._settings.holidays))

    def staffing_present(self, project: Project) -> bool:
        return bool(self._repos.staff_roles.find(project.id)) and any(
            d.kind == DocumentKind.STAFFING_PLAN for d in self._repos.documents.find(project.id)
        )

    def _require_baseline(self, project: Project) -> None:
        if not project.baseline_revision_id or not self._repos.requirements.find(project.id):
            raise ValidationError(
                "기준 데이터가 적재되지 않았습니다.",
                resolution="기존 산출물(요구사항 정의서·추적표·WBS)을 업로드하고 '기준 데이터 적재'를 먼저 실행하십시오.",
            )

    def period(self, project: Project) -> tuple[date | None, date | None]:
        if project.start_date and project.end_date:
            return project.start_date, project.end_date
        wbs = self._repos.wbs.tree(project.id)
        starts = [w.planned_start for w in wbs if w.planned_start]
        return (project.start_date or (min(starts) if starts else None), project.end_date)

    # --- 접수 ----------------------------------------------------------------------------------
    def create_request(
        self,
        project: Project,
        *,
        input_kind: InputKind,
        request_text: str,
        requester: str,
        reason: str,
        requested_on: date | None = None,
        selected_ids: list[str] | None = None,
        title: str = "",
        attachments: list[tuple[str, bytes]] | None = None,
        actor: str = "user",
    ) -> ChangeRequest:
        self._require_baseline(project)
        if not requester.strip():
            raise ValidationError("요청자를 입력하십시오.")
        selected = [s for s in (selected_ids or []) if s]
        text = request_text.strip()
        attachment_ids: list[str] = []
        excerpts: list[str] = []
        for name, data in attachments or []:
            doc = self._documents.register_upload(
                project, kind=DocumentKind.OTHER, file_name=name, data=data, actor=actor
            )
            attachment_ids.append(doc.id)
            outcome = self._extraction.extract_document(project, doc, actor=actor)
            blocks = [b.text for b in getattr(outcome, "blocks", []) if b.text.strip()]
            if not blocks:
                blocks = [
                    b.text
                    for b in self._extraction.current_blocks(project)
                    if b.source_document_id == doc.id and b.text.strip()
                ]
            joined = "\n".join(blocks)
            if not joined.strip():
                raise ValidationError(
                    f"첨부 문서 '{name}'에서 텍스트를 추출하지 못했습니다.",
                    resolution="텍스트가 있는 DOCX/PDF/TXT를 올리거나 요청 내용을 직접 입력하십시오.",
                )
            excerpts.append(f"[첨부 {name} 발췌]\n{joined[:ATTACHMENT_MAX_CHARS]}")
        if excerpts:
            text = (text + "\n" if text else "") + "\n".join(excerpts)
        if not text and not selected:
            raise ValidationError(
                "변경 내용을 입력하거나 요구사항을 선택하거나 문서를 첨부하십시오."
            )
        if input_kind in (InputKind.MODIFY_BUTTON, InputKind.DELETE_BUTTON) and not selected:
            raise ValidationError("수정·삭제 요청은 대상 요구사항을 선택해야 합니다.")
        existing = {r.id for r in self.active_requirements(project)}
        unknown = [s for s in selected if s not in existing]
        if unknown:
            raise ValidationError(f"존재하지 않는 요구사항 ID: {', '.join(unknown)}")
        number = self._repos.sequences.next(project.id, "cr")
        cr = ChangeRequest(
            id=f"CR-{number:03d}",
            project_id=project.id,
            title=title.strip()
            or (split_items(text)[0][:60] if text else f"{input_kind.value} {', '.join(selected)}"),
            input_kind=input_kind,
            request_text=text,
            requester=requester.strip(),
            requested_on=requested_on or date.today(),
            reason=reason.strip(),
            selected_requirement_ids=selected,
            attachment_document_ids=attachment_ids,
            created_by=actor,
            user_edits={
                "request_text": bool(request_text.strip()),
                "reason": bool(reason.strip()),
                "title": bool(title.strip()),
            },
        )
        self._repos.change_requests.insert(cr)
        self._audit.record(
            project.id,
            "change.requested",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={
                "input_kind": input_kind.value,
                "selected": selected,
                "attachments": attachment_ids,
            },
        )
        return cr

    def update_request(
        self, project: Project, cr: ChangeRequest, *, actor: str = "user", **fields: Any
    ) -> ChangeRequest:
        """사용자가 접수 내용을 직접 수정. 분석 결과는 무효화된다(재분석 필요)."""
        if cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED):
            raise ValidationError(
                f"{cr.id}는 승인·반영된 요청이라 수정할 수 없습니다.",
                resolution="새 변경 요청을 등록하십시오.",
            )
        for k, v in fields.items():
            if k in (
                "request_text",
                "reason",
                "requester",
                "requested_on",
                "title",
                "selected_requirement_ids",
            ):
                setattr(cr, k, v)
                cr.user_edits[k] = True
        cr.candidates, cr.impact, cr.status = [], None, ChangeStatus.REQUESTED
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.updated",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={"fields": list(fields)},
        )
        return cr

    # --- 분석 ----------------------------------------------------------------------------------
    def analyze(
        self, project: Project, cr: ChangeRequest, *, actor: str = "user", use_agent: bool = True
    ) -> ChangeRequest:
        self._require_baseline(project)
        if cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED):
            raise ValidationError(f"{cr.id}는 이미 승인·반영되었습니다.")
        existing = self.active_requirements(project)
        decisions = {c.id: (c.user_decision, c.user_override) for c in cr.candidates}
        candidates = classify_request(
            cr.request_text,
            existing,
            input_kind=cr.input_kind,
            selected_ids=cr.selected_requirement_ids,
        )
        for c in candidates:  # 재분석 시 사용자 결정은 유지
            if c.id in decisions:
                c.user_decision, c.user_override = decisions[c.id]
        cr.analysis_sources = ["rule"]
        cr.unresolved = []
        if use_agent:
            self._overlay_agent(project, cr, candidates, existing, actor)
        cr.candidates = candidates
        cr.impact = self.compute_impact(project, cr)
        cr.status = ChangeStatus.ANALYZED
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.analyzed",
            actor=actor,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={
                "candidates": [
                    (c.id, c.classification.value, c.requirement_id, c.source) for c in candidates
                ],
                "sources": cr.analysis_sources,
                "impact_error": cr.impact.error if cr.impact else None,
            },
        )
        return cr

    def _overlay_agent(
        self,
        project: Project,
        cr: ChangeRequest,
        candidates: list[ChangeCandidate],
        existing: list[Requirement],
        actor: str,
    ) -> None:
        items = split_items(cr.request_text)
        prompt = (
            f'<request requester="{cr.requester}" reason="{cr.reason}">\n'
            + "\n".join(f"[{i}] {t}" for i, t in enumerate(items, start=1))
            + "\n</request>\n<existing>\n"
            + "\n".join(f"{r.id} | {r.name} | {r.description[:200]}" for r in existing[:200])
            + "\n</existing>\n<rule_result>\n"
            + "\n".join(
                f"[{i}] {c.classification.value} {c.requirement_id or '-'} ({c.rationale[:120]})"
                for i, c in enumerate(candidates, start=1)
            )
            + "\n</rule_result>"
        )
        try:
            result = self._steps.run_role(
                project, "semantic_differ", prompt, actor=actor, include_prior=False
            )
        except (AgentRunError, PWAError) as exc:
            cr.unresolved.append(f"AI 의미 비교 생략 (규칙 결과만 사용): {exc}")
            return
        draft = result.output
        if not isinstance(draft, SemanticDiffDraft):
            cr.unresolved.append("AI 의미 비교 결과 형식 오류 — 규칙 결과만 사용")
            return
        cr.analysis_sources.append("ai")
        by_index = {i: c for i, c in enumerate(candidates, start=1)}
        valid_ids = {r.id for r in existing}
        for ai in draft.candidates:
            rid = ai.requirement_id if ai.requirement_id in valid_ids else None
            try:
                cls = CandidateClass(ai.classification)
            except ValueError:
                continue
            target = by_index.get(ai.item_index)
            note = (
                f"AI 의견: {cls.value}"
                + (f" ({rid})" if rid else "")
                + f" — {ai.rationale[:200]} (신뢰도 {ai.confidence:.2f})"
            )
            if target is None:
                candidates.append(
                    ChangeCandidate(
                        id=f"A{ai.item_index:02d}",
                        classification=CandidateClass.AMBIGUOUS,
                        requirement_id=rid,
                        related_ids=[x for x in ai.related_ids if x in valid_ids],
                        proposed_name=ai.proposed_name[:40],
                        proposed_description=ai.proposed_description,
                        rationale=note,
                        confidence=min(ai.confidence, 0.6),
                        needs_confirmation=True,
                        source="ai",
                        evidence=[ai.proposed_description],
                    )
                )
                continue
            # 문맥 비교 관점·난이도는 에이전트 판단을 우선 반영 (규칙 값은 근거에 남긴다)
            if ai.change_aspects:
                target.change_aspects = list(
                    dict.fromkeys([*target.change_aspects, *ai.change_aspects])
                )
            if ai.difficulty and Difficulty.from_label(ai.difficulty):
                prev = f"규칙 {target.difficulty}" if target.difficulty else "규칙 미산정"
                target.difficulty = Difficulty.from_label(ai.difficulty).label  # type: ignore[union-attr]
                target.difficulty_basis = f"AI: {ai.difficulty_basis or '근거 미기재'} ({prev})" + (
                    f"; 공수 힌트: {ai.effort_hint}" if ai.effort_hint else ""
                )
            elif ai.effort_hint:
                target.difficulty_basis += f"; 공수 힌트(AI): {ai.effort_hint}"
            if cls != target.classification or (rid and rid != target.requirement_id):
                target.rationale += " | " + note + " → 규칙과 불일치, 사용자 확인 필요"
                target.needs_confirmation = True
                if cls == CandidateClass.AMBIGUOUS or target.classification in (
                    CandidateClass.MODIFY,
                    CandidateClass.DELETE_REQUEST,
                ):
                    target.classification = (
                        CandidateClass.AMBIGUOUS
                    )  # 수정·삭제를 자동 결정하지 않는다
                target.source = "rule+ai"
            else:
                target.rationale += " | " + note + " (규칙과 일치)"
                target.confidence = round(
                    min(0.98, (target.confidence + ai.confidence) / 2 + 0.1), 2
                )
                target.source = "rule+ai"
            for x in ai.related_ids:
                if x in valid_ids and x not in target.related_ids:
                    target.related_ids.append(x)

    def compute_impact(self, project: Project, cr: ChangeRequest) -> ChangeImpact:
        start, end = self.period(project)
        return analyze_impact(
            cr.candidates,
            requirements=self.active_requirements(project),
            wbs=self._repos.wbs.tree(project.id),
            dependencies=self._repos.dependencies.find(project.id),
            roles=self._repos.staff_roles.find(project.id),
            staffing_plan_present=self.staffing_present(project),
            project_start=start,
            project_end=end,
            calendar=self.calendar(),
        )

    # --- 사용자 확인 -----------------------------------------------------------------------------
    def decide_candidate(
        self,
        project: Project,
        cr: ChangeRequest,
        candidate_id: str,
        *,
        decision: str | None,
        overrides: dict[str, Any] | None = None,
        classification: str | None = None,
        actor: str = "user",
    ) -> ChangeRequest:
        if cr.status in (ChangeStatus.APPROVED, ChangeStatus.APPLIED):
            raise ValidationError(f"{cr.id}는 이미 승인·반영되었습니다.")
        cand = next((c for c in cr.candidates if c.id == candidate_id), None)
        if cand is None:
            raise ValidationError(f"후보 {candidate_id}가 없습니다.")
        if decision not in (None, "accept", "reject"):
            raise ValidationError("결정은 accept/reject 중 하나여야 합니다.")
        if classification:
            new_cls = CandidateClass(classification)
            if new_cls == CandidateClass.AMBIGUOUS:
                raise ValidationError(
                    "AMBIGUOUS는 사용자가 확정할 수 있는 분류가 아닙니다. ADD/MODIFY/DELETE_REQUEST/NO_CHANGE 중 선택하십시오."
                )
            if new_cls in (
                CandidateClass.MODIFY,
                CandidateClass.DELETE_REQUEST,
                CandidateClass.NO_CHANGE,
            ) and not (overrides or {}).get("requirement_id", cand.requirement_id):
                raise ValidationError(f"{new_cls.value}는 대상 요구사항 ID가 필요합니다.")
            cand.user_override["classification"] = new_cls.value
            cand.classification = new_cls
            cand.source = "user"
        for k, v in (overrides or {}).items():
            if k == "requirement_id" and v and not self._repos.requirements.exists(v, project.id):
                raise ValidationError(f"존재하지 않는 요구사항 ID: {v}")
            cand.user_override[k] = v
            if k == "requirement_id":
                cand.requirement_id = v
            if k == "description":
                cand.proposed_description = str(v)
                if cand.after is not None:
                    cand.after["description"] = str(v)
            if k == "name":
                cand.proposed_name = str(v)
                if cand.after is not None:
                    cand.after["name"] = str(v)
        if decision == "accept" and cand.classification == CandidateClass.AMBIGUOUS:
            raise ValidationError(
                f"{cand.id}는 모호(AMBIGUOUS) 상태라 그대로 수락할 수 없습니다.",
                resolution="분류(추가/수정/삭제/변경 없음)와 대상 ID를 지정한 뒤 수락하십시오.",
            )
        cand.user_decision = decision
        if decision is not None:
            cand.needs_confirmation = False
        cr.impact = self.compute_impact(project, cr)
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.candidate_decided",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={
                "candidate": candidate_id,
                "decision": decision,
                "overrides": overrides or {},
                "classification": classification,
            },
        )
        return cr

    def approval_blockers(self, cr: ChangeRequest) -> list[str]:
        problems: list[str] = []
        if cr.status not in (ChangeStatus.ANALYZED,):
            problems.append(
                f"상태가 '{cr.status.value}'라 승인할 수 없습니다 (분석 완료 상태여야 함)."
            )
        accepted = cr.accepted_candidates
        if not accepted:
            problems.append("수락된 변경 후보가 없습니다. 후보별로 수락/거절을 결정하십시오.")
        for c in accepted:
            if c.classification == CandidateClass.AMBIGUOUS:
                problems.append(f"{c.id}: 모호 상태를 수락할 수 없습니다.")
            if (
                c.classification in (CandidateClass.MODIFY, CandidateClass.DELETE_REQUEST)
                and not c.requirement_id
            ):
                problems.append(f"{c.id}: 대상 요구사항 ID가 없습니다.")
        undecided = [
            c.id
            for c in cr.candidates
            if c.user_decision is None and c.classification != CandidateClass.NO_CHANGE
        ]
        if undecided:
            problems.append("미결정 후보: " + ", ".join(undecided))
        if cr.impact is None:
            problems.append("영향 분석이 없습니다.")
        elif cr.impact.error:
            problems.append("영향 분석 오류: " + cr.impact.error)
        return problems

    # --- 승인/반려 ------------------------------------------------------------------------------
    def approve(
        self,
        project: Project,
        cr: ChangeRequest,
        *,
        approver: str,
        comments: str,
        update_staffing: bool | None = None,
        actor: str | None = None,
    ) -> ApplyResult:
        problems = self.approval_blockers(cr)
        if problems:
            raise ValidationError(
                "승인 조건을 만족하지 않습니다.",
                cause="; ".join(problems),
                resolution="미결정 후보를 처리하고 영향 분석 오류를 해결한 뒤 다시 승인하십시오.",
            )
        if not approver.strip():
            raise ValidationError("승인자를 입력하십시오.")
        approval = Approval(
            project_id=project.id,
            target_type=ApprovalTarget.CHANGE_REQUEST,
            target_id=cr.id,
            decision=ApprovalDecision.APPROVED_WITH_COMMENTS
            if comments.strip()
            else ApprovalDecision.APPROVED,
            approver=approver,
            comments=comments,
            created_by=approver,
        )
        self._repos.approvals.insert(approval)
        cr.approval_id, cr.approver, cr.approved_at = approval.id, approver, utcnow()
        cr.status = ChangeStatus.APPROVED
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.approved",
            actor=approver,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={"approval": approval.id, "comments": comments},
        )
        return self.apply(project, cr, actor=actor or approver, update_staffing=update_staffing)

    def reject(
        self, project: Project, cr: ChangeRequest, *, approver: str, comments: str
    ) -> ChangeRequest:
        if cr.status in (ChangeStatus.APPLIED, ChangeStatus.APPROVED):
            raise ValidationError(f"{cr.id}는 이미 승인·반영되었습니다.")
        if not comments.strip():
            raise ValidationError("반려 사유를 입력하십시오.")
        approval = Approval(
            project_id=project.id,
            target_type=ApprovalTarget.CHANGE_REQUEST,
            target_id=cr.id,
            decision=ApprovalDecision.REJECTED,
            approver=approver,
            comments=comments,
            created_by=approver,
        )
        self._repos.approvals.insert(approval)
        cr.approval_id, cr.approver, cr.approved_at = approval.id, approver, utcnow()
        cr.status = ChangeStatus.REJECTED
        cr.result_summary = f"반려: {comments}"
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.rejected",
            actor=approver,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={"comments": comments},
        )
        return cr

    def withdraw(self, project: Project, cr: ChangeRequest, *, actor: str) -> ChangeRequest:
        if cr.status in (ChangeStatus.APPLIED, ChangeStatus.APPROVED):
            raise ValidationError(f"{cr.id}는 이미 승인·반영되었습니다.")
        cr.status = ChangeStatus.WITHDRAWN
        cr.touch()
        self._repos.change_requests.update(cr)
        self._audit.record(
            project.id,
            "change.withdrawn",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="ChangeRequest",
            entity_id=cr.id,
        )
        return cr

    # --- 반영 ----------------------------------------------------------------------------------
    def apply(
        self,
        project: Project,
        cr: ChangeRequest,
        *,
        actor: str,
        update_staffing: bool | None = None,
    ) -> ApplyResult:
        if cr.status not in (ChangeStatus.APPROVED, ChangeStatus.ERROR):
            raise ValidationError(f"{cr.id}는 승인 상태가 아닙니다 (현재 {cr.status.value}).")
        if cr.status == ChangeStatus.ERROR and not cr.approval_id:
            raise ValidationError(f"{cr.id}는 승인 기록이 없습니다.")
        staffing = self.staffing_present(project)
        include_staffing = staffing if update_staffing is None else update_staffing
        before_files = self._current_files(project)
        try:
            with self._repos.db.transaction():
                result = self._apply_baseline(project, cr, actor, include_staffing)
                cr.before_files = before_files
                cr.status = ChangeStatus.APPLIED
                cr.error = None
                cr.touch()
                self._repos.change_requests.update(cr)
            deliverables, qa_errors = self.regenerate(
                project, cr, result.revision, actor=actor, include_staffing=include_staffing
            )
            result.deliverables, result.qa_errors = deliverables, qa_errors
            cr.after_files = [d.file_path for d in deliverables]
            if not include_staffing:
                cr.unresolved.append(
                    "인력 투입계획은 갱신하지 않았습니다"
                    + (
                        " (업로드된 투입계획 없음 — 새 계획 작성 여부를 결정하십시오)."
                        if not staffing
                        else " (사용자 선택)."
                    )
                )
            cr.result_summary = self._summary(cr, result)
            cr.touch()
            self._repos.change_requests.update(cr)
        except Exception as exc:
            cr.status = ChangeStatus.ERROR
            cr.error = (
                exc.to_dict()
                if isinstance(exc, PWAError)
                else {"type": type(exc).__name__, "message": str(exc)}
            )
            cr.touch()
            self._repos.change_requests.update(cr)
            self._audit.record_error(
                project.id,
                "change.apply_failed",
                exc,
                actor=actor,
                entity_type="ChangeRequest",
                entity_id=cr.id,
            )
            raise
        self._audit.record(
            project.id,
            "change.applied",
            actor=actor,
            entity_type="ChangeRequest",
            entity_id=cr.id,
            payload={
                "revision": result.revision.id,
                "new_ids": result.new_ids,
                "files": cr.after_files,
                "qa_errors": result.qa_errors,
            },
        )
        return result

    def _current_files(self, project: Project) -> list[str]:
        latest: dict[DeliverableKind, Deliverable] = {}
        for d in self._repos.deliverables.find(project.id, order_by="created_at"):
            latest[d.kind] = d
        if latest:
            return [d.file_path for d in latest.values()]
        return [
            d.stored_path
            for d in self._repos.documents.find(project.id)
            if d.kind
            in (
                DocumentKind.REQUIREMENT_SPEC,
                DocumentKind.TRACE_MATRIX,
                DocumentKind.WBS,
                DocumentKind.STAFFING_PLAN,
            )
        ]

    def _id_policy(self, project: Project) -> RequirementIdPolicy:
        prefixes = {**self._settings.id_prefixes, **(project.settings.get("id_prefixes") or {})}
        return RequirementIdPolicy(self._repos.sequences, prefixes, self._settings.id_width)

    def _new_requirement_id(
        self, project: Project, req_type: RequirementType, existing_ids: list[str]
    ) -> str:
        policy = self._id_policy(project)
        prefix = policy.prefix_for(req_type)
        same_type = [i for i in existing_ids if i.upper().startswith(prefix.upper())]
        scheme = LegacyIdScheme.infer(same_type) or LegacyIdScheme.infer(existing_ids)
        if scheme:
            return policy.allocate_legacy(project.id, scheme, existing_ids)
        return policy.allocate(project.id, req_type)

    def _apply_baseline(
        self, project: Project, cr: ChangeRequest, actor: str, include_staffing: bool
    ) -> ApplyResult:
        parent_rev = self._repos.revisions.find(project.id, order_by="created_at")
        requirements = {r.id: r for r in self._repos.requirements.find(project.id)}
        new_ids: dict[str, str] = {}
        applied: list[str] = []
        stamp = utcnow().isoformat()
        for cand in cr.accepted_candidates:
            if cand.classification == CandidateClass.ADD:
                req_type = RequirementType(cand.user_override.get("type", cand.proposed_type))
                new_id = self._new_requirement_id(project, req_type, list(requirements))
                req = Requirement(
                    id=new_id,
                    project_id=project.id,
                    name=str(cand.user_override.get("name", cand.proposed_name)) or new_id,
                    description=str(
                        cand.user_override.get("description", cand.proposed_description)
                    ),
                    type=req_type,
                    status=RequirementStatus.CHANGED,
                    verification_status=VerificationStatus.UNVERIFIED,
                    review_status=ReviewStatus.APPROVED,
                    rationale=cand.rationale,
                    added_by=cr.requester,
                    added_on=cr.requested_on,
                    change_state="added",
                    change_summary=f"{cr.id} 추가 — {cr.reason or cr.title}",
                    difficulty=Difficulty.from_label(
                        str(cand.user_override.get("difficulty") or cand.difficulty or "")
                    ),
                    difficulty_basis=cand.difficulty_basis,
                    implementation_approach=(
                        f"- {cr.id} 추가 요구 — 구현 방안은 설계 단계에서 확정\n"
                        f"- [자동 초안] 변경 관점: {', '.join(aspect_labels(cand.change_aspects)) or '신규'}"
                    ),
                    approach_source="rule",
                    created_by=actor,
                )
                req.add_history(actor, "change.add", changes={"cr": cr.id}, note=cr.reason)
                self._repos.requirements.insert(req)
                requirements[new_id] = req
                new_ids[cand.id] = new_id
                cand.user_override["requirement_id"] = new_id
                applied.append(new_id)
            elif cand.classification == CandidateClass.MODIFY and cand.requirement_id:
                req = requirements[cand.requirement_id]
                before = {
                    "name": req.name,
                    "description": req.description,
                    "type": req.type.value,
                    "version": req.version,
                    "at": stamp,
                }
                req.previous_versions.append(before)
                new_desc = str(cand.user_override.get("description", cand.proposed_description))
                new_name = str(cand.user_override.get("name", req.name))
                req.add_history(
                    actor,
                    "change.modify",
                    changes={
                        "description": (req.description, new_desc),
                        "name": (req.name, new_name),
                        "cr": cr.id,
                    },
                    note=cr.reason,
                )
                req.description, req.name = new_desc, new_name
                req.status = RequirementStatus.CHANGED
                req.change_state = "modified"
                req.change_summary = f"{cr.id} 변경 — {cr.reason or cr.title}" + (
                    f" (관점: {', '.join(aspect_labels(cand.change_aspects))})"
                    if cand.change_aspects
                    else ""
                )
                new_level = Difficulty.from_label(
                    str(cand.user_override.get("difficulty") or cand.difficulty or "")
                )
                if new_level is not None:
                    req.difficulty = new_level
                    req.difficulty_basis = f"{cr.id}: {cand.difficulty_basis}"[:300]
                if req.implementation_approach and req.approach_source != "user":
                    req.review_notes = (
                        req.review_notes + "\n" if req.review_notes else ""
                    ) + f"@{cr.id} 변경 반영 — 구현 방안 재검토 필요"
                req.verification_status = VerificationStatus.NEEDS_REVISION
                req.touch()
                self._repos.requirements.update(req)
                self._mark_traces(project, req.id, f"{cr.id} 수정 — 화면·테스트 재검토")
                applied.append(req.id)
            elif cand.classification == CandidateClass.DELETE_REQUEST and cand.requirement_id:
                req = requirements[cand.requirement_id]
                req.previous_versions.append(
                    {
                        "name": req.name,
                        "description": req.description,
                        "type": req.type.value,
                        "version": req.version,
                        "at": stamp,
                    }
                )
                req.add_history(
                    actor, "change.delete_request", changes={"cr": cr.id}, note=cr.reason
                )
                req.status = RequirementStatus.CHANGED
                req.change_state = "deleted"
                req.change_summary = f"{cr.id} 삭제 — {cr.reason or cr.title} (기록 보존)"
                req.touch()
                self._repos.requirements.update(req)
                self._mark_traces(project, req.id, f"{cr.id} 삭제 요청 — 링크 유지, 재검토")
                applied.append(req.id)
        # WBS·일정 (코드 계산)
        self._apply_wbs(project, cr, new_ids, actor)
        if include_staffing:
            self._rebuild_allocations(project)
        revision = self._record_revision(project, cr, parent_rev[-1] if parent_rev else None, actor)
        cr.applied_requirement_ids = applied
        cr.revision_id = revision.id
        return ApplyResult(request=cr, revision=revision, new_ids=new_ids)

    def _mark_traces(self, project: Project, req_id: str, reason: str) -> None:
        for t in self._repos.traces.find(project.id, requirement_id=req_id):
            t.review_status = "재검토 필요"
            t.review_reason = reason
            t.touch()
            self._repos.traces.update(t)

    def _apply_wbs(
        self, project: Project, cr: ChangeRequest, new_ids: dict[str, str], actor: str
    ) -> None:
        for cand in cr.candidates:
            if cand.id in new_ids:
                cand.user_override["requirement_id"] = new_ids[cand.id]
        wbs = self._repos.wbs.tree(project.id)
        deps = self._repos.dependencies.find(project.id)
        start, end = self.period(project)
        impact, after, sched = simulate(
            cr.accepted_candidates,
            wbs=wbs,
            dependencies=deps,
            project_start=start,
            project_end=end,
            calendar=self.calendar(),
        )
        if impact.error or sched is None:
            raise ValidationError(
                "WBS 재계산 실패: " + (impact.error or "일정 없음"),
                resolution="WBS 의존 관계(순환·누락)를 수정한 뒤 다시 반영하십시오.",
            )
        by_code = {w.code: w for w in wbs}
        for code, t in after.tasks.items():
            if t.is_new:
                parent = by_code.get(t.parent_code) if t.parent_code else None
                depth = code.count(".") + 1
                item = WBSItem(
                    project_id=project.id,
                    code=code,
                    parent_id=parent.id if parent else None,
                    level=WBSLevel.PHASE
                    if depth == 1
                    else WBSLevel.ACTIVITY
                    if depth == 2
                    else WBSLevel.TASK,
                    name=t.name,
                    description=f"{cr.id}로 추가된 Task",
                    related_requirement_ids=t.requirement_ids,
                    role=t.role,
                    planned_start=sched.starts.get(code),
                    planned_end=sched.ends.get(code),
                    duration_days=t.duration,
                    effort_md=t.effort_md,
                    estimate_basis=next(
                        (ti.basis for ti in impact.tasks if ti.wbs_code == code),
                        "유사 Task 기준 추정",
                    ),
                    roles=[{"role": t.role, "ratio": "1"}] if t.role else [],
                    order=len(wbs) + 1,
                    notes=f"{cr.id} 신규",
                    auto_generated=True,
                    created_by=actor,
                )
                self._repos.wbs.insert(item)
                by_code[code] = item
                for rid in t.requirement_ids:
                    self._repos.traces.insert(
                        RequirementTrace(
                            project_id=project.id,
                            requirement_id=rid,
                            target_type=TraceTargetType.WBS_ITEM,
                            target_id=code,
                            note="wbs_code",
                            review_status="재검토 필요",
                            review_reason=f"{cr.id} 신규 Task — 화면·테스트 ID 미정",
                        )
                    )
                continue
            item = by_code[code]
            changed = False
            if t.removed:
                item.status = TaskStatus.ON_HOLD
                item.notes = (
                    item.notes + "; " if item.notes else ""
                ) + f"{cr.id} 삭제 요청으로 보류 (기록 보존)"
                changed = True
            else:
                if item.effort_md != t.effort_md:
                    item.estimate_basis = (
                        item.estimate_basis + "; " if item.estimate_basis else ""
                    ) + f"{cr.id}: {item.effort_md}→{t.effort_md} M/D"
                    item.effort_md = t.effort_md
                    item.duration_days = t.duration
                    changed = True
                ns, ne = sched.starts.get(code), sched.ends.get(code)
                if ns and ne and (item.planned_start != ns or item.planned_end != ne):
                    item.notes = (
                        item.notes + "; " if item.notes else ""
                    ) + f"{cr.id} 일정 재계산 {item.planned_start}~{item.planned_end}→{ns}~{ne}"
                    item.planned_start, item.planned_end = ns, ne
                    changed = True
            if changed:
                item.touch()
                self._repos.wbs.update(item)
        # 상위 항목 날짜·공수 롤업
        self._rollup(project)
        existing_pairs = {(d.predecessor_id, d.successor_id) for d in deps}
        for e in after.edges():
            p, s = by_code.get(e.predecessor), by_code.get(e.successor)
            if p and s and (p.id, s.id) not in existing_pairs:
                self._repos.dependencies.insert(
                    Dependency(
                        project_id=project.id,
                        predecessor_id=p.id,
                        successor_id=s.id,
                        type=e.type,
                        lag_days=e.lag_days,
                    )
                )
                existing_pairs.add((p.id, s.id))

    def _rollup(self, project: Project) -> None:
        items = self._repos.wbs.tree(project.id)
        children: dict[str, list[WBSItem]] = {}
        for w in items:
            if w.parent_id:
                children.setdefault(w.parent_id, []).append(w)
        by_id = {w.id: w for w in items}

        def visit(w: WBSItem) -> tuple[Decimal, date | None, date | None]:
            kids = children.get(w.id, [])
            if not kids:
                return (
                    (w.effort_md if w.status != TaskStatus.ON_HOLD else Decimal("0")),
                    w.planned_start,
                    w.planned_end,
                )
            total, s, e = Decimal("0"), None, None
            for k in kids:
                ke, ks, kend = visit(k)
                total += ke
                s = ks if s is None or (ks and ks < s) else s
                e = kend if e is None or (kend and kend > e) else e
            if (w.effort_md, w.planned_start, w.planned_end) != (total, s, e):
                w.effort_md, w.planned_start, w.planned_end = total, s, e
                w.touch()
                self._repos.wbs.update(w)
            return total, s, e

        for w in items:
            if w.parent_id is None or w.parent_id not in by_id:
                visit(w)

    def _rebuild_allocations(self, project: Project) -> None:
        """WBS leaf Task의 역할·공수·일정으로 월별 투입을 다시 만든다 (투입계획 갱신용)."""
        self._repos.allocations.clear_project(project.id)
        roles = {r.role_name: r for r in self._repos.staff_roles.find(project.id)}
        calendar = self.calendar()
        items = self._repos.wbs.tree(project.id)
        parents = {w.parent_id for w in items if w.parent_id}
        for w in items:
            if (
                w.id in parents
                or w.status == TaskStatus.ON_HOLD
                or w.effort_md <= 0
                or not (w.planned_start and w.planned_end)
            ):
                continue
            role_name = w.role or "(미지정)"
            role = roles.get(role_name)
            if role is None:
                role = StaffRole(
                    project_id=project.id,
                    role_name=role_name,
                    notes="변경 반영 시 추가된 역할 — 등급·단가 입력 필요",
                )
                self._repos.staff_roles.insert(role)
                roles[role_name] = role
            monthly = distribute_by_month(w.effort_md, w.planned_start, w.planned_end, calendar)
            self._repos.allocations.insert(
                StaffingAllocation(
                    project_id=project.id,
                    wbs_item_id=w.id,
                    staff_role_id=role.id,
                    start=w.planned_start,
                    end=w.planned_end,
                    effort_md=w.effort_md,
                    monthly_md={m: str(v) for m, v in monthly.items()},
                    estimate_basis=w.estimate_basis,
                )
            )

    def _record_revision(
        self, project: Project, cr: ChangeRequest, parent: Revision | None, actor: str
    ) -> Revision:
        snapshot = self._baseline.snapshot(project)
        snapshot["change_request"] = cr.model_dump(mode="json")
        name = self._files.next_version_name(
            project.output_dir, REVISION_SUBDIR, f"revision_{cr.id}", ".json"
        )
        stored = self._files.save_bytes(
            project.output_dir,
            REVISION_SUBDIR,
            name,
            json.dumps(snapshot, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
        )
        count = len(self._repos.revisions.find(project.id))
        rev = Revision(
            project_id=project.id,
            number=f"v{count + 1}.0",
            label=f"{cr.id} 반영",
            reason=cr.reason or cr.title,
            change_ids=[cr.id],
            snapshot_path=stored.relative_path,
            approval_id=cr.approval_id,
            parent_revision_id=parent.id if parent else None,
            created_by=actor,
        )
        self._repos.revisions.insert(rev)
        return rev

    # --- 문서 재생성 ----------------------------------------------------------------------------
    def build_context(self, project: Project, version: str) -> GenerationContext:
        requirements = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
        ]
        wbs = self._repos.wbs.tree(project.id)
        start, end = self.period(project)
        ends = [w.planned_end for w in wbs if w.planned_end]
        end = end or (max(ends) if ends else None)
        ctx = GenerationContext(
            project=project,
            requirements=requirements,
            wbs=wbs,
            dependencies=self._repos.dependencies.find(project.id),
            roles=self._repos.staff_roles.find(project.id),
            allocations=self._repos.allocations.find(project.id),
            period_start=start,
            period_end=end,
            version=version,
        )
        ctx.change_log = self.change_log_rows(project)
        return ctx

    def change_log_rows(self, project: Project) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for cr in self.list_requests(project):
            files = ", ".join(cr.after_files) if cr.after_files else ""
            imp = cr.impact
            for c in cr.candidates:
                if c.classification == CandidateClass.NO_CHANGE:
                    continue
                rows.append(
                    [
                        cr.id,
                        c.classification.value,
                        cr.requester,
                        cr.requested_on,
                        cr.reason,
                        c.requirement_id or c.user_override.get("requirement_id", ""),
                        json.dumps(c.before, ensure_ascii=False) if c.before else "",
                        json.dumps(c.after, ensure_ascii=False) if c.after else "",
                        c.rationale,
                        ", ".join(aspect_labels(c.change_aspects)),
                        (
                            f"{c.user_override.get('difficulty') or c.difficulty or ''}"
                            + (f" — {c.difficulty_basis[:80]}" if c.difficulty_basis else "")
                        ).strip(),
                        cr.status.value,
                        cr.approver or "",
                        cr.approved_at.date() if cr.approved_at else None,
                        files,
                        (
                            f"{imp.schedule_delta_days}영업일"
                            + (" (과제 종료 초과)" if imp.project_end_exceeded else "")
                        )
                        if imp
                        else "",
                        f"+{imp.effort.added_md} / -{imp.effort.reduced_md} = {imp.effort.net_md} M/D ({imp.effort.estimate_status})"
                        if imp
                        else "",
                        (
                            str(imp.cost_delta)
                            if imp and imp.cost_delta is not None
                            else "단가 미입력"
                        )
                        if imp
                        else "",
                        cr.result_summary or ("거절" if c.user_decision == "reject" else ""),
                    ]
                )
        return rows

    def regenerate(
        self,
        project: Project,
        cr: ChangeRequest,
        revision: Revision,
        *,
        actor: str,
        include_staffing: bool,
    ) -> tuple[list[Deliverable], list[str]]:
        ctx = self.build_context(project, revision.number)
        stamp = datetime.now().strftime("%Y%m%d%H%M")
        builders: list[tuple[DeliverableKind, Any]] = [
            (DeliverableKind.REQUIREMENT_SPEC_XLSX, lambda: build_requirement_spec(ctx)),
            (
                DeliverableKind.TRACE_MATRIX_XLSX,
                lambda: build_trace_matrix(
                    ctx,
                    self._repos.traces.find(project.id),
                    self._repos.screens.find(project.id),
                    self._repos.unit_tests.find(project.id),
                    self._repos.integration_tests.find(project.id),
                ),
            ),
            (DeliverableKind.WBS_GANTT_XLSX, lambda: build_wbs_gantt(ctx)),
        ]
        if include_staffing:
            builders.append((DeliverableKind.STAFFING_PLAN_XLSX, lambda: build_staffing_plan(ctx)))
        out: list[Deliverable] = []
        qa_errors: list[str] = []
        for kind, make in builders:
            subdir, stem = FILE_STEMS[kind]
            stored = self._files.store_unique(
                project.output_dir, subdir, f"{stem}_{stamp}.xlsx", make()
            )
            outcome = QaOutcome()
            check_xlsx(stored.path, kind, outcome, ctx)
            errors = [f.message for f in outcome.findings if f.level.value == "error"]
            qa_errors.extend(f"{stored.path.name}: {e}" for e in errors)
            d = Deliverable(
                project_id=project.id,
                revision_id=revision.id,
                kind=kind,
                file_path=stored.relative_path,
                version=revision.number,
                sha256=stored.sha256,
                generated_from_snapshot=revision.snapshot_path,
                integrity_status=IntegrityStatus.PASSED
                if outcome.opened.get(kind.value, True) and not errors
                else IntegrityStatus.FAILED,
                qa_status=QaStatus.PASSED if not errors else QaStatus.FAILED,
                created_by=actor,
            )
            self._repos.deliverables.insert(d)
            out.append(d)
        return out, qa_errors

    def _summary(self, cr: ChangeRequest, result: ApplyResult) -> str:
        parts = [f"반영 완료 (Revision {result.revision.number})"]
        if result.new_ids:
            parts.append("신규 ID: " + ", ".join(f"{k}→{v}" for k, v in result.new_ids.items()))
        if cr.impact:
            parts.append(
                f"일정 {cr.impact.schedule_delta_days:+d}영업일, 공수 {cr.impact.effort.net_md:+} M/D, 인력 시나리오 {cr.impact.staffing_scenario.value}"
            )
        parts.append(f"문서 {len(result.deliverables)}건 생성")
        if result.qa_errors:
            parts.append(f"QA 오류 {len(result.qa_errors)}건")
        return "; ".join(parts)


__all__ = ["ApplyResult", "ChangeService", "GATE5_KEY", "CHANGE_LOG_HEADERS", "SimPlan"]
