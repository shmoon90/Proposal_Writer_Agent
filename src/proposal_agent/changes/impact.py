"""WBS·일정·공수·인력 영향 시뮬레이션 (코드 계산, 기준 데이터는 바꾸지 않는다).

- 기존 Task 재사용/수정/신규/제거를 판단하고, 변경 전후 일정을 같은 방식(scheduler)으로 계산해 비교한다.
  기존 Task는 계획 시작일을 '그보다 빠르지 않게'(earliest_start)로 두어 여유(slack)가 있으면 후행이 밀리지 않는다.
- 공수는 변경 전·추가·감소·순증·변경 후를 근거와 함께 내고, 불확실하면 범위로 표시한다.
- 인력 시나리오 1~6 판정. 투입계획이 없으면 6(사용자 판단)으로 두고 인력 조정을 단정하지 않는다.
- 순환 의존 등 계산 불가 사유가 있으면 ``error``에 기록하고 중단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from proposal_agent.changes.semantic import similarity
from proposal_agent.models import Dependency, Requirement, StaffRole, WBSItem
from proposal_agent.models.change import (
    CandidateClass,
    ChangeCandidate,
    ChangeImpact,
    EffortImpact,
    RoleImpact,
    StaffingScenario,
    TaskImpact,
)
from proposal_agent.planning.calendar import BusinessCalendar
from proposal_agent.planning.effort import md_to_mm
from proposal_agent.planning.scheduler import DepEdge, ScheduleResult, TaskNode, compute_schedule
from proposal_agent.planning.staffing import RoleLoad, aggregate_roles

Q = Decimal("0.1")


def q(v: Decimal) -> Decimal:
    return v.quantize(Q, rounding=ROUND_HALF_UP)


@dataclass
class SimTask:
    code: str
    parent_code: str | None
    name: str
    role: str
    requirement_ids: list[str]
    duration: int
    effort_md: Decimal
    planned_start: date | None
    planned_end: date | None
    is_new: bool = False
    removed: bool = False
    item_id: str | None = None


@dataclass
class SimPlan:
    tasks: dict[str, SimTask] = field(default_factory=dict)
    deps: list[DepEdge] = field(default_factory=list)

    def leaves(self) -> list[SimTask]:
        parents = {t.parent_code for t in self.tasks.values() if t.parent_code}
        return [t for t in self.tasks.values() if t.code not in parents and not t.removed]

    def nodes(self, *, keep_dates: bool) -> list[TaskNode]:
        out = []
        parents = {t.parent_code for t in self.tasks.values() if t.parent_code}
        for t in self.tasks.values():
            if t.removed:
                continue
            leaf = t.code not in parents
            out.append(
                TaskNode(
                    t.code,
                    t.parent_code,
                    t.name,
                    max(1, t.duration) if leaf else 1,
                    earliest_start=t.planned_start
                    if (keep_dates and leaf and not t.is_new)
                    else None,
                )
            )
        return out

    def edges(self) -> list[DepEdge]:
        alive = {c for c, t in self.tasks.items() if not t.removed}
        return [d for d in self.deps if d.predecessor in alive and d.successor in alive]


def build_sim(wbs: list[WBSItem], deps: list[Dependency], calendar: BusinessCalendar) -> SimPlan:
    by_id = {w.id: w for w in wbs}
    plan = SimPlan()
    for w in wbs:
        dur = w.duration_days
        if (dur is None or dur <= 0) and w.planned_start and w.planned_end:
            dur = calendar.business_days_between(w.planned_start, w.planned_end)
        plan.tasks[w.code] = SimTask(
            code=w.code,
            parent_code=by_id[w.parent_id].code if w.parent_id and w.parent_id in by_id else None,
            name=w.name,
            role=w.role,
            requirement_ids=list(w.related_requirement_ids),
            duration=int(dur or 1),
            effort_md=Decimal(str(w.effort_md)),
            planned_start=w.planned_start,
            planned_end=w.planned_end,
            item_id=w.id,
        )
    for d in deps:
        p, s = by_id.get(d.predecessor_id), by_id.get(d.successor_id)
        if p and s:
            plan.deps.append(DepEdge(p.code, s.code, d.type, d.lag_days))
    return plan


def _next_code(parent_code: str | None, plan: SimPlan) -> str:
    siblings = [t.code for t in plan.tasks.values() if t.parent_code == parent_code]
    nums = []
    for c in siblings:
        try:
            nums.append(int(c.rsplit(".", 1)[-1]))
        except ValueError:
            continue
    n = (max(nums) + 1) if nums else 1
    return f"{parent_code}.{n}" if parent_code else str(n)


def _effort_estimate(
    cand: ChangeCandidate,
    similar: list[tuple[SimTask, float]],
    base_md: Decimal | None,
    *,
    share: int = 1,
) -> tuple[Decimal, Decimal, Decimal, str, str]:
    """(추정값, 최소, 최대, 상태, 근거). ``share``는 사용자 입력 공수를 나눠 받는 Task 수."""
    override = cand.user_override.get("effort_md")
    if override is not None:
        v = q(Decimal(str(override)) / Decimal(max(1, share)))
        return (
            v,
            v,
            v,
            "확정",
            "사용자 입력 공수" + (f" (Task {share}개 균등 분배)" if share > 1 else ""),
        )
    if cand.classification == CandidateClass.MODIFY and base_md is not None:
        ratio = Decimal(str(round(max(0.2, min(0.6, 1.0 - cand.similarity)), 2)))
        est = q(base_md * ratio)
        return (
            est,
            q(est * Decimal("0.5")),
            q(est * Decimal("1.5")),
            "범위",
            f"기존 Task 공수 {base_md} M/D × 변경 비율 {ratio} (유사도 기반 추정)",
        )
    if similar:
        vals = sorted(t.effort_md for t, _ in similar if t.effort_md > 0)
        if vals:
            mid = vals[len(vals) // 2]
            return (
                mid,
                vals[0],
                vals[-1],
                "범위",
                f"유사 Task {', '.join(t.code for t, _ in similar)} 공수 중앙값 (범위 {vals[0]}~{vals[-1]} M/D)",
            )
    return (
        Decimal("10"),
        Decimal("5"),
        Decimal("20"),
        "범위",
        "비교 가능한 Task가 없어 기본값(10 M/D, 범위 5~20) 적용 — 사용자 확인 필요",
    )


def analyze_impact(
    candidates: list[ChangeCandidate],
    *,
    requirements: list[Requirement],
    wbs: list[WBSItem],
    dependencies: list[Dependency],
    roles: list[StaffRole],
    staffing_plan_present: bool,
    project_start: date | None,
    project_end: date | None,
    calendar: BusinessCalendar,
) -> ChangeImpact:
    impact, after, sched_after = simulate(
        candidates,
        wbs=wbs,
        dependencies=dependencies,
        project_start=project_start,
        project_end=project_end,
        calendar=calendar,
    )
    if impact.error or sched_after is None:
        return impact
    before = build_sim(wbs, dependencies, calendar)
    starts = [t.planned_start for t in before.tasks.values() if t.planned_start]
    p_start = project_start or (min(starts) if starts else date.today())
    sched_before = compute_schedule(
        before.nodes(keep_dates=True),
        before.edges(),
        project_start=p_start,
        project_end=project_end,
        calendar=calendar,
    )
    _staffing(
        impact, before, after, sched_before, sched_after, roles, staffing_plan_present, calendar
    )
    return impact


def simulate(
    candidates: list[ChangeCandidate],
    *,
    wbs: list[WBSItem],
    dependencies: list[Dependency],
    project_start: date | None,
    project_end: date | None,
    calendar: BusinessCalendar,
) -> tuple[ChangeImpact, SimPlan, ScheduleResult | None]:
    """변경 후 계획(SimPlan)과 일정을 계산한다. 기준 데이터는 바꾸지 않는다."""
    impact = ChangeImpact(project_end=project_end)
    active = [
        c
        for c in candidates
        if c.classification
        in (CandidateClass.ADD, CandidateClass.MODIFY, CandidateClass.DELETE_REQUEST)
        and c.user_decision != "reject"
    ]
    after = build_sim(wbs, dependencies, calendar)
    if not wbs:
        impact.error = (
            "WBS가 없어 일정·공수 영향을 계산할 수 없습니다. 기준 WBS를 먼저 적재하십시오."
        )
        return impact, after, None
    before = build_sim(wbs, dependencies, calendar)
    starts = [t.planned_start for t in before.tasks.values() if t.planned_start]
    p_start = project_start or (min(starts) if starts else date.today())
    sched_before = compute_schedule(
        before.nodes(keep_dates=True),
        before.edges(),
        project_start=p_start,
        project_end=project_end,
        calendar=calendar,
    )
    if sched_before.errors:
        impact.error = "기준 WBS 일정 계산 불가: " + "; ".join(sched_before.errors)
        return impact, after, None

    added = Decimal("0")
    reduced = Decimal("0")
    rmin = Decimal("0")
    rmax = Decimal("0")
    statuses: set[str] = set()
    bases: list[str] = []
    leaves = before.leaves()

    for cand in active:
        rid = cand.requirement_id
        if cand.classification == CandidateClass.MODIFY and rid:
            tasks = [t for t in leaves if rid in t.requirement_ids]
            if not tasks:
                impact.warnings.append(f"{rid}: 연결된 WBS Task가 없어 신규 Task로 처리합니다.")
            for t in tasks:
                est, lo, hi, st, basis = _effort_estimate(cand, [], t.effort_md, share=len(tasks))
                at = after.tasks[t.code]
                at.effort_md = t.effort_md + est
                at.duration = t.duration + max(
                    1,
                    int((est / Decimal("1")).to_integral_value(rounding="ROUND_CEILING"))
                    // max(1, _concurrency(t)),
                )
                others = [r for r in t.requirement_ids if r != rid]
                impact.affected_requirement_ids.extend(
                    o for o in others if o not in impact.affected_requirement_ids
                )
                impact.tasks.append(
                    TaskImpact(
                        wbs_code=t.code,
                        task_name=t.name,
                        action="modify",
                        requirement_ids=t.requirement_ids,
                        effort_before_md=t.effort_md,
                        effort_added_md=est,
                        basis=basis
                        + (f"; 같은 Task를 쓰는 {', '.join(others)}도 영향" if others else ""),
                    )
                )
                added += est
                rmin += lo
                rmax += hi
                statuses.add(st)
                bases.append(f"{t.code}: {basis}")
                impact.tests_added.append(f"{t.code} 관련 단위·통합테스트 재검토 ({rid})")
            if not tasks:
                _add_new_task(cand, rid, after, leaves, impact, calendar)
                est = impact.tasks[-1].effort_added_md
                added += est
                rmin += est / 2
                rmax += est * 2
                statuses.add("범위")
                bases.append(f"{impact.tasks[-1].wbs_code}: {impact.tasks[-1].basis}")
        elif cand.classification == CandidateClass.ADD:
            new_id = cand.user_override.get("requirement_id") or f"NEW-{cand.id}"
            est, lo, hi, st = _add_new_task(cand, new_id, after, leaves, impact, calendar)
            added += est
            rmin += lo
            rmax += hi
            statuses.add(st)
            bases.append(f"{impact.tasks[-1].wbs_code}: {impact.tasks[-1].basis}")
        elif cand.classification == CandidateClass.DELETE_REQUEST and rid:
            tasks = [t for t in leaves if rid in t.requirement_ids]
            if not tasks:
                impact.warnings.append(
                    f"{rid}: 연결된 WBS Task가 없어 일정 영향 없음 (문서 상태만 '삭제'로 표시)"
                )
            for t in tasks:
                others = [r for r in t.requirement_ids if r != rid]
                at = after.tasks[t.code]
                if others:
                    share = q(t.effort_md / Decimal(len(t.requirement_ids)))
                    at.effort_md = t.effort_md - share
                    at.duration = max(1, t.duration - int(share))
                    impact.affected_requirement_ids.extend(
                        o for o in others if o not in impact.affected_requirement_ids
                    )
                    impact.tasks.append(
                        TaskImpact(
                            wbs_code=t.code,
                            task_name=t.name,
                            action="modify",
                            requirement_ids=t.requirement_ids,
                            effort_before_md=t.effort_md,
                            effort_reduced_md=share,
                            basis=f"{rid} 몫({share} M/D, 균등 분할)만 감소; {', '.join(others)}는 유지",
                        )
                    )
                    reduced += share
                else:
                    at.removed = True
                    impact.tasks.append(
                        TaskImpact(
                            wbs_code=t.code,
                            task_name=t.name,
                            action="remove",
                            requirement_ids=t.requirement_ids,
                            effort_before_md=t.effort_md,
                            effort_reduced_md=t.effort_md,
                            basis=f"{rid} 전용 Task — 제거 (보류 표시, 물리 삭제 없음)",
                        )
                    )
                    reduced += t.effort_md
                    # 제거 Task의 선행→후행을 이어 준다 (의존 끊김 방지)
                    preds = [d for d in after.deps if d.successor == t.code]
                    succs = [d for d in after.deps if d.predecessor == t.code]
                    for p in preds:
                        for s in succs:
                            after.deps.append(
                                DepEdge(p.predecessor, s.successor, s.type, s.lag_days)
                            )
                            impact.dependency_changes.append(
                                f"{p.predecessor}→{s.successor} (제거된 {t.code} 우회)"
                            )
                statuses.add("확정")
                bases.append(f"{t.code}: 기준 공수 {t.effort_md} M/D")

    sched_after = compute_schedule(
        after.nodes(keep_dates=True),
        after.edges(),
        project_start=p_start,
        project_end=project_end,
        calendar=calendar,
    )
    if sched_after.errors:
        impact.error = "변경 후 일정 계산 중단: " + "; ".join(sched_after.errors)
        impact.warnings.extend(sched_after.warnings)
        return impact, after, None
    impact.warnings.extend(w for w in sched_after.warnings if w not in sched_before.warnings)

    # Task별 날짜 전후 채우기
    for ti in impact.tasks:
        ti.before_start, ti.before_end = (
            sched_before.starts.get(ti.wbs_code),
            sched_before.ends.get(ti.wbs_code),
        )
        ti.after_start, ti.after_end = (
            sched_after.starts.get(ti.wbs_code),
            sched_after.ends.get(ti.wbs_code),
        )
    for code in sched_before.ends:
        if code in sched_after.ends and (
            sched_after.ends[code] != sched_before.ends[code]
            or sched_after.starts[code] != sched_before.starts[code]
        ):
            t = before.tasks[code]
            impact.changed_task_dates.append(
                f"{code} {t.name}: {sched_before.starts[code]}~{sched_before.ends[code]} → {sched_after.starts[code]}~{sched_after.ends[code]}"
            )
            for r in t.requirement_ids:
                if r not in impact.affected_requirement_ids and not any(
                    c.requirement_id == r for c in active
                ):
                    impact.affected_requirement_ids.append(r)
    top_before = [c for c, t in before.tasks.items() if t.parent_code is None]
    top_after = [c for c, t in after.tasks.items() if t.parent_code is None and not t.removed]
    impact.schedule_before_end = max(
        (sched_before.ends[c] for c in top_before if c in sched_before.ends), default=None
    )
    impact.schedule_after_end = max(
        (sched_after.ends[c] for c in top_after if c in sched_after.ends), default=None
    )
    if impact.schedule_before_end and impact.schedule_after_end:
        impact.schedule_delta_days = (
            calendar.business_days_between(impact.schedule_before_end, impact.schedule_after_end)
            - 1
            if impact.schedule_after_end > impact.schedule_before_end
            else 0
        )
    impact.project_end_exceeded = bool(
        project_end and impact.schedule_after_end and impact.schedule_after_end > project_end
    )
    if impact.project_end_exceeded:
        impact.warnings.append(
            f"변경 후 종료일 {impact.schedule_after_end}이 과제 종료일 {project_end}을 초과합니다."
        )
    elif project_end is None and impact.schedule_delta_days > 0:
        impact.warnings.append(
            "과제 종료일이 입력되지 않아 기간 초과 여부는 판단하지 않았습니다 (프로젝트 화면에서 종료일 입력)."
        )

    # 공수
    before_total = sum((t.effort_md for t in leaves), Decimal("0"))
    net = added - reduced
    status = (
        "확정" if statuses <= {"확정"} and statuses else ("범위" if "범위" in statuses else "추정")
    )
    impact.effort = EffortImpact(
        before_md=q(before_total),
        added_md=q(added),
        reduced_md=q(reduced),
        net_md=q(net),
        after_md=q(before_total + net),
        estimate_status=status,
        range_min_md=q(before_total + rmin - reduced) if status == "범위" else None,
        range_max_md=q(before_total + rmax - reduced) if status == "범위" else None,
        basis="; ".join(bases)[:1500],
        assumptions=[
            "1 M/D = 1인 1영업일, 1 MM = 20 M/D",
            "기존 Task 수정 공수는 유사도 기반 비율 추정 — 사용자 확정 가능",
            "신규 Task는 유사 Task 공수 중앙값 적용",
        ],
    )

    return impact, after, sched_after


def _concurrency(t: SimTask) -> int:
    return 1


def _add_new_task(
    cand: ChangeCandidate,
    req_id: str,
    after: SimPlan,
    leaves: list[SimTask],
    impact: ChangeImpact,
    calendar: BusinessCalendar,
) -> tuple[Decimal, Decimal, Decimal, str]:
    text = f"{cand.proposed_name} {cand.proposed_description}"
    scored = sorted(
        ((t, similarity(text, f"{t.name} {t.requirement_ids}")) for t in leaves if not t.removed),
        key=lambda x: x[1],
        reverse=True,
    )
    similar = [(t, s) for t, s in scored[:3] if s >= 0.2] or scored[:1]
    est, lo, hi, st, basis = _effort_estimate(cand, similar, None)
    anchor = similar[0][0] if similar else None
    parent = anchor.parent_code if anchor else None
    code = _next_code(parent, after)
    role = cand.user_override.get("role") or (anchor.role if anchor else "")
    dur = max(1, int(est.to_integral_value(rounding="ROUND_CEILING")))
    after.tasks[code] = SimTask(
        code=code,
        parent_code=parent,
        name=f"{cand.proposed_name} 개발",
        role=role,
        requirement_ids=[req_id],
        duration=dur,
        effort_md=est,
        planned_start=None,
        planned_end=None,
        is_new=True,
    )
    if anchor:
        # 유사 Task와 같은 선행을 갖고, 유사 Task의 후행(시험 등)은 새 Task도 기다린다
        for d in list(after.deps):
            if d.successor == anchor.code:
                after.deps.append(DepEdge(d.predecessor, code, d.type, d.lag_days))
            if d.predecessor == anchor.code:
                after.deps.append(DepEdge(code, d.successor, d.type, d.lag_days))
                impact.dependency_changes.append(
                    f"{code}→{d.successor} (기존 {anchor.code}의 후행을 신규 Task도 선행)"
                )
    impact.tasks.append(
        TaskImpact(
            wbs_code=code,
            task_name=f"{cand.proposed_name} 개발",
            action="add",
            requirement_ids=[req_id],
            effort_added_md=est,
            predecessors_changed=bool(anchor),
            basis=basis + (f"; 유사 Task {anchor.code} 기준 배치" if anchor else ""),
        )
    )
    impact.tests_added.append(f"{code} 단위테스트·통합테스트 신규 필요 ({req_id})")
    return est, lo, hi, st


def _role_loads(
    plan: SimPlan, sched: ScheduleResult, calendar: BusinessCalendar
) -> dict[str, RoleLoad]:
    rows: list[tuple[str, str, Decimal, date, date]] = []
    for t in plan.leaves():
        if t.code in sched.starts and t.effort_md > 0:
            rows.append(
                (
                    t.code,
                    t.role or "(미지정)",
                    t.effort_md,
                    sched.starts[t.code],
                    sched.ends[t.code],
                )
            )
    return aggregate_roles(rows, calendar)


def _staffing(
    impact: ChangeImpact,
    before: SimPlan,
    after: SimPlan,
    sb: ScheduleResult,
    sa: ScheduleResult,
    roles: list[StaffRole],
    present: bool,
    calendar: BusinessCalendar,
) -> None:
    impact.staffing_plan_present = present
    lb, la = _role_loads(before, sb, calendar), _role_loads(after, sa, calendar)
    plan_roles = {r.role_name: r for r in roles}
    names = sorted(set(lb) | set(la))
    new_roles: list[str] = []
    over: list[str] = []
    for n in names:
        b, a = lb.get(n), la.get(n)
        pr = plan_roles.get(n)
        ri = RoleImpact(
            role=n,
            exists_in_plan=pr is not None,
            before_mm=q(b.total_mm) if b else Decimal("0"),
            after_mm=q(a.total_mm) if a else Decimal("0"),
        )
        ri.delta_mm = q(ri.after_mm - ri.before_mm)
        ri.peak_month_before = (
            max(b.monthly_md, key=lambda m: b.monthly_md[m]) if b and b.monthly_md else None
        )
        ri.peak_month_after = (
            max(a.monthly_md, key=lambda m: a.monthly_md[m]) if a and a.monthly_md else None
        )
        ri.headcount_before = pr.headcount_planned if pr else (b.headcount if b else 0)
        ri.headcount_needed = a.headcount if a else 0
        impact.roles.append(ri)
        if a and a.total_md > 0 and pr is None and n != "(미지정)" and not (b and b.total_md > 0):
            new_roles.append(n)
        if pr and ri.headcount_needed > pr.headcount_planned:
            over.append(f"{n}: 필요 {ri.headcount_needed}명 > 계획 {pr.headcount_planned}명")
    net = impact.effort.net_md
    if not present or not roles:
        impact.staffing_scenario = StaffingScenario.S6_UNKNOWN
        impact.staffing_explanation = "인력 투입계획이 없어 인력 조정 가능 여부를 판단할 수 없습니다. 역할별 공수 변화만 제시하며, 새 투입계획 작성 여부는 사용자가 결정합니다."
        return
    if new_roles:
        impact.staffing_scenario = StaffingScenario.S4_NEW_ROLE
        impact.staffing_explanation = f"투입계획에 없는 역할이 필요합니다: {', '.join(new_roles)}."
    elif net <= 0:
        impact.staffing_scenario = StaffingScenario.S5_OFFSET
        impact.staffing_explanation = f"감소 공수({impact.effort.reduced_md} M/D)가 추가 공수({impact.effort.added_md} M/D) 이상이어서 기존 인력으로 상쇄 가능합니다."
    elif impact.schedule_delta_days == 0 and not over:
        impact.staffing_scenario = StaffingScenario.S1_EXISTING_OK
        impact.staffing_explanation = (
            "전체 종료일 변동 없음, 역할별 월 최대 투입이 계획 인원 이내입니다."
        )
    elif impact.schedule_delta_days == 0:
        impact.staffing_scenario = StaffingScenario.S2_RESCHEDULE
        impact.staffing_explanation = (
            "종료일은 유지되지만 일부 월에 계획 인원을 초과합니다: "
            + "; ".join(over)
            + ". 일정 재배치 또는 일시 증원 검토."
        )
    else:
        impact.staffing_scenario = StaffingScenario.S3_EXTEND
        impact.staffing_explanation = (
            f"전체 종료일이 {impact.schedule_delta_days} 영업일 늦어져 해당 역할의 투입 기간 연장이 필요합니다."
            + (" 월 초과: " + "; ".join(over) if over else "")
        )
    # 비용: 영향 역할 모두 단가가 있을 때만
    affected = [ri for ri in impact.roles if ri.delta_mm != 0]
    if affected and all(
        plan_roles.get(ri.role) and plan_roles[ri.role].unit_cost_per_mm is not None
        for ri in affected
    ):
        cb = sum(
            (
                ri.before_mm * (plan_roles[ri.role].unit_cost_per_mm or Decimal("0"))
                for ri in affected
            ),
            Decimal("0"),
        )
        ca = sum(
            (
                ri.after_mm * (plan_roles[ri.role].unit_cost_per_mm or Decimal("0"))
                for ri in affected
            ),
            Decimal("0"),
        )
        impact.cost_before, impact.cost_after, impact.cost_delta = (
            cb.quantize(Decimal("1")),
            ca.quantize(Decimal("1")),
            (ca - cb).quantize(Decimal("1")),
        )
    elif affected:
        impact.warnings.append(
            "영향 역할 중 단가가 없는 역할이 있어 비용 영향은 계산하지 않습니다 (공수만 제시)."
        )


def md_summary(md: Decimal) -> str:
    return f"{q(md)} M/D ({md_to_mm(md)} MM)"
