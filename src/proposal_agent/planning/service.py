"""계획 서비스: WBS 초안(에이전트 또는 코드 기본값) → 검증 → 일정·공수·인력 계산 → 저장.

과제 기간 결정 순서: UI 입력(Project.start_date/end_date) → RFP 분석의 schedule_hints(개월 수) → 없으면 입력 요청(ValidationError).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.schemas import MilestoneDraft, WBSDraft, WbsItemDraft
from proposal_agent.config.errors import ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.settings import Settings
from proposal_agent.models import (
    Dependency,
    DependencyType,
    Project,
    Requirement,
    RequirementStatus,
    RequirementType,
    StaffingAllocation,
    StaffRole,
    WBSItem,
    WBSLevel,
    WorkType,
)
from proposal_agent.planning.calendar import BusinessCalendar, parse_holidays
from proposal_agent.planning.effort import duration_days_for, rollup, split_by_ratio
from proposal_agent.planning.scheduler import DepEdge, ScheduleResult, TaskNode, compute_schedule
from proposal_agent.planning.staffing import DEFAULT_ROLE_CATALOG, RoleLoad, aggregate_roles
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("planning.service")

_MONTHS_RE = re.compile(r"(\d+)\s*개월")
# 보고용 WBS 마일스톤 기본값 (에이전트가 milestones를 주지 않을 때). 코드 '0' 아래에 들어간다.
MILESTONE_PHASE_CODE = "0"
MILESTONE_PHASE_NAME = "사업관리(마일스톤)"
DEFAULT_MILESTONES: tuple[tuple[str, str], ...] = (
    ("착수", "start"),
    ("착수보고", "+2w"),
    ("중간보고", "mid"),
    ("완료보고", "-2w"),
    ("종료", "end"),
)
_REL_WEEK_RE = re.compile(r"^([+-])(\d+)w$")


def milestone_date(
    timing: str,
    *,
    start: date,
    end: date,
    ends_by_code: dict[str, date],
    calendar: BusinessCalendar,
) -> date | None:
    """마일스톤 시점 표기 → 날짜. start | mid | end | after:<code> | +Nw(착수 후) | -Nw(종료 전)."""
    t = (timing or "end").strip()
    if t == "start":
        return calendar.next_business_day(start)
    if t == "end":
        return end if calendar.is_business_day(end) else calendar.next_business_day(end)
    if t == "mid":
        total = calendar.business_days_between(start, end)
        return calendar.add_business_days(start, max(0, total // 2))
    if t.startswith("after:"):
        d = ends_by_code.get(t[6:].strip())
        return calendar.next_business_day(d + timedelta(days=1)) if d else None
    m = _REL_WEEK_RE.match(t)
    if m:
        weeks = int(m.group(2))
        base = start if m.group(1) == "+" else end
        d = base + timedelta(days=7 * weeks * (1 if m.group(1) == "+" else -1))
        d = max(start, min(end, d))
        return d if calendar.is_business_day(d) else calendar.next_business_day(d)
    return None


DEFAULT_EFFORT_BY_TYPE: dict[RequirementType, Decimal] = {
    RequirementType.FUNCTIONAL: Decimal("8"),
    RequirementType.NON_FUNCTIONAL: Decimal("5"),
    RequirementType.CONSTRAINT: Decimal("3"),
    RequirementType.EVALUATION: Decimal("0"),
    RequirementType.SUBMISSION: Decimal("0"),
}
ROLE_BY_TYPE: dict[RequirementType, list[dict[str, str]]] = {
    RequirementType.FUNCTIONAL: [
        {"role": "백엔드", "ratio": "0.5"},
        {"role": "프런트엔드", "ratio": "0.3"},
        {"role": "QA", "ratio": "0.2"},
    ],
    RequirementType.NON_FUNCTIONAL: [
        {"role": "아키텍트", "ratio": "0.5"},
        {"role": "인프라", "ratio": "0.3"},
        {"role": "QA", "ratio": "0.2"},
    ],
    RequirementType.CONSTRAINT: [
        {"role": "아키텍트", "ratio": "0.6"},
        {"role": "PL", "ratio": "0.4"},
    ],
}


@dataclass
class ProjectPeriod:
    start: date
    end: date
    source: str  # ui | rfp_hint | default


@dataclass
class PlanResult:
    items: list[WBSItem] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    roles: list[StaffRole] = field(default_factory=list)
    allocations: list[StaffingAllocation] = field(default_factory=list)
    schedule: ScheduleResult | None = None
    period: ProjectPeriod | None = None
    role_loads: dict[str, RoleLoad] = field(default_factory=dict)
    auto_generated: bool = False
    review_notes: list[str] = field(default_factory=list)
    total_effort_md: Decimal = Decimal("0")


class PlanningService:
    def __init__(self, repos: Repositories, settings: Settings, audit: AuditService) -> None:
        self._repos = repos
        self._settings = settings
        self._audit = audit

    # --- 기간 ------------------------------------------------------------------------------
    def resolve_period(self, project: Project, analysis: dict[str, Any] | None) -> ProjectPeriod:
        if project.start_date and project.end_date:
            return ProjectPeriod(project.start_date, project.end_date, "ui")
        hints = (analysis or {}).get("schedule_hints") or []
        for hint in hints:
            m = _MONTHS_RE.search(str(hint))
            if m and project.start_date:
                months = int(m.group(1))
                year = project.start_date.year + (project.start_date.month - 1 + months) // 12
                month = (project.start_date.month - 1 + months) % 12 + 1
                end = (
                    date(year, month, min(project.start_date.day, 28))
                    if months
                    else project.start_date
                )
                return ProjectPeriod(project.start_date, end, "rfp_hint")
        raise ValidationError(
            "과제 기간을 확인할 수 없습니다.",
            cause="프로젝트 시작일·종료일이 없고 RFP에서 기간을 읽지 못함",
            resolution="프로젝트 화면에서 과제 시작일과 종료일을 입력한 뒤 다시 실행하십시오.",
        )

    def calendar(self) -> BusinessCalendar:
        return BusinessCalendar(parse_holidays(self._settings.holidays))

    # --- 기본 WBS (에이전트 결과 없을 때) ------------------------------------------------------
    def default_draft(self, requirements: list[Requirement]) -> WBSDraft:
        """요구사항에서 3단계 WBS를 결정적으로 만든다. 공수는 기본값이며 '검토 필요'로 표시된다."""
        items: list[WbsItemDraft] = []
        deps = []
        phases = [("1", "분석·설계", "분석"), ("2", "구현", "개발"), ("3", "시험·이행", "QA")]
        items.append(
            WbsItemDraft(code="1", level="phase", name="분석·설계", estimate_basis="단계 합계")
        )
        items.append(
            WbsItemDraft(
                code="1.1",
                parent_code="1",
                level="activity",
                name="요구사항 분석·설계",
                estimate_basis="요구사항 수 × 1 M/D",
                effort_md_estimate=float(max(len(requirements), 1)),
                roles=[{"role": "PL", "ratio": "0.5"}, {"role": "분석", "ratio": "0.5"}],
                related_requirement_ids=[r.id for r in requirements],
            )
        )
        items.append(WbsItemDraft(code="2", level="phase", name="구현", estimate_basis="단계 합계"))
        grouped: dict[RequirementType, list[Requirement]] = {}
        for r in requirements:
            grouped.setdefault(r.type, []).append(r)
        n = 0
        for rtype, label in (
            (RequirementType.FUNCTIONAL, "기능 구현"),
            (RequirementType.NON_FUNCTIONAL, "비기능 구현"),
            (RequirementType.CONSTRAINT, "제약 대응"),
        ):
            reqs = grouped.get(rtype, [])
            if not reqs:
                continue
            n += 1
            act = f"2.{n}"
            items.append(
                WbsItemDraft(
                    code=act,
                    parent_code="2",
                    level="activity",
                    name=label,
                    estimate_basis="하위 Task 합계",
                )
            )
            for i, r in enumerate(reqs, start=1):
                md = DEFAULT_EFFORT_BY_TYPE[rtype]
                items.append(
                    WbsItemDraft(
                        code=f"{act}.{i}",
                        parent_code=act,
                        level="task",
                        name=f"{r.id} {r.name}"[:60],
                        description=r.description[:200],
                        effort_md_estimate=float(md),
                        estimate_basis=f"기본값 {md} M/D ({rtype.label} 요구사항 표준 공수, 검토 필요)",
                        roles=ROLE_BY_TYPE[rtype],
                        related_requirement_ids=[r.id],
                    )
                )
        items.append(
            WbsItemDraft(code="3", level="phase", name="시험·이행", estimate_basis="단계 합계")
        )
        items.append(
            WbsItemDraft(
                code="3.1",
                parent_code="3",
                level="activity",
                name="통합시험·이행",
                estimate_basis="구현 공수의 25%",
                effort_md_estimate=round(
                    sum(float(DEFAULT_EFFORT_BY_TYPE[r.type]) for r in requirements) * 0.25, 1
                )
                or 1.0,
                roles=[{"role": "QA", "ratio": "0.6"}, {"role": "백엔드", "ratio": "0.4"}],
                related_requirement_ids=[r.id for r in requirements],
            )
        )
        deps.append({"predecessor_code": "1", "successor_code": "2", "type": "FS", "lag_days": 0})
        deps.append({"predecessor_code": "2", "successor_code": "3", "type": "FS", "lag_days": 0})
        return WBSDraft(
            items=items,
            dependencies=[
                {
                    "predecessor_code": d["predecessor_code"],
                    "successor_code": d["successor_code"],
                    "type": d["type"],
                    "lag_days": d["lag_days"],
                }
                for d in deps
            ],
            assumptions=[f"역할 분류·공수는 코드 기본값 ({', '.join(p[1] for p in phases)})"],
            risks=["공수 기본값은 실제 생산성으로 검증되지 않음"],
        )

    # --- 계산·저장 -------------------------------------------------------------------------
    def build_plan(
        self,
        project: Project,
        draft: WBSDraft | None,
        analysis: dict[str, Any] | None,
        *,
        actor: str = "user",
    ) -> PlanResult:
        requirements = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
        ]
        result = PlanResult()
        if draft is None:
            draft = self.default_draft(requirements)
            result.auto_generated = True
            result.review_notes.append(
                "WBS·공수가 코드 기본값으로 생성되었습니다. 산정 근거를 검토하십시오."
            )
        missing_basis = [i.code for i in draft.items if not i.estimate_basis.strip()]
        if missing_basis:
            raise ValidationError(
                "산정 근거가 없는 WBS 항목이 있습니다.",
                cause=", ".join(missing_basis),
                resolution="모든 항목에 estimate_basis를 적으십시오.",
            )
        period = self.resolve_period(project, analysis)
        result.period = period
        calendar = self.calendar()

        code_to_effort = {i.code: Decimal(str(i.effort_md_estimate)) for i in draft.items}
        parent_of = {i.code: i.parent_code for i in draft.items}
        totals = rollup(code_to_effort, parent_of)
        children = {c for c in parent_of.values() if c}
        nodes = [
            TaskNode(
                i.code,
                i.parent_code,
                i.name,
                duration_days_for(code_to_effort[i.code], self._concurrency(i))
                if i.code not in children
                else 1,
            )
            for i in draft.items
        ]
        edges = [
            DepEdge(d.predecessor_code, d.successor_code, DependencyType(d.type), d.lag_days)
            for d in draft.dependencies
        ]
        schedule = compute_schedule(
            nodes, edges, project_start=period.start, project_end=period.end, calendar=calendar
        )
        result.schedule = schedule
        if not schedule.ok:
            raise ValidationError(
                "WBS 검증 실패",
                cause="; ".join(schedule.errors),
                resolution="WBS 코드·의존 관계를 수정하십시오.",
            )
        result.review_notes.extend(schedule.warnings)

        # 저장 (파생 데이터 교체)
        for repo in (
            self._repos.allocations,
            self._repos.dependencies,
            self._repos.wbs,
            self._repos.staff_roles,
        ):
            repo.clear_project(project.id)
        preds = {d.successor_code for d in draft.dependencies}
        succs = {d.predecessor_code for d in draft.dependencies}
        by_code: dict[str, WBSItem] = {}
        for order, d in enumerate(draft.items):
            work_type = (
                WorkType.PREDECESSOR
                if d.code in succs and d.code not in preds
                else WorkType.SUCCESSOR
                if d.code in preds
                else WorkType.STANDALONE
            )
            role_names = [str(r.get("role", "")) for r in d.roles if r.get("role")]
            item = WBSItem(
                project_id=project.id,
                code=d.code,
                level=WBSLevel(d.level),
                name=d.name,
                description=d.description,
                related_requirement_ids=d.related_requirement_ids,
                role=", ".join(role_names),
                category=d.category,
                organization=d.organization,
                assignee=d.assignee,
                quantity=d.quantity,
                work_type=work_type,
                planned_start=schedule.starts.get(d.code),
                planned_end=schedule.ends.get(d.code),
                duration_days=calendar.business_days_between(
                    schedule.starts[d.code], schedule.ends[d.code]
                )
                if d.code in schedule.starts
                else None,
                effort_md=totals[d.code],
                estimate_basis=d.estimate_basis,
                deliverable_names=d.deliverables,
                roles=d.roles,
                order=order,
                auto_generated=result.auto_generated,
                created_by=actor,
            )
            by_code[d.code] = item
        for d in draft.items:
            if d.parent_code:
                by_code[d.code].parent_id = by_code[d.parent_code].id
        for item in by_code.values():
            self._repos.wbs.insert(item)
            result.items.append(item)
        # 보고용 마일스톤 (코드 '0' 단계 아래, 공수 0·1일). 에이전트가 주지 않으면 기본값(검토 필요)
        milestone_items = self._milestone_items(
            project,
            draft.milestones or [MilestoneDraft(name=n, timing=t) for n, t in DEFAULT_MILESTONES],
            period,
            schedule,
            calendar,
            actor=actor,
            auto=not draft.milestones,
        )
        for item in milestone_items:
            self._repos.wbs.insert(item)
            result.items.append(item)
        if not draft.milestones:
            result.review_notes.append(
                "보고용 마일스톤(착수·착수보고·중간보고·완료보고·종료)은 코드 기본값입니다. 고객 보고 일정에 맞춰 조정하십시오."
            )
        for e in draft.dependencies:
            dep = Dependency(
                project_id=project.id,
                predecessor_id=by_code[e.predecessor_code].id,
                successor_id=by_code[e.successor_code].id,
                type=DependencyType(e.type),
                lag_days=e.lag_days,
                created_by=actor,
            )
            self._repos.dependencies.insert(dep)
            result.dependencies.append(dep)

        # 인력: leaf 작업별 역할 분배 → 월별 집계
        leaf_allocs: list[tuple[str, str, Decimal, date, date]] = []
        for d in draft.items:
            if d.code in children:
                continue
            item = by_code[d.code]
            if item.planned_start is None or item.planned_end is None:
                continue
            for role, md in split_by_ratio(code_to_effort[d.code], d.roles).items():
                if md > 0:
                    leaf_allocs.append((d.code, role, md, item.planned_start, item.planned_end))
        loads = aggregate_roles(leaf_allocs, calendar)
        result.role_loads = loads
        catalog = dict(DEFAULT_ROLE_CATALOG)
        team = {t.role: t for t in draft.team}
        role_records: dict[str, StaffRole] = {}
        for name in [*loads, *[r for r in team if r not in loads]]:
            load = loads.get(name)
            t = team.get(name)
            # 수행 조직(에이전트 team)이 있으면 조직·등급·인원·구성원을 쓰고, 부하로 계산한 필요 인원보다 적으면 경고
            headcount = (load.headcount if load else 0) or 1
            if t is not None:
                if load and t.headcount < load.headcount:
                    result.review_notes.append(
                        f"역할 '{name}' 투입 인원 {t.headcount}명이 월 최대 부하 기준 필요 인원 {load.headcount}명보다 적습니다."
                    )
                headcount = max(t.headcount, 1)
            rec = StaffRole(
                project_id=project.id,
                role_name=name,
                organization=t.organization if t else "수행사",
                grade=(t.grade if t and t.grade and t.grade != "미정" else None),
                skills=list(t.skills) if t else [],
                duties=(t.duties if t and t.duties else catalog.get(name, "")),
                headcount_planned=headcount,
                members=[t.name] if t and t.name else [],
                notes=("단가 미입력 — 비용 미계산" if name else "")
                + ("" if load else "; WBS 배분 공수 없음(조직 구성에만 있음)"),
                created_by=actor,
            )
            self._repos.staff_roles.insert(rec)
            role_records[name] = rec
            result.roles.append(rec)
        from proposal_agent.planning.staffing import distribute_by_month

        for code, role, md, start, end in leaf_allocs:
            monthly = distribute_by_month(md, start, end, calendar)
            alloc = StaffingAllocation(
                project_id=project.id,
                wbs_item_id=by_code[code].id,
                staff_role_id=role_records[role].id,
                start=start,
                end=end,
                allocation_ratio=1.0,
                effort_md=md,
                monthly_md={k: str(v) for k, v in monthly.items()},
                estimate_basis=f"{by_code[code].estimate_basis} × 역할 비율",
                created_by=actor,
            )
            self._repos.allocations.insert(alloc)
            result.allocations.append(alloc)
        result.total_effort_md = sum(
            (totals[c] for c in parent_of if parent_of[c] is None), Decimal("0")
        )
        self._audit.record(
            project.id,
            "plan.built",
            actor=actor,
            payload={
                "items": len(result.items),
                "deps": len(result.dependencies),
                "roles": list(loads),
                "total_md": str(result.total_effort_md),
                "period": [str(period.start), str(period.end), period.source],
                "auto": result.auto_generated,
                "warnings": schedule.warnings,
            },
        )
        return result

    def _milestone_items(
        self,
        project: Project,
        drafts: list[MilestoneDraft],
        period: ProjectPeriod,
        schedule: ScheduleResult,
        calendar: BusinessCalendar,
        *,
        actor: str,
        auto: bool,
    ) -> list[WBSItem]:
        """마일스톤을 코드 '0'(사업관리) 단계와 '0.n' 항목으로 만든다. 날짜는 timing 표기로 계산한다."""
        dated: list[tuple[str, date]] = []
        for m in drafts:
            d = milestone_date(
                m.timing,
                start=period.start,
                end=period.end,
                ends_by_code=schedule.ends,
                calendar=calendar,
            )
            if d is None:
                log.warning("마일스톤 '%s' 시점 '%s'을 해석하지 못해 제외", m.name, m.timing)
                continue
            dated.append((m.name, d))
        if not dated:
            return []
        dated.sort(key=lambda x: x[1])
        phase = WBSItem(
            project_id=project.id,
            code=MILESTONE_PHASE_CODE,
            level=WBSLevel.PHASE,
            name=MILESTONE_PHASE_NAME,
            description="고객 보고·검수 시점 (보고용 WBS 첫 행)",
            role="PM",
            organization="수행사",
            planned_start=dated[0][1],
            planned_end=dated[-1][1],
            duration_days=calendar.business_days_between(dated[0][1], dated[-1][1]),
            effort_md=Decimal("0"),
            estimate_basis="마일스톤(공수 없음)",
            milestone=True,
            order=-100,
            auto_generated=auto,
            notes="코드 기본값 — 검토 필요" if auto else "",
            created_by=actor,
        )
        items = [phase]
        for i, (name, d) in enumerate(dated, start=1):
            items.append(
                WBSItem(
                    project_id=project.id,
                    code=f"{MILESTONE_PHASE_CODE}.{i}",
                    parent_id=phase.id,
                    level=WBSLevel.ACTIVITY,
                    name=name,
                    role="PM",
                    organization="수행사",
                    planned_start=d,
                    planned_end=d,
                    duration_days=calendar.business_days_between(d, d),
                    effort_md=Decimal("0"),
                    estimate_basis="마일스톤(공수 없음)",
                    milestone=True,
                    order=-100 + i,
                    auto_generated=auto,
                    created_by=actor,
                )
            )
        return items

    @staticmethod
    def _concurrency(item: WbsItemDraft) -> float:
        total = 0.0
        for r in item.roles:
            try:
                total += float(r.get("ratio", "1"))
            except ValueError:
                total += 1.0
        return max(total, 1.0) if item.roles else 1.0

    # --- 조회 ------------------------------------------------------------------------------
    def plan_missing(self, project: Project) -> bool:
        """WBS 가 아직 없는가 (단계 7 분해 전에 오케스트레이터가 계획을 먼저 세운다)."""
        return not self._repos.wbs.tree(project.id)

    def rebuild_allocations(self, project: Project, *, holidays: str | None = None) -> int:
        """WBS leaf Task 의 역할·공수·일정으로 월별 투입을 다시 만든다 (WBS 분해·변경 뒤 투입계획 갱신). 배정 수를 돌려준다."""
        from proposal_agent.models import StaffingAllocation, StaffRole
        from proposal_agent.models.planning import TaskStatus
        from proposal_agent.planning.staffing import distribute_by_month

        self._repos.allocations.clear_project(project.id)
        roles = {r.role_name: r for r in self._repos.staff_roles.find(project.id)}
        calendar = BusinessCalendar(
            parse_holidays(holidays if holidays is not None else self._settings.holidays)
        )
        items = self._repos.wbs.tree(project.id)
        parents = {w.parent_id for w in items if w.parent_id}
        count = 0
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
                    notes="WBS 분해·변경 반영 시 추가된 역할 — 등급·단가 입력 필요",
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
            count += 1
        return count

    def current_plan(
        self, project: Project
    ) -> tuple[list[WBSItem], list[Dependency], list[StaffRole], list[StaffingAllocation]]:
        return (
            self._repos.wbs.tree(project.id),
            self._repos.dependencies.find(project.id),
            self._repos.staff_roles.find(project.id),
            self._repos.allocations.find(project.id),
        )

    def set_unit_cost(
        self, project: Project, role_id: str, unit_cost_per_mm: Decimal | None, *, actor: str
    ) -> StaffRole:
        rec = self._repos.staff_roles.get(role_id)
        rec.unit_cost_per_mm = unit_cost_per_mm
        rec.notes = "" if unit_cost_per_mm is not None else "단가 미입력 — 비용 미계산"
        self._repos.staff_roles.update(rec)
        self._audit.record(
            project.id,
            "plan.unit_cost_set",
            actor=actor,
            entity_type="StaffRole",
            entity_id=rec.id,
            payload={
                "unit_cost_per_mm": str(unit_cost_per_mm) if unit_cost_per_mm is not None else None
            },
        )
        return rec
