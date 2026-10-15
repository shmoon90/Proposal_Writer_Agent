"""선후행 검증과 일정 계산 (결정적).

- 입력: 작업 노드(코드·기간·부모)와 의존 관계(FS/SS/FF/SF + lag). 날짜는 계산 결과다.
- 검증: 미존재 참조, 자기 참조, 순환, 3단계 초과, 기간 0.
- 전진 계산: 위상 순서로 leaf 작업의 시작·종료를 정하고, 상위 항목은 자식의 min/max.
- 검사: 전체 기간 초과, 명시 날짜와 의존 관계 충돌.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from proposal_agent.models.enums import DependencyType
from proposal_agent.planning.calendar import BusinessCalendar

MAX_DEPTH = 3


@dataclass
class TaskNode:
    code: str
    parent_code: str | None
    name: str
    duration_days: int = 1  # 영업일
    fixed_start: date | None = None  # UI 등에서 명시한 날짜 (있으면 우선, 충돌 검사 대상)
    fixed_end: date | None = None


@dataclass
class DepEdge:
    predecessor: str
    successor: str
    type: DependencyType = DependencyType.FS
    lag_days: int = 0


@dataclass
class ScheduleResult:
    starts: dict[str, date] = field(default_factory=dict)
    ends: dict[str, date] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    project_end_exceeded: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def depth_of(code: str) -> int:
    return code.count(".") + 1


def validate_structure(nodes: list[TaskNode], deps: list[DepEdge]) -> list[str]:
    errors: list[str] = []
    codes = {n.code for n in nodes}
    if len(codes) != len(nodes):
        errors.append("중복 WBS 코드가 있습니다.")
    for n in nodes:
        if n.parent_code is not None and n.parent_code not in codes:
            errors.append(f"{n.code}: 상위 코드 {n.parent_code} 없음")
        if depth_of(n.code) > MAX_DEPTH:
            errors.append(f"{n.code}: WBS 단계가 {MAX_DEPTH}단계를 초과")
        if n.duration_days < 1:
            errors.append(f"{n.code}: 기간은 1일 이상이어야 함")
    for d in deps:
        if d.predecessor not in codes or d.successor not in codes:
            errors.append(f"의존 참조 오류: {d.predecessor} → {d.successor}")
        elif d.predecessor == d.successor:
            errors.append(f"자기 참조 의존: {d.predecessor}")
    return errors


def topological_order(codes: list[str], deps: list[DepEdge]) -> tuple[list[str], list[str]]:
    """Kahn 알고리즘. 순환이 있으면 (부분 순서, 순환에 포함된 코드 목록)."""
    indeg = dict.fromkeys(codes, 0)
    adj: dict[str, list[str]] = {c: [] for c in codes}
    for d in deps:
        if d.predecessor in adj and d.successor in indeg:
            adj[d.predecessor].append(d.successor)
            indeg[d.successor] += 1
    queue = [c for c in codes if indeg[c] == 0]
    order: list[str] = []
    while queue:
        c = queue.pop(0)
        order.append(c)
        for nxt in adj[c]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    cyclic = [c for c in codes if c not in order]
    return order, cyclic


def compute_schedule(
    nodes: list[TaskNode],
    deps: list[DepEdge],
    *,
    project_start: date,
    project_end: date | None,
    calendar: BusinessCalendar,
) -> ScheduleResult:
    result = ScheduleResult()
    result.errors.extend(validate_structure(nodes, deps))
    if result.errors:
        return result

    by_code = {n.code: n for n in nodes}
    children: dict[str, list[str]] = {n.code: [] for n in nodes}
    for n in nodes:
        if n.parent_code:
            children[n.parent_code].append(n.code)
    leaves = [n.code for n in nodes if not children[n.code]]

    # 의존은 leaf 사이에서만 계산한다 (상위 항목 의존은 그 자식 leaf 전체로 확장)
    def expand(code: str) -> list[str]:
        return [code] if not children[code] else [c for ch in children[code] for c in expand(ch)]

    leaf_deps: list[DepEdge] = []
    for d in deps:
        for p in expand(d.predecessor):
            for s in expand(d.successor):
                if p != s:
                    leaf_deps.append(DepEdge(p, s, d.type, d.lag_days))

    order, cyclic = topological_order(leaves, leaf_deps)
    if cyclic:
        result.errors.append(f"순환 의존성: {', '.join(sorted(cyclic))}")
        return result
    result.order = order

    preds: dict[str, list[DepEdge]] = {c: [] for c in leaves}
    for d in leaf_deps:
        preds[d.successor].append(d)

    for code in order:
        node = by_code[code]
        dur = node.duration_days
        start = calendar.next_business_day(project_start)
        end: date | None = None
        for d in preds[code]:
            ps, pe = result.starts[d.predecessor], result.ends[d.predecessor]
            if d.type == DependencyType.FS:
                cand = calendar.offset(pe, 1 + d.lag_days)
                start = max(start, cand)
            elif d.type == DependencyType.SS:
                start = max(start, calendar.offset(ps, d.lag_days))
            elif d.type == DependencyType.FF:
                e = calendar.offset(pe, d.lag_days)
                end = e if end is None else max(end, e)
            elif d.type == DependencyType.SF:
                e = calendar.offset(ps, d.lag_days)
                end = e if end is None else max(end, e)
        if end is not None:
            # FF/SF로 종료가 당겨지면 시작을 역산하되 다른 제약보다 늦게 끝나야 한다
            start_from_end = calendar.offset(end, -(dur - 1))
            start = max(start, start_from_end)
        if node.fixed_start is not None:
            if node.fixed_start < start:
                result.warnings.append(
                    f"{code}: 명시 시작일 {node.fixed_start}이 선행 작업 제약({start})과 충돌"
                )
            start = calendar.next_business_day(node.fixed_start)
        computed_end = calendar.add_business_days(start, dur)
        if node.fixed_end is not None:
            if node.fixed_end < computed_end:
                result.warnings.append(
                    f"{code}: 명시 종료일 {node.fixed_end}이 기간({dur}일)보다 짧음"
                )
            computed_end = max(computed_end, calendar.next_business_day(node.fixed_end))
        result.starts[code] = start
        result.ends[code] = computed_end

    # 상위 항목 롤업 (깊은 것부터)
    for n in sorted(nodes, key=lambda x: -depth_of(x.code)):
        if children[n.code]:
            kids = [c for c in children[n.code] if c in result.starts]
            if kids:
                result.starts[n.code] = min(result.starts[c] for c in kids)
                result.ends[n.code] = max(result.ends[c] for c in kids)

    if project_end is not None:
        latest = max(result.ends.values()) if result.ends else project_start
        if latest > project_end:
            result.project_end_exceeded = True
            result.warnings.append(f"전체 기간 초과: 계획 종료 {latest} > 과제 종료 {project_end}")
    return result
