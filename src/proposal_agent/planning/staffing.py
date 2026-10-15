"""인력 투입 계획 계산 (결정적).

- 작업별 역할 공수를 작업 기간의 영업일에 균등 분배해 월별 M/D를 만든다.
- 역할별 월별 M/M, 필요 인원(월 최대 M/M 올림), 전체 합계를 낸다.
- 단가가 있는 역할만 비용을 계산한다. 단가가 없으면 비용은 None(입력란 제공).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from proposal_agent.planning.calendar import BusinessCalendar
from proposal_agent.planning.effort import md_to_mm

DEFAULT_ROLE_CATALOG: tuple[tuple[str, str], ...] = (
    ("PM", "사업 관리·일정·품질 총괄"),
    ("PL", "분석·설계 리드"),
    ("분석", "요구사항 분석·업무 설계"),
    ("아키텍트", "아키텍처·기술 설계"),
    ("백엔드", "서버·API 개발"),
    ("프런트엔드", "화면 개발"),
    ("DB", "데이터 모델링·DB 구축"),
    ("연계", "외부 시스템 인터페이스"),
    ("인프라", "서버·네트워크·클라우드"),
    ("보안", "보안 설계·점검"),
    ("QA", "테스트·품질"),
    ("DevOps", "배포·운영 자동화"),
)


@dataclass
class RoleLoad:
    role: str
    monthly_md: dict[str, Decimal] = field(default_factory=dict)
    total_md: Decimal = Decimal("0")
    start: date | None = None
    end: date | None = None
    headcount: int = 0
    task_codes: list[str] = field(default_factory=list)

    @property
    def total_mm(self) -> Decimal:
        return md_to_mm(self.total_md)

    def monthly_mm(self) -> dict[str, Decimal]:
        return {m: md_to_mm(v) for m, v in sorted(self.monthly_md.items())}


def distribute_by_month(
    effort_md: Decimal, start: date, end: date, calendar: BusinessCalendar
) -> dict[str, Decimal]:
    days = calendar.business_days_by_month(start, end)
    total_days = sum(days.values())
    if total_days == 0:
        return {f"{start.year:04d}-{start.month:02d}": Decimal(str(effort_md))}
    out: dict[str, Decimal] = {}
    allocated = Decimal("0")
    months = sorted(days)
    for i, month in enumerate(months):
        if i == len(months) - 1:
            share = Decimal(str(effort_md)) - allocated
        else:
            share = (Decimal(str(effort_md)) * Decimal(days[month]) / Decimal(total_days)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            allocated += share
        out[month] = share
    return out


def aggregate_roles(
    allocations: list[tuple[str, str, Decimal, date, date]], calendar: BusinessCalendar
) -> dict[str, RoleLoad]:
    """(task_code, role, effort_md, start, end) 목록 → 역할별 부하."""
    loads: dict[str, RoleLoad] = {}
    for code, role, md, start, end in allocations:
        load = loads.setdefault(role, RoleLoad(role=role))
        for month, share in distribute_by_month(md, start, end, calendar).items():
            load.monthly_md[month] = load.monthly_md.get(month, Decimal("0")) + share
        load.total_md += Decimal(str(md))
        load.start = start if load.start is None else min(load.start, start)
        load.end = end if load.end is None else max(load.end, end)
        load.task_codes.append(code)
    for load in loads.values():
        peak_mm = max((md_to_mm(v) for v in load.monthly_md.values()), default=Decimal("0"))
        load.headcount = (
            max(1, int(peak_mm.to_integral_value(rounding="ROUND_CEILING")))
            if load.total_md > 0
            else 0
        )
    return loads


def cost_for(total_mm: Decimal, unit_cost_per_mm: Decimal | None) -> Decimal | None:
    if unit_cost_per_mm is None:
        return None
    return (total_mm * unit_cost_per_mm).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
