"""기술 조사 서비스 (Phase 3).

- 조사 주제는 코드가 결정적으로 식별한다 (RFP 명시 솔루션, 제약사항의 프레임워크·표준, 비기능의 보안·성능·호환성, 제품명 토큰).
- 조사 자체는 ``tech_researcher`` 역할(WebSearch/WebFetch)이 수행하고, 코드가 출처를 도메인 규칙으로 재분류하며
  출처 없는 사실은 미확인으로 강등한다. 결과는 ``TechnologyResearch``·``FeasibilityStudy``로 저장한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.control import CancellationToken
from proposal_agent.agents.schemas import ResearchReport
from proposal_agent.config.logging import get_logger
from proposal_agent.models import (
    FeasibilityComparisonRecord,
    FeasibilityStudy,
    FeasibilityVerdict,
    Project,
    Requirement,
    RequirementStatus,
    RequirementType,
    ResearchSource,
    SourceTrust,
    TechAlternativeRecord,
    TechnologyResearch,
)
from proposal_agent.research.sources import classify_url, effective_trust
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.agent_step_service import AgentStepService

log = get_logger("research.service")

COMPARISON_CRITERIA: tuple[str, ...] = (
    "rfp_fit",
    "feasibility",
    "performance",
    "security",
    "compatibility",
    "license_cost",
    "operations",
    "staffing",
    "support_longevity",
)
COMPARISON_AREAS: tuple[str, ...] = (
    "framework",
    "ui_ux",
    "web_was",
    "db",
    "api",
    "security",
    "deploy_ops",
)

_SECURITY_PERF = re.compile(
    r"보안|암호|성능|응답|동시|가용|이중화|호환|브라우저|접근성|백업|복구|TPS|부하", re.IGNORECASE
)
_FRAMEWORK = re.compile(
    r"프레임워크|표준|WAS|WEB|DBMS|DB|API|연계|인터페이스|플랫폼|클라우드|컨테이너", re.IGNORECASE
)
_PRODUCT_TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9.+#-]{2,}(?:\s[A-Z][A-Za-z0-9.+#-]{1,})?\b")
_PRODUCT_STOP = {
    "RFP",
    "SSO",
    "SMS",
    "PDF",
    "Excel",
    "SLA",
    "ISMS",
    "API",
    "URL",
    "HTTP",
    "HTTPS",
    "KPI",
    "UI",
    "UX",
    "IT",
    "SI",
}


@dataclass
class ResearchTopic:
    topic: str
    requirement_ids: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ResearchRunResult:
    items: list[TechnologyResearch]
    study: FeasibilityStudy | None
    cost_usd: float
    topics: list[ResearchTopic]
    unverified_count: int


class ResearchService:
    def __init__(self, repos: Repositories, steps: AgentStepService) -> None:
        self._repos = repos
        self._steps = steps

    # --- 주제 식별 (결정적) -----------------------------------------------------------------
    def identify_topics(
        self, project: Project, analysis: dict[str, Any] | None = None
    ) -> list[ResearchTopic]:
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
        ]
        topics: dict[str, ResearchTopic] = {}

        def add(topic: str, req: Requirement | None, reason: str) -> None:
            key = topic.strip()
            if not key:
                return
            t = topics.setdefault(key, ResearchTopic(topic=key, reason=reason))
            if req and req.id not in t.requirement_ids:
                t.requirement_ids.append(req.id)

        for name in (analysis or {}).get("named_solutions", []) or []:
            add(f"명시 솔루션: {name}", None, "RFP에 명시된 제품·솔루션")
        for target in (analysis or {}).get("integration_targets", []) or []:
            add(f"연계 대상 인터페이스: {target}", None, "연계 대상 시스템의 API·개발 가이드 확인")
        for r in reqs:
            text = f"{r.name} {r.description}"
            for m in _PRODUCT_TOKEN.findall(text):
                if (
                    m not in _PRODUCT_STOP
                    and not m.isupper()
                    or (m.isupper() and len(m) > 4 and m not in _PRODUCT_STOP)
                ):
                    add(f"제품·기술 확인: {m}", r, "요구사항에 등장한 제품·기술 명칭")
            if r.type == RequirementType.CONSTRAINT and _FRAMEWORK.search(text):
                add(f"제약 기술 검토: {r.name}", r, "제약사항에 명시된 프레임워크·표준·플랫폼")
            if r.type == RequirementType.NON_FUNCTIONAL and _SECURITY_PERF.search(text):
                add(f"비기능 검증: {r.name}", r, "보안·성능·호환성·가용성 검증 필요")
        if not any(t.topic.startswith("명시 솔루션") for t in topics.values()):
            add(
                "기술 스택 대안 비교 (프레임워크/WEB·WAS/DB)",
                None,
                "RFP가 기술을 명시하지 않아 대안 비교 필요",
            )
        return list(topics.values())

    # --- 실행 ------------------------------------------------------------------------------
    def run(
        self,
        project: Project,
        *,
        topics: list[ResearchTopic] | None = None,
        actor: str = "user",
        step_run_id: str | None = None,
        cancel: CancellationToken | None = None,
    ) -> ResearchRunResult:
        analysis = self._steps.prior_output(project, "rfp_analyst")
        topics = topics or self.identify_topics(project, analysis)
        prompt = self._prompt(project, topics)
        result = self._steps.run_role(
            project, "tech_researcher", prompt, actor=actor, step_run_id=step_run_id, cancel=cancel
        )
        report: ResearchReport = result.output  # type: ignore[assignment]
        items: list[TechnologyResearch] = []
        unverified = 0
        for draft in report.items:
            sources = [self._to_source(s) for s in draft.sources]
            facts = list(draft.confirmed_facts)
            unverified_items = list(draft.unverified_items)
            feasibility = draft.feasibility
            if not sources and facts:
                unverified_items.extend(f"(출처 없음) {f}" for f in facts)
                facts = []
                feasibility = FeasibilityVerdict.UNKNOWN
            if not sources:
                unverified_items.append("출처 URL이 기록되지 않아 사실 확인 불가")
            unverified += len(unverified_items)
            rec = TechnologyResearch(
                project_id=project.id,
                topic=draft.topic,
                related_requirement_ids=draft.related_requirement_ids,
                summary=draft.summary,
                confirmed_facts=facts,
                applicability_conditions=draft.applicability_conditions,
                unverified_items=unverified_items,
                impact_on_implementation=draft.impact_on_implementation,
                impact_on_proposal=draft.impact_on_proposal,
                feasibility=feasibility,
                risks=draft.risks,
                recommended_stack=draft.recommended_stack,
                sources=sources,
                agent_output_id=result.output_record.id,
                created_by=actor,
            )
            self._repos.research.insert(rec)
            items.append(rec)
            self._fill_implementation_approach(project, rec, actor)
        study: FeasibilityStudy | None = None
        if report.comparisons:
            comparisons = [
                FeasibilityComparisonRecord(
                    area=c.area,
                    rfp_specified=c.rfp_specified,
                    recommendation=c.recommendation,
                    rationale=c.rationale,
                    unverified_items=[*c.unverified_items, *self._missing_criteria(c)],
                    alternatives=[
                        TechAlternativeRecord(
                            name=a.name,
                            scores=a.scores,
                            license_and_cost=a.license_and_cost,
                            notes=a.notes,
                            sources=[self._to_source(s) for s in a.sources],
                        )
                        for a in c.alternatives
                    ],
                )
                for c in report.comparisons
            ]
            study = FeasibilityStudy(
                project_id=project.id,
                comparisons=comparisons,
                notes=report.notes,
                agent_output_id=result.output_record.id,
                created_by=actor,
            )
            self._repos.feasibility.insert(study)
        return ResearchRunResult(
            items=items,
            study=study,
            cost_usd=result.response.cost_usd,
            topics=topics,
            unverified_count=unverified,
        )

    def _fill_implementation_approach(
        self, project: Project, rec: TechnologyResearch, actor: str
    ) -> None:
        """조사 결과(impact_on_implementation)를 관련 요구사항의 구현 방안으로 채운다 (비어 있을 때만, 구현 불가·미확인 제외).

        제안서의 구현 방안이 조사 근거 없이 쓰이지 않게 하는 장치다. 사람이 요구사항 화면에서 고칠 수 있다.
        """
        if rec.feasibility in (FeasibilityVerdict.INFEASIBLE, FeasibilityVerdict.UNKNOWN):
            return
        text = (rec.impact_on_implementation or "").strip()
        if not text:
            return
        all_reqs = self._repos.requirements.find(project.id, order_by="id")
        by_any_id = {r.id: r for r in all_reqs}
        by_any_id.update({r.rfp_requirement_id: r for r in all_reqs if r.rfp_requirement_id})
        for rid in rec.related_requirement_ids:
            req = by_any_id.get(rid)  # 내부 ID(FR-001) 또는 RFP ID(SFR-001)
            if req is None or req.implementation_approach:
                continue
            req.implementation_approach = (
                f"{text[:300]} (근거: 조사 '{rec.topic[:40]}', {rec.feasibility.value})"
            )
            req.add_history(actor, "approach_from_research", note=rec.topic[:60])
            self._repos.requirements.update(req)

    @staticmethod
    def _missing_criteria(comparison: Any) -> list[str]:
        missing: list[str] = []
        for alt in comparison.alternatives:
            absent = [c for c in COMPARISON_CRITERIA if c not in alt.scores]
            if absent:
                missing.append(f"{alt.name}: 미평가 기준 {', '.join(absent)}")
        return missing

    @staticmethod
    def _to_source(draft: Any) -> ResearchSource:
        rule = classify_url(draft.url)
        return ResearchSource(
            url=draft.url,
            title=draft.title,
            product=draft.product,
            version=draft.version,
            trust=effective_trust(draft.trust, rule),
            trust_by_rule=rule,
            excerpt=draft.excerpt,
        )

    def _prompt(self, project: Project, topics: list[ResearchTopic]) -> str:
        reqs = self._steps.requirements_summary(project)
        existing = self._repos.research.find(project.id, order_by="created_at")
        prior = [
            {
                "topic": t.topic,
                "feasibility": str(t.feasibility),
                "sources": [s.url for s in t.sources],
            }
            for t in existing
        ][-30:]
        return (
            f"프로젝트: {project.name}\n\n<topics>\n{json.dumps([t.__dict__ for t in topics], ensure_ascii=False, indent=1)}\n</topics>\n\n"
            f"<requirements>\n{json.dumps(reqs, ensure_ascii=False)}\n</requirements>\n\n"
            f"<existing_research>\n{json.dumps(prior, ensure_ascii=False)}\n</existing_research>\n\n"
            "위 주제를 조사하고 구현 가능성 비교를 포함해 JSON으로 반환하라. 기존 조사와 같은 주제는 반복하지 말고 변경·보강 사항만 적어라. "
            "열람하지 않은 출처는 적지 말고, 확인하지 못한 항목은 unverified_items에 남겨라."
        )

    # --- 조회 ------------------------------------------------------------------------------
    def list_research(self, project: Project) -> list[TechnologyResearch]:
        return self._repos.research.find(project.id, order_by="created_at")

    def latest_study(self, project: Project) -> FeasibilityStudy | None:
        rows = self._repos.feasibility.find(
            project.id, order_by="created_at", descending=True, limit=1
        )
        return rows[0] if rows else None

    def mark_verified(
        self, project: Project, research_id: str, *, actor: str
    ) -> TechnologyResearch:
        rec = self._repos.research.get(research_id)
        rec.verified_by_human = True
        self._repos.research.update(rec)
        return rec


__all__ = [
    "COMPARISON_AREAS",
    "COMPARISON_CRITERIA",
    "ResearchRunResult",
    "ResearchService",
    "ResearchTopic",
    "SourceTrust",
]
