"""인력 투입계획 Excel: 투입계획(역할·등급·기술·인원·담당·기간·MM·월별·근거·단가·비용), 공수요약, 월별투입.

단가가 없으면 비용을 계산하지 않고 단가 입력란을 비워 둔다. 공수는 WBS 배분과 동일한 Decimal 값이다.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.excel.style import add_note, write_table
from proposal_agent.models import StaffRole
from proposal_agent.planning.calendar import BusinessCalendar
from proposal_agent.planning.effort import md_to_mm
from proposal_agent.planning.staffing import cost_for

SHEET_PLAN = "투입계획"
SHEET_SUMMARY = "공수요약"
SHEET_MONTHLY = "월별투입"


@dataclass
class RoleAgg:
    role: StaffRole
    md: Decimal = Decimal("0")
    monthly: dict[str, Decimal] = field(default_factory=dict)
    start: date | None = None
    end: date | None = None
    tasks: list[str] = field(default_factory=list)


def _aggregate(ctx: GenerationContext) -> tuple[dict[str, RoleAgg], list[str]]:
    roles = ctx.roles_by_id
    by_role: dict[str, RoleAgg] = {}
    months: set[str] = set()
    for a in ctx.allocations:
        role = roles.get(a.staff_role_id)
        if role is None:
            continue
        agg = by_role.setdefault(role.id, RoleAgg(role=role, start=a.start, end=a.end))
        agg.md += a.effort_md
        for m, v in a.monthly_md.items():
            agg.monthly[m] = agg.monthly.get(m, Decimal("0")) + Decimal(v)
            months.add(m)
        if a.start and (agg.start is None or a.start < agg.start):
            agg.start = a.start
        if a.end and (agg.end is None or a.end > agg.end):
            agg.end = a.end
        w = ctx.wbs_by_id.get(a.wbs_item_id)
        if w:
            agg.tasks.append(w.code)
    return by_role, sorted(months)


def build_staffing_plan(ctx: GenerationContext) -> bytes:
    by_role, month_list = _aggregate(ctx)
    calendar = BusinessCalendar()
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_PLAN
    headers = [
        "조직",
        "역할",
        "기술 등급",
        "필요 기술",
        "투입 인원",
        "담당 업무",
        "투입 시작일",
        "투입 종료일",
        "투입 기간(영업일)",
        "예상 공수(MM)",
        "예상 공수(M/D)",
        *month_list,
        "산정 근거",
        "단가(원/MM, 입력)",
        "비용 합계(원)",
        "비고",
    ]
    rows: list[list[object]] = []
    total_md = Decimal("0")
    for agg in by_role.values():
        role = agg.role
        total_md += agg.md
        mm = md_to_mm(agg.md)
        duration = (
            calendar.business_days_between(agg.start, agg.end) if agg.start and agg.end else None
        )
        cost = cost_for(mm, role.unit_cost_per_mm)
        rows.append(
            [
                role.organization or "수행사",
                role.role_name,
                role.grade or "미정",
                ", ".join(role.skills),
                role.headcount_planned,
                role.duties,
                agg.start,
                agg.end,
                duration,
                float(mm),
                float(agg.md),
                *[float(md_to_mm(agg.monthly.get(m, Decimal("0")))) for m in month_list],
                f"WBS {', '.join(sorted(set(agg.tasks)))[:80]} 역할 배분 합계",
                float(role.unit_cost_per_mm) if role.unit_cost_per_mm is not None else None,
                float(cost) if cost is not None else None,
                role.notes
                or ("단가 입력 시 비용 자동 계산" if role.unit_cost_per_mm is None else ""),
            ]
        )
    widths = [10, 12, 10, 20, 8, 28, 12, 12, 10, 10, 10, *[8] * len(month_list), 40, 14, 14, 24]
    fmt: dict[int, str] = {10: "0.00", 11: "0.0"}
    for i in range(len(month_list)):
        fmt[12 + i] = "0.00"
    unit_col = len(headers) - 2
    cost_col = len(headers) - 1
    fmt[unit_col] = "#,##0"
    fmt[cost_col] = "#,##0"
    last = write_table(
        ws,
        headers,
        rows,
        widths=widths,
        validations={3: ("특급", "고급", "중급", "초급", "미정")},
        number_formats=fmt,
    )
    unit_letter = get_column_letter(unit_col)
    for r in range(2, last + 1):  # 단가 × MM, 단가가 비어 있으면 빈 값
        ws.cell(row=r, column=cost_col, value=f'=IF({unit_letter}{r}="","",{unit_letter}{r}*J{r})')
    add_note(
        ws,
        last + 2,
        f"총 공수 {float(total_md):.1f} M/D = {float(md_to_mm(total_md)):.2f} MM (1 MM = 20 M/D 가정). 단가 미입력 시 비용은 계산하지 않음.",
    )

    ws2 = wb.create_sheet(SHEET_SUMMARY)
    sum_rows: list[list[object]] = [
        [agg.role.role_name, agg.role.headcount_planned, float(agg.md), float(md_to_mm(agg.md))]
        for agg in by_role.values()
    ]
    sum_rows.append(
        [
            "합계",
            sum(agg.role.headcount_planned for agg in by_role.values()),
            float(total_md),
            float(md_to_mm(total_md)),
        ]
    )
    write_table(
        ws2,
        ("역할", "투입 인원", "공수(M/D)", "공수(MM)"),
        sum_rows,
        widths=(14, 10, 12, 12),
        number_formats={3: "0.0", 4: "0.00"},
    )
    add_note(
        ws2, len(sum_rows) + 3, "합계는 WBS 산정근거 시트의 총 공수와 같아야 한다 (QA에서 검증)."
    )

    ws3 = wb.create_sheet(SHEET_MONTHLY)
    m_rows: list[list[object]] = [
        [
            agg.role.role_name,
            *[float(md_to_mm(agg.monthly.get(m, Decimal("0")))) for m in month_list],
        ]
        for agg in by_role.values()
    ]
    m_rows.append(
        [
            "합계",
            *[
                float(
                    md_to_mm(
                        sum(
                            (agg.monthly.get(m, Decimal("0")) for agg in by_role.values()),
                            Decimal("0"),
                        )
                    )
                )
                for m in month_list
            ],
        ]
    )
    write_table(
        ws3,
        ("역할(MM)", *month_list),
        m_rows,
        widths=(14, *[9] * len(month_list)),
        number_formats={i + 2: "0.00" for i in range(len(month_list))},
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
