"""사업성 평가 서비스 (지시문 §6, 단계 2).

- ``assess_from_data`` 는 순수 함수다: RFP 분석·요구사항(+품질 검토)·조사·프로젝트 설정·계획(WBS·역할·배정) 을 받아
  13개 항목의 판정·근거·가정과 권고(제안) 를 만든다. 수익성은 사용자 단가(``ProjectSettings.cost_rates``) 와 예산이 있을
  때만 계산하고, 없으면 ``unavailable`` 로 둔다 — 임의 수치를 만들지 않는다.
- ``recommend`` 는 판정 분포로 권고를 제안한다(참여 권고/조건부/추가 검토/비권고). 최종 결정은 사람이 ``record_decision``
  으로 ``Decision``(공식 결정) 에 남긴다.
- 선택적으로 ``bid_reviewer`` 에이전트가 항목별 의견·위험·질문을 덧붙인다(API 키 필요).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.schemas import BidReviewDraft
from proposal_agent.config.errors import ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.models import (
    ActorKind,
    BidRecommendation,
    Decision,
    DecisionKind,
    DecisionStatus,
    FeasibilityAssessment,
    FeasibilityItem,
    FeasibilityRating,
    FeasibilityVerdict,
    Project,
    ProjectSettings,
    Requirement,
    RequirementStatus,
    RequirementType,
    StaffingAllocation,
    StaffRole,
    TechnologyResearch,
    WBSItem,
    utcnow,
)
from proposal_agent.models.feasibility import CRITICAL_ITEMS, ITEM_KEYS
from proposal_agent.planning.effort import md_to_mm
from proposal_agent.requirements.quality import QualityFinding, check_requirement_quality
from proposal_agent.requirements.service import LOW_CONFIDENCE
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.planning.service import PlanningService
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService

log = get_logger("feasibility")

STEP_BID_ASSESSMENT = "bid_assessment"
ROLE_BID_REVIEWER = "bid_reviewer"
REPORT_SUBDIR = "02_RFP_Analysis"
_KRW_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원?")
_CONTRACT_WORDS = ("지체상금", "하자보수", "무상", "책임", "손해배상", "위약", "계약", "보증")
_SECURITY_WORDS = ("개인정보", "보안", "암호", "접근 통제", "인증", "ISMS", "법", "규정")


# --- 도우미 --------------------------------------------------------------------------------------
def parse_krw(text: str) -> Decimal | None:
    """'약 4.5억', '450,000,000원', '3천만원' 같은 금액 문구를 원 단위 Decimal 로. 못 찾으면 None."""
    best: Decimal | None = None
    for num, unit in _KRW_RE.findall(text or ""):
        try:
            v = Decimal(num.replace(",", ""))
        except Exception:
            continue
        mult = {
            "억": Decimal(10**8),
            "천만": Decimal(10**7),
            "백만": Decimal(10**6),
            "만": Decimal(10**4),
        }.get(unit)
        if mult is None:
            if "," not in num and v < 10_000:  # 단위 없는 작은 수는 금액이 아님
                continue
            mult = Decimal(1)
        v = (v * mult).quantize(Decimal("1"))
        if best is None or v > best:
            best = v
    return best


def _rating_rank(r: FeasibilityRating) -> int:
    return {"good": 0, "unknown": 1, "caution": 2, "risk": 3}[r.value]


def recommend(items: list[FeasibilityItem]) -> tuple[BidRecommendation, list[str]]:
    """판정 분포 → 권고(제안). 치명 항목의 위험은 가중치 없이 그대로 센다(사람이 최종 결정)."""
    finals = {i.key: i.final_rating for i in items}
    risks = [k for k, r in finals.items() if r == FeasibilityRating.RISK]
    cautions = [k for k, r in finals.items() if r == FeasibilityRating.CAUTION]
    unknowns = [k for k, r in finals.items() if r == FeasibilityRating.UNKNOWN]
    titles = dict(ITEM_KEYS)
    basis: list[str] = [
        f"판정 분포: 양호 {len(items) - len(risks) - len(cautions) - len(unknowns)} · 주의 {len(cautions)} · 위험 {len(risks)} · 미확인 {len(unknowns)}"
    ]
    critical_risk = [k for k in risks if k in CRITICAL_ITEMS]
    if len(risks) >= 2 or len(critical_risk) >= 1 and len(unknowns) <= 2 and len(risks) >= 2:
        rec = BidRecommendation.NOT_RECOMMENDED
        basis.append("위험 항목 2개 이상: " + ", ".join(titles[k] for k in risks))
    elif risks:
        rec = BidRecommendation.CONDITIONAL
        basis.append("위험 항목 1개(" + titles[risks[0]] + ") — 해소 조건을 붙여 참여 검토")
    elif len(unknowns) >= 4:
        rec = BidRecommendation.NEEDS_REVIEW
        basis.append(
            "미확인 항목 4개 이상 — 사용자 입력·추가 확인 후 재평가: "
            + ", ".join(titles[k] for k in unknowns[:6])
        )
    elif len(cautions) >= 4:
        rec = BidRecommendation.CONDITIONAL
        basis.append("주의 항목 4개 이상: " + ", ".join(titles[k] for k in cautions[:6]))
    else:
        rec = BidRecommendation.RECOMMENDED
        basis.append("위험 없음, 미확인 4개 미만")
    basis.append("권고는 제안이며 최종 참여 여부는 사용자가 결정한다")
    return rec, basis


@dataclass
class AssessmentInputs:
    project: Project
    settings: ProjectSettings
    analysis: dict[str, Any] | None
    requirements: list[Requirement]
    research: list[TechnologyResearch]
    wbs: list[WBSItem]
    roles: list[StaffRole]
    allocations: list[StaffingAllocation]
    quality: list[QualityFinding]
    today: date | None = None


def _item(key: str) -> FeasibilityItem:
    return FeasibilityItem(key=key, title=dict(ITEM_KEYS)[key])


def assess_from_data(inp: AssessmentInputs) -> FeasibilityAssessment:  # noqa: C901 — 항목별 규칙 나열
    a = inp.analysis or {}
    s = inp.settings
    reqs = [
        r
        for r in inp.requirements
        if r.status != RequirementStatus.DELETED and r.change_state != "deleted"
    ]
    func = [r for r in reqs if r.type == RequirementType.FUNCTIONAL]
    items: list[FeasibilityItem] = []

    # 1. 전략 적합성 — 데이터로 판단 불가, 설명·목표만 제시
    it = _item("strategic_fit")
    goals = a.get("client_goals") or []
    if goals:
        it.code_basis.append("발주처 목표: " + "; ".join(str(g)[:60] for g in goals[:3]))
    if s.description:
        it.code_basis.append("사업 설명(설정): " + s.description[:100])
    it.needs_input = True
    it.assumptions.append("제안사의 전략·사업 방향과의 적합성은 사용자 판단")
    items.append(it)

    # 2. 수주 가능성·평가 기준
    it = _item("win_probability")
    crit = a.get("evaluation_criteria") or []
    if crit:
        it.code_basis.append(
            f"RFP 평가 기준 {len(crit)}개: " + "; ".join(str(c)[:50] for c in crit[:4])
        )
        it.rating = FeasibilityRating.CAUTION
        it.assumptions.append(
            "경쟁사·실적 정보가 없어 배점 구조만 반영(기술·가격 비중은 사용자 확인)"
        )
    else:
        it.code_basis.append("RFP 분석에 평가 기준 없음")
    it.needs_input = True
    items.append(it)

    # 3. 기술 확보
    it = _item("tech_capability")
    verdicts = [t.feasibility for t in inp.research]
    if not verdicts:
        it.code_basis.append("기술 조사 기록 없음")
    else:
        n_inf = sum(1 for v in verdicts if v == FeasibilityVerdict.INFEASIBLE)
        n_risk = sum(1 for v in verdicts if v == FeasibilityVerdict.FEASIBLE_WITH_RISK)
        n_unk = sum(1 for v in verdicts if v == FeasibilityVerdict.UNKNOWN)
        it.code_basis.append(
            f"조사 {len(verdicts)}건: 구현 불가 {n_inf}, 위험 동반 {n_risk}, 미확인 {n_unk}, 가능 {len(verdicts) - n_inf - n_risk - n_unk}"
        )
        unverified = sum(len(t.unverified_items) for t in inp.research)
        if unverified:
            it.code_basis.append(f"조사 미확인 사항 {unverified}건")
        if n_inf:
            it.rating = FeasibilityRating.RISK
        elif n_risk or n_unk:
            it.rating = FeasibilityRating.CAUTION
        else:
            it.rating = FeasibilityRating.GOOD
    named = a.get("named_solutions") or []
    if named:
        it.code_basis.append("RFP 명시 솔루션·기술: " + ", ".join(str(x)[:30] for x in named[:6]))
    if s.tech_stack.filled():
        it.code_basis.append(
            "설정 기술 스택: " + ", ".join(f"{k} {v}" for k, v in s.tech_stack.labeled()[:4])
        )
    items.append(it)

    # 4. 인력·협력사
    it = _item("staffing")
    if inp.roles:
        it.code_basis.append(
            f"계획 역할 {len(inp.roles)}종, 인원 {sum(r.headcount_planned for r in inp.roles)}명: "
            + ", ".join(f"{r.role_name}×{r.headcount_planned}" for r in inp.roles[:6])
        )
        it.rating = FeasibilityRating.CAUTION
        it.assumptions.append("역할·인원은 계획값이며 실제 확보 가능 여부는 사용자 확인")
    else:
        it.code_basis.append("인력 계획 없음(WBS·인력 계획 단계 전)")
    if s.external_solutions:
        it.code_basis.append("외부 솔루션·협력사 후보: " + ", ".join(s.external_solutions[:5]))
    it.needs_input = True
    items.append(it)

    # 5. 일정·납기
    it = _item("schedule")
    months = None
    if inp.project.start_date and inp.project.end_date:
        days = (inp.project.end_date - inp.project.start_date).days + 1
        months = max(days / 30.4, 0.1)
        it.code_basis.append(
            f"사업 기간 {inp.project.start_date}~{inp.project.end_date} ({months:.1f}개월)"
        )
    hints = a.get("schedule_hints") or []
    if hints:
        it.code_basis.append("RFP 일정 조건: " + "; ".join(str(h)[:50] for h in hints[:3]))
    if s.schedule_constraints:
        it.code_basis.append("설정 일정 제약: " + "; ".join(s.schedule_constraints[:3]))
    total_md = (
        sum((w.effort_md for w in inp.wbs if w.parent_id is None), Decimal("0"))
        if inp.wbs
        else Decimal("0")
    )
    if not inp.wbs:
        total_md = Decimal("0")
    if months and total_md > 0:
        total_mm = md_to_mm(total_md)
        team = float(total_mm) / months
        it.code_basis.append(f"총 공수 {total_mm} M/M ÷ {months:.1f}개월 = 평균 투입 {team:.1f}명")
        if team > 12:
            it.rating = FeasibilityRating.RISK
            it.assumptions.append("평균 12명 초과는 동시 투입·관리 부담이 큼(기준값, 조정 가능)")
        elif team > 6 or months < 4:
            it.rating = FeasibilityRating.CAUTION
        else:
            it.rating = FeasibilityRating.GOOD
    elif months:
        it.rating = FeasibilityRating.CAUTION if months < 4 else FeasibilityRating.UNKNOWN
        it.assumptions.append("공수(WBS) 가 없어 기간만으로 판단")
    else:
        it.code_basis.append("사업 기간 미정")
    items.append(it)

    # 6. 공수
    it = _item("effort")
    if total_md > 0:
        it.code_basis.append(
            f"WBS 총 공수 {total_md} M/D ({md_to_mm(total_md)} M/M), 상위 항목 {sum(1 for w in inp.wbs if w.parent_id is None)}개"
        )
        it.rating = FeasibilityRating.GOOD
        basis_missing = sum(1 for w in inp.wbs if not (w.estimate_basis or "").strip())
        if basis_missing:
            it.rating = FeasibilityRating.CAUTION
            it.code_basis.append(f"산정 근거 없는 항목 {basis_missing}개")
        if s.effort_limit_mm is not None:
            if md_to_mm(total_md) > s.effort_limit_mm:
                it.rating = FeasibilityRating.RISK
                it.code_basis.append(f"공수 상한 {s.effort_limit_mm} M/M 초과")
            else:
                it.code_basis.append(f"공수 상한 {s.effort_limit_mm} M/M 이내")
    else:
        it.code_basis.append(f"WBS 없음 — 요구사항 {len(reqs)}건(기능 {len(func)}건) 기준 산정 전")
        it.assumptions.append("공수는 WBS 단계에서 산정, 지금은 미확인")
    items.append(it)

    # 7. 수익성
    it = _item("profitability")
    revenue = s.budget_amount
    rev_src = "설정 예산"
    if revenue is None:
        for h in a.get("budget_hints") or []:
            parsed = parse_krw(str(h))
            if parsed:
                revenue, rev_src = parsed, f"RFP 예산 문구 '{str(h)[:40]}'"
                break
    cost: Decimal | None = None
    cost_lines: list[str] = []
    if inp.allocations and (s.cost_rates or any(r.unit_cost_per_mm for r in inp.roles)):
        by_role: dict[str, Decimal] = {}
        role_name = {r.id: r.role_name for r in inp.roles}
        for al in inp.allocations:
            by_role[role_name.get(al.staff_role_id, al.staff_role_id)] = by_role.get(
                role_name.get(al.staff_role_id, al.staff_role_id), Decimal("0")
            ) + Decimal(str(al.effort_md))
        rate_of = {r.role_name: r.unit_cost_per_mm for r in inp.roles if r.unit_cost_per_mm}
        rate_of.update(s.cost_rates)
        missing_rate = [n for n in by_role if n not in rate_of]
        if not missing_rate:
            cost = Decimal("0")
            for n, md in by_role.items():
                mm = md_to_mm(md)
                cost += mm * rate_of[n]
                cost_lines.append(f"{n}: {mm} M/M × {rate_of[n]:,} 원")
            if s.overhead_ratio is not None:
                cost = cost * (Decimal(1) + s.overhead_ratio)
                cost_lines.append(f"간접비율 {s.overhead_ratio} 적용")
        else:
            it.assumptions.append("단가 없는 역할: " + ", ".join(missing_rate[:5]))
    cost_estimate: dict[str, Any] = {"status": "unavailable", "assumptions": []}
    if revenue is not None and cost is not None:
        margin = (revenue - cost) / revenue if revenue else Decimal(0)
        cost_estimate = {
            "status": "estimated",
            "revenue": str(revenue),
            "revenue_source": rev_src,
            "cost": str(cost.quantize(Decimal("1"))),
            "margin_ratio": str(margin.quantize(Decimal("0.001"))),
            "lines": cost_lines,
            "assumptions": [
                "부가세·간접비 처리는 단가·예산 입력 기준",
                "원가는 계획 공수 × 단가이며 실제 투입과 다를 수 있음",
            ],
        }
        it.code_basis.append(
            f"매출(예산) {revenue:,} 원 ({rev_src}), 원가 {cost.quantize(Decimal('1')):,} 원, 마진 {margin:.1%}"
        )
        if margin >= Decimal("0.15"):
            it.rating = FeasibilityRating.GOOD
        elif margin >= Decimal("0.05"):
            it.rating = FeasibilityRating.CAUTION
        else:
            it.rating = FeasibilityRating.RISK
    else:
        if revenue is not None:
            it.code_basis.append(f"매출(예산) {revenue:,} 원 ({rev_src})")
        else:
            it.code_basis.append("예산 정보 없음(설정·RFP 모두)")
        if cost is None:
            it.code_basis.append("원가 산정 불가: 역할별 단가 또는 배정 공수 없음")
        cost_estimate["assumptions"] = ["단가(설정 '역할별 단가')·예산·배정 공수가 있어야 산정"]
        it.needs_input = True
    it.assumptions.extend(cost_estimate.get("assumptions", []))
    items.append(it)

    # 8. 외부 솔루션
    it = _item("external_solutions")
    ext = list(s.external_solutions) + [str(x) for x in named if str(x) not in s.external_solutions]
    if ext:
        it.code_basis.append("솔루션·제품: " + ", ".join(ext[:6]))
        it.rating = FeasibilityRating.CAUTION
        it.assumptions.append("라이선스·도입 비용은 견적 확인 전(사용자 입력)")
        it.needs_input = True
    else:
        it.code_basis.append("명시된 외부 솔루션 없음")
        it.rating = FeasibilityRating.GOOD
    items.append(it)

    # 9. 계약 조건
    it = _item("contract")
    cons = [
        str(c) for c in (a.get("constraints") or []) if any(w in str(c) for w in _CONTRACT_WORDS)
    ]
    if cons:
        it.code_basis.append("계약 관련 조건: " + "; ".join(c[:50] for c in cons[:3]))
        it.rating = FeasibilityRating.CAUTION
    else:
        it.code_basis.append("RFP 분석에서 계약·책임 조건을 찾지 못함")
    it.needs_input = True
    items.append(it)

    # 10. 보안·개인정보·법적
    it = _item("security_legal")
    sec = [str(x) for x in (a.get("security_privacy") or [])] + list(
        s.security_privacy_requirements
    )
    if sec:
        it.code_basis.append(
            f"보안·개인정보 요구 {len(sec)}건: " + "; ".join(x[:40] for x in sec[:3])
        )
        it.rating = FeasibilityRating.CAUTION
        if any("개인정보" in x for x in sec):
            it.assumptions.append("개인정보 처리 시 법적 검토(위탁·비식별) 필요")
    else:
        it.code_basis.append("보안·개인정보 요구 미확인")
    items.append(it)

    # 11. 모호성
    it = _item("ambiguity")
    low_conf = [r.id for r in reqs if r.confidence < LOW_CONFIDENCE]
    vague = [f for f in inp.quality if f.rule in ("Q-VAGUE", "Q-CONFLICT", "Q-DUP")]
    unc = a.get("uncertainties") or []
    n_reqs = len(reqs) or 1
    score = (len(low_conf) + len(vague)) / n_reqs
    it.code_basis.append(
        f"요구사항 {len(reqs)}건 중 신뢰도 낮음 {len(low_conf)}건, 검증 불가·충돌·중복 후보 {len(vague)}건, RFP 불확실 사항 {len(unc)}건"
    )
    if reqs:
        it.rating = (
            FeasibilityRating.RISK
            if score > 0.3
            else FeasibilityRating.CAUTION
            if score > 0.1 or unc
            else FeasibilityRating.GOOD
        )
    else:
        it.code_basis.append("요구사항 없음")
    items.append(it)

    # 12. 기존 시스템 연계·기술 부채
    it = _item("legacy")
    targets = a.get("integration_targets") or []
    if targets or s.integration_systems:
        it.code_basis.append(
            "연계 대상: "
            + ", ".join([str(t)[:30] for t in targets[:5]] + s.integration_systems[:5])
        )
        it.rating = FeasibilityRating.CAUTION
    if s.has_existing_system is True:
        it.code_basis.append("기존 시스템 있음: " + (s.existing_system_note or "설명 없음"))
        it.rating = FeasibilityRating.CAUTION
    elif s.has_existing_system is False and not targets:
        it.rating = FeasibilityRating.GOOD
        it.code_basis.append("기존 시스템 없음, 연계 대상 없음")
    if it.rating == FeasibilityRating.UNKNOWN:
        it.code_basis.append("기존 시스템·연계 정보 미확인(설정 입력)")
        it.needs_input = True
    items.append(it)

    # 13. 실패 요인·대응
    it = _item("failure_factors")
    worst = max(items, key=lambda x: _rating_rank(x.final_rating))
    risky = [
        x for x in items if x.final_rating in (FeasibilityRating.RISK, FeasibilityRating.CAUTION)
    ]
    for x in risky[:6]:
        it.code_basis.append(
            f"{x.title}: {x.final_rating.label} — " + (x.code_basis[0] if x.code_basis else "")
        )
    research_risks = [rk for t in inp.research for rk in t.risks][:4]
    for rk in research_risks:
        it.code_basis.append("조사 위험: " + str(rk)[:60])
    it.rating = (
        FeasibilityRating.GOOD
        if not risky
        else (
            FeasibilityRating.CAUTION
            if worst.final_rating != FeasibilityRating.RISK
            else FeasibilityRating.RISK
        )
    )
    it.assumptions.append("대응 방안은 전략 브리프·위험 대장에서 구체화")
    items.append(it)

    rec, basis = recommend(items)
    key_risks = [
        f"{x.title}: {x.code_basis[0]}"
        for x in items
        if x.final_rating == FeasibilityRating.RISK and x.code_basis
    ]
    open_q = [f"{x.title}: 사용자 입력·확인 필요" for x in items if x.needs_input] + [
        str(u)[:80] for u in unc[:5]
    ]
    return FeasibilityAssessment(
        project_id=inp.project.id,
        items=items,
        recommendation=rec,
        recommendation_basis=basis,
        key_risks=key_risks,
        open_questions=open_q,
        effort_estimate={
            "total_md": str(total_md),
            "total_mm": str(md_to_mm(total_md)) if total_md else "",
            "months": f"{months:.1f}" if months else "",
        },
        cost_estimate=cost_estimate,
        inputs_snapshot={
            "requirements": len(reqs),
            "functional": len(func),
            "research": len(inp.research),
            "wbs_items": len(inp.wbs),
            "roles": len(inp.roles),
            "quality_findings": len(inp.quality),
            "analysis_keys": sorted(k for k in a if a.get(k)),
            "settings": s.summary_lines()[:8],
        },
        created_by="code:feasibility",
    )


# --- 서비스 ---------------------------------------------------------------------------------------
class FeasibilityService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        files: FileStore,
        audit: AuditService,
        steps: AgentStepService,
        planning: PlanningService,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._files = files
        self._audit = audit
        self._steps = steps
        self._planning = planning

    def latest(self, project: Project) -> FeasibilityAssessment | None:
        rows = self._repos.feasibility_assessments.find(
            project.id, order_by="created_at", descending=True, limit=1
        )
        return rows[0] if rows else None

    def assess(
        self,
        project: Project,
        *,
        actor: str = "user",
        user_ratings: dict[str, tuple[str | None, str]] | None = None,
    ) -> FeasibilityAssessment:
        """데이터로 평가하고 평가서(JSON·MD) 를 쓴다. ``user_ratings`` 는 {key: (rating 또는 None, note)}."""
        from proposal_agent.models import SETTINGS_KEY  # noqa: F401 — 설정 키 존재 확인용

        settings = ProjectSettings.from_project_settings(project.settings)
        reqs = self._repos.requirements.find(project.id, order_by="id")
        research = self._repos.research.find(project.id, order_by="created_at")
        wbs, _deps, roles, allocs = self._planning.current_plan(project)
        inp = AssessmentInputs(
            project=project,
            settings=settings,
            analysis=self._steps.prior_output(project, "rfp_analyst"),
            requirements=reqs,
            research=research,
            wbs=wbs,
            roles=roles,
            allocations=allocs,
            quality=check_requirement_quality(reqs),
        )
        assessment = assess_from_data(inp)
        prev = self.latest(project)
        if prev is not None:
            assessment.version = prev.version + 1
            if prev.agent_review:
                assessment.agent_review = prev.agent_review
        for key, (rating, note) in (user_ratings or {}).items():
            it = assessment.item(key)
            if it is None:
                continue
            it.user_rating = FeasibilityRating(rating) if rating else None
            it.user_note = note or ""
        if user_ratings:
            assessment.recommendation, assessment.recommendation_basis = recommend(assessment.items)
        assessment.created_by = actor
        assessment.report_path = self._write_report(project, assessment)
        self._repos.feasibility_assessments.insert(assessment)
        self._audit.record(
            project.id,
            "feasibility.assessed",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="FeasibilityAssessment",
            entity_id=assessment.id,
            payload={
                "recommendation": assessment.recommendation.value,
                "counts": assessment.counts(),
                "report": assessment.report_path,
            },
        )
        return assessment

    def review_with_agent(
        self, project: Project, assessment: FeasibilityAssessment, *, actor: str = "user"
    ) -> FeasibilityAssessment:
        """bid_reviewer 에이전트로 항목별 의견·위험·질문을 받는다(선택). 판정은 바꾸지 않고 의견만 덧붙인다."""
        prompt = (
            "<assessment>\n"
            + json.dumps(
                {
                    "recommendation": assessment.recommendation.value,
                    "items": [
                        {
                            "key": i.key,
                            "title": i.title,
                            "rating": i.final_rating.value,
                            "basis": i.code_basis,
                            "assumptions": i.assumptions,
                            "needs_input": i.needs_input,
                        }
                        for i in assessment.items
                    ],
                    "cost_estimate": assessment.cost_estimate,
                    "effort_estimate": assessment.effort_estimate,
                    "open_questions": assessment.open_questions,
                },
                ensure_ascii=False,
            )
            + "\n</assessment>\n\n위 코드 평가를 검토해 항목별 의견(근거 있는 사실과 판단 구분), 추가 위험, 확인 질문을 JSON 으로 반환하라. 수치를 만들지 말고 데이터에 없는 것은 질문으로 남겨라."
        )
        result = self._steps.run_role(project, ROLE_BID_REVIEWER, prompt, actor=actor)
        draft = BidReviewDraft.model_validate(result.output)
        for c in draft.items:
            it = assessment.item(c.key)
            if it is not None:
                it.agent_comment = c.comment[:400]
        assessment.agent_review = {
            "overall": draft.overall_comment,
            "key_risks": draft.key_risks,
            "open_questions": draft.open_questions,
            "cost_usd": round(result.response.cost_usd, 4),
            "output_id": result.output_record.id,
        }
        assessment.key_risks = list(dict.fromkeys(assessment.key_risks + draft.key_risks))[:10]
        assessment.open_questions = list(
            dict.fromkeys(assessment.open_questions + draft.open_questions)
        )[:12]
        assessment.status = "reviewed"
        assessment.report_path = self._write_report(project, assessment)
        self._repos.feasibility_assessments.update(assessment)
        return assessment

    def record_decision(
        self,
        project: Project,
        assessment: FeasibilityAssessment,
        *,
        choice: BidRecommendation,
        rationale: str,
        decider: str,
        authority_confirmed: bool,
    ) -> Decision:
        """참여 의사결정을 공식 결정(Decision) 으로 기록한다. 권한이 확인되지 않으면 '제안' 상태로 남는다."""
        if not (rationale or "").strip():
            raise ValidationError(
                "참여 결정에는 근거가 필요합니다.",
                resolution="결정 근거(주요 위험·조건) 를 적으십시오.",
            )
        code = self._repos.next_code(project.id, "DEC")
        decision = Decision(
            project_id=project.id,
            code=code,
            title=f"사업 참여 결정: {choice.label}",
            kind=DecisionKind.OFFICIAL_DECISION,
            status=DecisionStatus.APPROVED if authority_confirmed else DecisionStatus.PROPOSED,
            content=f"평가 권고 {assessment.recommendation.label} → 결정 {choice.label}",
            rationale=rationale,
            recorded_on=date.today(),
            owner=decider,
            authority_confirmed=authority_confirmed,
            approved_by=decider if authority_confirmed else "",
            approved_at=utcnow() if authority_confirmed else None,
            created_by=decider,
        )
        self._repos.decisions.insert(decision)
        assessment.decision_id = decision.id
        assessment.decision_choice = choice.value
        assessment.status = "decided" if authority_confirmed else assessment.status
        assessment.report_path = self._write_report(project, assessment)
        self._repos.feasibility_assessments.update(assessment)
        self._audit.record(
            project.id,
            "feasibility.decided",
            actor=decider,
            actor_kind=ActorKind.USER,
            entity_type="Decision",
            entity_id=decision.id,
            payload={
                "choice": choice.value,
                "authority_confirmed": authority_confirmed,
                "binding": decision.is_binding,
            },
        )
        return decision

    # --- 평가서 ---------------------------------------------------------------------------------
    def _write_report(self, project: Project, a: FeasibilityAssessment) -> str:
        md = self.render_markdown(project, a)
        name = self._files.next_version_name(project.output_dir, REPORT_SUBDIR, "사업성평가", ".md")
        stored = self._files.save_bytes(project.output_dir, REPORT_SUBDIR, name, md.encode("utf-8"))
        json_name = name[:-3] + ".json"
        self._files.save_bytes(
            project.output_dir,
            REPORT_SUBDIR,
            json_name,
            json.dumps(a.model_dump(mode="json"), ensure_ascii=False, indent=1).encode("utf-8"),
        )
        return stored.relative_path

    @staticmethod
    def render_markdown(project: Project, a: FeasibilityAssessment) -> str:
        lines = [
            f"# 사업 참여 타당성 평가서 — {project.name}",
            "",
            f"작성: {a.created_at:%Y-%m-%d %H:%M} · 버전 {a.version} · 상태 {a.status}",
            "",
            f"## 1. 권고(제안): **{a.recommendation.label}**",
            "",
            *[f"- {b}" for b in a.recommendation_basis],
            "",
            "> 점수만으로 결정하지 않는다. 최종 참여 여부는 사용자가 결정하며 아래 '참여 결정' 에 기록된다.",
            "",
            "## 2. 항목별 평가",
            "",
            "| # | 항목 | 코드 판정 | 사용자 판정 | 근거 | 가정·확인 필요 |",
            "|---|---|---|---|---|---|",
        ]
        for i, it in enumerate(a.items, start=1):
            lines.append(
                f"| {i} | {it.title} | {it.rating.label} | {it.user_rating.label if it.user_rating else '-'}"
                f"{(' — ' + it.user_note) if it.user_note else ''} | {'<br>'.join(it.code_basis) or '-'} | "
                f"{'<br>'.join(it.assumptions) or '-'}{'<br>(사용자 입력 필요)' if it.needs_input else ''} |"
            )
        lines += ["", "## 3. 공수·비용 산정", ""]
        ce = a.cost_estimate or {}
        if ce.get("status") == "estimated":
            lines += [
                f"- 매출(예산): {Decimal(ce['revenue']):,} 원 ({ce.get('revenue_source', '')})",
                f"- 원가: {Decimal(ce['cost']):,} 원",
                f"- 마진율: {Decimal(ce['margin_ratio']):.1%}",
                *[f"  - {x}" for x in ce.get("lines", [])],
            ]
        else:
            lines.append("- 산정 불가: " + "; ".join(ce.get("assumptions", [])))
        ee = a.effort_estimate or {}
        if ee.get("total_mm"):
            lines.append(
                f"- 총 공수 {ee['total_md']} M/D ({ee['total_mm']} M/M), 기간 {ee.get('months') or '-'}개월"
            )
        lines += ["", "## 4. 주요 위험", ""] + (
            [f"- {x}" for x in a.key_risks] or ["- 위험 판정 항목 없음"]
        )
        lines += ["", "## 5. 추가 확인 사항", ""] + (
            [f"- {x}" for x in a.open_questions] or ["- 없음"]
        )
        if a.agent_review:
            lines += ["", "## 6. 에이전트 검토 의견", "", a.agent_review.get("overall", ""), ""]
            for it in a.items:
                if it.agent_comment:
                    lines.append(f"- {it.title}: {it.agent_comment}")
        lines += ["", "## 7. 참여 결정", ""]
        if a.decision_id:
            lines.append(
                f"- 결정: **{BidRecommendation(a.decision_choice).label}** (Decision {a.decision_id}, 상태 {a.status})"
            )
        else:
            lines.append("- 미결정 — 화면 '사업성 평가' 에서 결정을 기록")
        lines += [
            "",
            "## 8. 평가에 쓴 데이터",
            "",
            "```json",
            json.dumps(a.inputs_snapshot, ensure_ascii=False, indent=1),
            "```",
            "",
        ]
        return "\n".join(lines)


__all__ = [
    "ROLE_BID_REVIEWER",
    "STEP_BID_ASSESSMENT",
    "AssessmentInputs",
    "FeasibilityService",
    "assess_from_data",
    "parse_krw",
    "recommend",
]
