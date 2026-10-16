"""회의록·인터뷰·질의응답 구조화 + 결정·미결·조치 항목 + 기술 협상 → 기준선 반영 통제 (지시문 §10·§11, 단계 5).

원칙
- 회의에서 논의되었다는 사실만으로 승인으로 보지 않는다. ``Decision`` 은 에이전트·규칙이 **제안** 으로 만들고, 사람이 확정한다.
- **결정 권한이 확인되지 않은 결정은 승인할 수 없다**(``authority_confirmed`` 필수). 승인된 공식 결정(``is_binding``)과
  고객 합의·승인된 협상(``can_apply_to_baseline``)만 변경 요청으로 전환해 기준선에 반영할 수 있다. 전환해도 변경 관리의
  분석 → 후보 확정 → 승인 → 반영 절차를 그대로 거친다(자동 반영 없음).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from proposal_agent.agents.schemas import MeetingNoteReport
from proposal_agent.config.errors import AgentRunError, PWAError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import (
    ActorKind,
    Decision,
    DecisionKind,
    DecisionStatus,
    DocumentKind,
    Negotiation,
    NegotiationStatus,
    Project,
    SourceDocument,
    utcnow,
)
from proposal_agent.models.change import ChangeRequest, InputKind
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.repositories import Repositories

log = get_logger(__name__)

ROLE_MEETING_ANALYZER = "meeting_analyzer"

# 규칙 추출: 줄 머리 표지 → 항목 종류
_KIND_MARKERS: tuple[tuple[tuple[str, ...], DecisionKind], ...] = (
    (("[결정]", "결정:", "합의:", "확정:", "결정사항", "합의사항"), DecisionKind.OFFICIAL_DECISION),
    (("[요청]", "요청:", "고객 요청", "요구:"), DecisionKind.CUSTOMER_REQUEST),
    (
        ("[미결]", "미결:", "질문:", "확인 필요", "미확정", "검토 필요:", "[질문]"),
        DecisionKind.OPEN_QUESTION,
    ),
    (("[조치]", "조치:", "action:", "todo:", "액션:", "[AI]", "to-do"), DecisionKind.ACTION_ITEM),
    (("[위험]", "위험:", "이슈:", "리스크:", "[이슈]"), DecisionKind.RISK_ISSUE),
    (("[의견]", "의견:", "내부 의견", "제안:"), DecisionKind.INTERNAL_OPINION),
)
_REQ_ID_RE = re.compile(r"\b([A-Z]{2,4}-\d{3})\b")
_DUE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_OWNER_RE = re.compile(r"(?:담당|owner|책임)\s*[:：]\s*([^\s,;)]+)", re.IGNORECASE)


def _title_key(title: str) -> str:
    """제목 비교 키: 괄호 안·공백·구두점을 지운 앞 24자."""
    t = re.sub(r"\([^)]*\)", "", str(title))
    return re.sub(r"[\s\W_]+", "", t).casefold()[:24]


def extract_meeting_items(text: str) -> list[dict[str, Any]]:
    """회의록 텍스트에서 표지(결정/요청/미결/조치/위험/의견)가 붙은 줄을 항목으로 뽑는다 (규칙, 에이전트 보강 전)."""
    items: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-•*·○■□▶▷ ").strip()
        if len(line) < 4:
            continue
        low = line.casefold()
        kind: DecisionKind | None = None
        for markers, k in _KIND_MARKERS:
            if any(low.startswith(m.casefold()) for m in markers):
                kind = k
                break
        if kind is None:
            continue
        body = line
        for markers, _ in _KIND_MARKERS:
            for m in markers:
                if body.casefold().startswith(m.casefold()):
                    body = body[len(m) :].strip(" :：-")
        due = None
        m_due = _DUE_RE.search(body)
        if m_due:
            try:
                due = date(int(m_due.group(1)), int(m_due.group(2)), int(m_due.group(3)))
            except ValueError:
                due = None
        m_owner = _OWNER_RE.search(body)
        items.append(
            {
                "kind": kind,
                "title": body[:60],
                "content": body,
                "owner": m_owner.group(1) if m_owner else "",
                "due_date": due,
                "related_requirement_ids": sorted(set(_REQ_ID_RE.findall(body))),
                "evidence": raw.strip(),
            }
        )
    return items


class DecisionService:
    def __init__(
        self,
        repos: Repositories,
        audit: AuditService,
        steps: AgentStepService,
        *,
        extraction: Any = None,
        paths: Any = None,
    ) -> None:
        self._repos = repos
        self._audit = audit
        self._steps = steps
        self._extraction = extraction
        self._paths = paths

    # --- 조회 ------------------------------------------------------------------------------------
    def decisions(self, project: Project) -> list[Decision]:
        return self._repos.decisions.find(project.id, order_by="code")

    def negotiations(self, project: Project) -> list[Negotiation]:
        return self._repos.negotiations.find(project.id, order_by="code")

    def open_items(self, project: Project) -> list[Decision]:
        """미결 질문·조치 항목 중 아직 해결되지 않은 것."""
        return [
            d
            for d in self.decisions(project)
            if d.kind in (DecisionKind.OPEN_QUESTION, DecisionKind.ACTION_ITEM)
            and d.status not in (DecisionStatus.RESOLVED, DecisionStatus.REJECTED)
        ]

    def overdue_items(self, project: Project, today: date | None = None) -> list[Decision]:
        t = today or date.today()
        return [d for d in self.open_items(project) if d.due_date and d.due_date < t]

    # --- 회의록 구조화 ----------------------------------------------------------------------------
    def meeting_text(self, project: Project, document: SourceDocument) -> str:
        if self._extraction is None:
            raise ValidationError("문서 추출 서비스가 없어 회의록 텍스트를 읽을 수 없습니다.")
        blocks = [
            b.text
            for b in self._extraction.current_blocks(project)
            if b.source_document_id == document.id and b.text.strip()
        ]
        if not blocks:
            outcome = self._extraction.extract_document(project, document, actor="system")
            blocks = [b.text for b in getattr(outcome, "blocks", []) if b.text.strip()]
        text = "\n".join(blocks).strip()
        if not text:
            raise ValidationError(
                f"회의록 '{document.file_name}'에서 텍스트를 추출하지 못했습니다.",
                resolution="텍스트가 있는 DOCX/PDF/TXT/PPTX 를 올리거나 OCR 가능한 이미지를 쓰십시오.",
            )
        return text

    def structure_meeting(
        self,
        project: Project,
        document: SourceDocument,
        *,
        actor: str = "user",
        use_agent: bool = True,
        text: str | None = None,
    ) -> tuple[list[Decision], list[str]]:
        """회의록 문서 → 결정·요청·미결·조치·위험·의견 항목(Decision, 전부 '제안' 상태). (생성 항목, 경고) 를 돌려준다."""
        if document.kind != DocumentKind.MEETING_NOTE:
            raise ValidationError(
                f"'{document.file_name}'은(는) 회의록 문서가 아닙니다 ({document.kind.value}).",
                resolution="문서 종류를 '회의록·인터뷰·질의응답'으로 등록하십시오.",
            )
        body = text if text is not None else self.meeting_text(project, document)
        warnings: list[str] = []
        items = extract_meeting_items(body)
        sources = ["rule"]
        if use_agent:
            agent_items, warn = self._agent_items(project, document, body, items, actor)
            warnings.extend(warn)
            if agent_items:
                items = self._merge(items, agent_items)
                sources.append("ai")
        if not items:
            warnings.append(
                "구조화된 항목이 없습니다 — 회의록에 '결정:/요청:/미결:/조치:' 표지를 붙이거나 에이전트를 사용하십시오."
            )
        existing_ids = {r.id for r in self._repos.requirements.find(project.id)}
        created: list[Decision] = []
        for it in items:
            rel = [x for x in it.get("related_requirement_ids", []) if x in existing_ids]
            unknown = [x for x in it.get("related_requirement_ids", []) if x not in existing_ids]
            if unknown:
                warnings.append(
                    f"'{it['title'][:30]}': 존재하지 않는 요구사항 ID {', '.join(unknown)} 무시"
                )
            d = Decision(
                project_id=project.id,
                code=self._repos.next_code(project.id, "DEC"),
                title=str(it["title"])[:80] or "(제목 없음)",
                kind=it["kind"],
                status=DecisionStatus.PROPOSED,
                content=str(it.get("content", ""))[:2000],
                rationale=str(it.get("rationale", ""))[:500],
                source_document_id=document.id,
                source_excerpt=str(it.get("evidence", ""))[:500],
                recorded_on=date.today(),
                owner=str(it.get("owner", ""))[:40],
                due_date=it.get("due_date"),
                authority_confirmed=False,  # 회의록만으로는 권한을 확인할 수 없다
                related_requirement_ids=rel,
                action_items=list(it.get("action_items", []))[:10],
                created_by=actor,
            )
            self._repos.decisions.insert(d)
            created.append(d)
        self._audit.record(
            project.id,
            "decision.structured",
            actor=actor,
            entity_type="SourceDocument",
            entity_id=document.id,
            payload={"count": len(created), "sources": sources, "codes": [d.code for d in created]},
        )
        return created, warnings

    def _agent_items(
        self,
        project: Project,
        document: SourceDocument,
        body: str,
        rule_items: list[dict[str, Any]],
        actor: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        prompt = (
            f'<meeting_note file="{document.file_name}">\n{body[:12000]}\n</meeting_note>\n<rule_items>\n'
            + json.dumps(
                [
                    {"kind": it["kind"].value, "title": it["title"], "owner": it["owner"]}
                    for it in rule_items
                ],
                ensure_ascii=False,
            )
            + "\n</rule_items>\n\n회의록을 결정·고객 요청·내부 의견·미결 질문·조치 항목·위험으로 구조화해 JSON 으로 반환하라. "
            "논의된 사실과 결정을 구분하고, 결정 권한자가 명시되지 않으면 authority_hint 를 비워라. 수치·날짜를 만들지 말라."
        )
        try:
            result = self._steps.run_role(
                project, ROLE_MEETING_ANALYZER, prompt, actor=actor, include_prior=False
            )
        except (AgentRunError, PWAError) as exc:
            return [], [f"에이전트 구조화 생략 (규칙 결과만 사용): {exc}"]
        draft = result.output
        if not isinstance(draft, MeetingNoteReport):
            try:
                draft = MeetingNoteReport.model_validate(draft)
            except Exception:  # noqa: BLE001
                return [], ["에이전트 결과 형식 오류 — 규칙 결과만 사용"]
        out: list[dict[str, Any]] = []
        for it in draft.items:
            try:
                kind = DecisionKind(it.kind)
            except ValueError:
                continue
            due = None
            if it.due_date:
                try:
                    due = datetime.strptime(it.due_date, "%Y-%m-%d").date()
                except ValueError:
                    due = None
            out.append(
                {
                    "kind": kind,
                    "title": it.title,
                    "content": it.content,
                    "rationale": it.rationale,
                    "owner": it.owner,
                    "due_date": due,
                    "related_requirement_ids": list(it.related_requirement_ids),
                    "evidence": it.evidence,
                    "action_items": list(it.action_items),
                }
            )
        warnings = [f"에이전트 미해결: {u}" for u in draft.unresolved[:5]]
        return out, warnings

    @staticmethod
    def _merge(
        rule_items: list[dict[str, Any]], agent_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """같은 제목(앞 20자)이면 에이전트 항목이 규칙 항목을 보강하고, 나머지는 합친다."""
        merged = list(agent_items)
        keys = [_title_key(a["title"]) for a in agent_items]
        ev_keys = [_title_key(a.get("evidence", ""))[:30] for a in agent_items]

        def same(rk: str, ek: str) -> bool:
            if rk and any(k and (k.startswith(rk) or rk.startswith(k)) for k in keys):
                return True
            return (
                bool(ek)
                and len(ek) >= 10
                and any(e and (e.startswith(ek) or ek.startswith(e)) for e in ev_keys)
            )

        for r in rule_items:
            if not same(_title_key(r["title"]), _title_key(r.get("evidence", ""))[:30]):
                merged.append(r)
        return merged

    # --- 결정 확정 ------------------------------------------------------------------------------
    def _get_decision(self, project: Project, decision_id: str) -> Decision:
        d = self._repos.decisions.get(decision_id, project.id)
        return d

    def confirm_decision(
        self,
        project: Project,
        decision_id: str,
        *,
        status: DecisionStatus,
        approver: str,
        authority_confirmed: bool,
        comments: str = "",
        kind: DecisionKind | None = None,
        actor: str | None = None,
    ) -> Decision:
        """사람이 항목을 확정한다. 승인(APPROVED) 은 결정 권한이 확인된 공식 결정에만 허용한다."""
        d = self._get_decision(project, decision_id)
        if kind is not None:
            d.kind = kind
        if status == DecisionStatus.APPROVED:
            if d.kind != DecisionKind.OFFICIAL_DECISION:
                raise ValidationError(
                    f"{d.code}: '{d.kind.value}' 항목은 승인 대상이 아닙니다 (공식 결정만 승인).",
                    resolution="종류를 '공식 결정'으로 바꾸거나 해결/보류로 처리하십시오.",
                )
            if not authority_confirmed:
                raise ValidationError(
                    f"{d.code}: 결정 권한이 확인되지 않아 승인할 수 없습니다 (지시문 §10.2).",
                    resolution="결정 권한자(고객 PM·사업 책임자 등)를 확인한 뒤 '권한 확인'을 체크하십시오.",
                )
            if not approver.strip():
                raise ValidationError("승인자를 입력하십시오.")
            d.authority_confirmed = True
            d.approved_by = approver.strip()
            d.approved_at = utcnow()
        d.status = status
        if comments:
            d.rationale = (d.rationale + "\n" if d.rationale else "") + comments[:500]
        d.version += 1
        d.touch()
        self._repos.decisions.update(d)
        self._audit.record(
            project.id,
            "decision.confirmed",
            actor=actor or approver,
            actor_kind=ActorKind.USER,
            entity_type="Decision",
            entity_id=d.id,
            payload={
                "status": status.value,
                "authority": authority_confirmed,
                "kind": d.kind.value,
            },
        )
        return d

    def decision_to_change_request(
        self, project: Project, decision_id: str, *, changes: Any, actor: str = "user"
    ) -> ChangeRequest:
        """승인된 공식 결정(is_binding)만 변경 요청으로 전환한다. 반영은 변경 관리 절차를 따른다."""
        d = self._get_decision(project, decision_id)
        if not d.is_binding:
            raise ValidationError(
                f"{d.code}: 승인된 공식 결정(권한 확인·승인자)만 변경 요청으로 전환할 수 있습니다.",
                resolution="결정을 확정(승인)한 뒤 전환하십시오.",
            )
        cr = changes.create_request(
            project,
            input_kind=InputKind.NATURAL_LANGUAGE,
            request_text=d.content or d.title,
            requester=d.approved_by or actor,
            reason=f"{d.code} {d.title}"[:200],
            selected_ids=list(d.related_requirement_ids),
            title=f"{d.code}: {d.title}"[:60],
            actor=actor,
        )
        cr.decision_ids = [d.id]
        cr.touch()
        self._repos.change_requests.update(cr)
        d.related_change_request_ids.append(cr.id)
        d.touch()
        self._repos.decisions.update(d)
        return cr

    # --- 기술 협상·계약 변경 ----------------------------------------------------------------------
    def create_negotiation(
        self,
        project: Project,
        *,
        title: str,
        before: str,
        after: str,
        reason: str,
        contract_impact: str = "",
        schedule_impact: str = "",
        cost_effort_impact: str = "",
        related_requirement_ids: list[str] | None = None,
        related_decision_ids: list[str] | None = None,
        actor: str = "user",
    ) -> Negotiation:
        if not title.strip() or not after.strip():
            raise ValidationError("협상 항목에는 제목과 변경 후 내용이 필요합니다.")
        existing = {r.id for r in self._repos.requirements.find(project.id)}
        unknown = [x for x in related_requirement_ids or [] if x not in existing]
        if unknown:
            raise ValidationError(f"존재하지 않는 요구사항 ID: {', '.join(unknown)}")
        n = Negotiation(
            project_id=project.id,
            code=self._repos.next_code(project.id, "NEG"),
            title=title.strip()[:120],
            before=before.strip(),
            after=after.strip(),
            reason=reason.strip(),
            contract_impact=contract_impact.strip(),
            schedule_impact=schedule_impact.strip(),
            cost_effort_impact=cost_effort_impact.strip(),
            related_requirement_ids=list(related_requirement_ids or []),
            related_decision_ids=list(related_decision_ids or []),
            created_by=actor,
        )
        self._repos.negotiations.insert(n)
        self._audit.record(
            project.id,
            "negotiation.created",
            actor=actor,
            entity_type="Negotiation",
            entity_id=n.id,
        )
        return n

    def settle_negotiation(
        self,
        project: Project,
        negotiation_id: str,
        *,
        status: NegotiationStatus,
        customer_agreed: bool | None,
        approver: str,
        actor: str | None = None,
    ) -> Negotiation:
        """합의(AGREED) 는 고객 합의가 확인되고 승인자가 있을 때만. APPLIED 는 변경 반영 시 코드가 설정한다."""
        n = self._repos.negotiations.get(negotiation_id, project.id)
        if status == NegotiationStatus.APPLIED:
            raise ValidationError("'반영' 상태는 변경 요청이 기준선에 반영될 때 코드가 설정합니다.")
        if status == NegotiationStatus.AGREED:
            if customer_agreed is not True:
                raise ValidationError(
                    f"{n.code}: 고객 합의가 확인되지 않아 합의 처리할 수 없습니다.",
                    resolution="고객 합의(공문·회의록 승인)를 확인한 뒤 처리하십시오.",
                )
            if not approver.strip():
                raise ValidationError("승인자를 입력하십시오.")
            n.approved_by = approver.strip()
            n.approved_at = utcnow()
        n.customer_agreed = customer_agreed
        n.status = status
        n.version += 1
        n.touch()
        self._repos.negotiations.update(n)
        self._audit.record(
            project.id,
            "negotiation.settled",
            actor=actor or approver,
            actor_kind=ActorKind.USER,
            entity_type="Negotiation",
            entity_id=n.id,
            payload={"status": status.value, "customer_agreed": customer_agreed},
        )
        return n

    def negotiation_to_change_request(
        self, project: Project, negotiation_id: str, *, changes: Any, actor: str = "user"
    ) -> ChangeRequest:
        """고객 합의·승인된 협상만 변경 요청으로 전환한다 (기준선 자동 반영 없음)."""
        n = self._repos.negotiations.get(negotiation_id, project.id)
        if not n.can_apply_to_baseline:
            raise ValidationError(
                f"{n.code}: 고객 합의·승인된 협상만 기준선 반영(변경 요청)으로 전환할 수 있습니다.",
                resolution="협상을 '합의' 상태로 확정(고객 합의 확인·승인자)한 뒤 전환하십시오.",
            )
        cr = changes.create_request(
            project,
            input_kind=InputKind.NATURAL_LANGUAGE,
            request_text=n.after,
            requester=n.approved_by or actor,
            reason=f"{n.code} {n.title} — {n.reason}"[:200],
            selected_ids=list(n.related_requirement_ids),
            title=f"{n.code}: {n.title}"[:60],
            actor=actor,
        )
        cr.negotiation_id = n.id
        cr.touch()
        self._repos.change_requests.update(cr)
        return cr

    def mark_negotiation_applied(self, project: Project, cr: ChangeRequest) -> None:
        """변경 요청이 기준선에 반영되면 연결된 협상을 '반영' 으로 바꾼다 (ChangeService.apply 가 호출)."""
        if not cr.negotiation_id:
            return
        try:
            n = self._repos.negotiations.get(cr.negotiation_id, project.id)
        except PWAError:
            return
        n.status = NegotiationStatus.APPLIED
        n.touch()
        self._repos.negotiations.update(n)

    # --- 보고 --------------------------------------------------------------------------------------
    def render_markdown(self, project: Project) -> str:
        lines = [f"# 결정·미결·조치·협상 현황 — {project.name}", ""]
        lines.append("| ID | 종류 | 제목 | 상태 | 권한 확인 | 담당 | 기한 | 관련 요구 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for d in self.decisions(project):
            lines.append(
                f"| {d.code} | {d.kind.value} | {d.title} | {d.status.value} | {'Y' if d.authority_confirmed else 'N'} | {d.owner} | {d.due_date or ''} | {', '.join(d.related_requirement_ids)} |"
            )
        lines += [
            "",
            "## 기술 협상·계약 변경",
            "",
            "| ID | 제목 | 상태 | 고객 합의 | 승인자 | 영향(계약/일정/비용) |",
            "|---|---|---|---|---|---|",
        ]
        for n in self.negotiations(project):
            lines.append(
                f"| {n.code} | {n.title} | {n.status.value} | {n.customer_agreed if n.customer_agreed is not None else '미확인'} | {n.approved_by} | {n.contract_impact} / {n.schedule_impact} / {n.cost_effort_impact} |"
            )
        return "\n".join(lines) + "\n"


__all__ = ["ROLE_MEETING_ANALYZER", "DecisionService", "extract_meeting_items"]
