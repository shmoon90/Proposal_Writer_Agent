"""WBS·간트 차트 Excel: WBS(필수 컬럼 17종), 간트(주 단위 셀 채움, WBS 데이터와 동일 날짜), 의존관계, 산정근거."""

from __future__ import annotations

import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.excel.style import (
    BODY_FONT,
    BORDER,
    CENTER,
    HEADER_FILL,
    HEADER_FONT,
    add_note,
    write_table,
)
from proposal_agent.models import TaskStatus, WorkType

SHEET_WBS = "WBS"
SHEET_GANTT = "간트"
SHEET_DEPS = "의존관계"
SHEET_BASIS = "산정근거"
HEADERS = (
    "WBS ID",
    "상위 WBS ID",
    "요구사항 ID",
    "Task 명",
    "Task 상세 내용",
    "담당 역할",
    "선행 업무",
    "후행 업무",
    "업무 유형",
    "계획 시작일",
    "계획 종료일",
    "실제 시작일",
    "실제 종료일",
    "기간(영업일)",
    "진행 상태",
    "산정 근거",
    "공수(M/D)",
    "비고",
)
WIDTHS = (10, 10, 20, 32, 40, 16, 14, 14, 10, 12, 12, 12, 12, 10, 10, 36, 10, 24)
GANTT_FILL = PatternFill("solid", fgColor="5B9BD5")
PHASE_FILL = PatternFill("solid", fgColor="2E75B6")


def build_wbs_gantt(ctx: GenerationContext) -> bytes:
    by_id = ctx.wbs_by_id
    preds: dict[str, list[str]] = {}
    succs: dict[str, list[str]] = {}
    for d in ctx.dependencies:
        p, s = by_id.get(d.predecessor_id), by_id.get(d.successor_id)
        if p and s:
            preds.setdefault(s.id, []).append(p.code)
            succs.setdefault(p.id, []).append(s.code)
    rows = []
    for w in ctx.wbs:
        rows.append(
            [
                w.code,
                by_id[w.parent_id].code if w.parent_id and w.parent_id in by_id else "",
                ", ".join(w.related_requirement_ids),
                w.name,
                w.description,
                w.role,
                ", ".join(preds.get(w.id, [])),
                ", ".join(succs.get(w.id, [])),
                w.work_type.value,
                w.planned_start,
                w.planned_end,
                w.actual_start,
                w.actual_end,
                w.duration_days,
                w.status.value,
                w.estimate_basis,
                float(w.effort_md),
                ("자동 생성 — 검토 필요; " if w.auto_generated else "") + w.notes,
            ]
        )
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_WBS
    last = write_table(
        ws,
        HEADERS,
        rows,
        widths=WIDTHS,
        validations={9: tuple(t.value for t in WorkType), 15: tuple(t.value for t in TaskStatus)},
        number_formats={
            10: "yyyy-mm-dd",
            11: "yyyy-mm-dd",
            12: "yyyy-mm-dd",
            13: "yyyy-mm-dd",
            17: "0.0",
        },
    )
    add_note(
        ws,
        last + 2,
        "업무 유형은 표시용이며 실제 선후행 관계는 '의존관계' 시트가 기준. 날짜는 계산값(영업일).",
    )

    # 간트: 주 단위 열
    ws2 = wb.create_sheet(SHEET_GANTT)
    starts = [w.planned_start for w in ctx.wbs if w.planned_start]
    ends = [w.planned_end for w in ctx.wbs if w.planned_end]
    if starts and ends:
        first = min(starts) - timedelta(days=min(starts).weekday())
        last_day = max(ends)
        weeks: list[date] = []
        cursor = first
        while cursor <= last_day:
            weeks.append(cursor)
            cursor += timedelta(days=7)
        fixed = ("WBS ID", "Task 명", "시작", "종료")
        for c, h in enumerate(fixed, start=1):
            cell = ws2.cell(row=1, column=c, value=h)
            cell.fill, cell.font, cell.alignment, cell.border = (
                HEADER_FILL,
                HEADER_FONT,
                CENTER,
                BORDER,
            )
        for i, wk in enumerate(weeks):
            cell = ws2.cell(row=1, column=len(fixed) + 1 + i, value=wk.strftime("%m/%d"))
            cell.fill, cell.font, cell.alignment = HEADER_FILL, HEADER_FONT, CENTER
            ws2.column_dimensions[get_column_letter(len(fixed) + 1 + i)].width = 5
        for r, w in enumerate(ctx.wbs, start=2):
            vals = [w.code, w.name, w.planned_start, w.planned_end]
            for c, v in enumerate(vals, start=1):
                cell = ws2.cell(row=r, column=c, value=v)
                cell.font, cell.border = BODY_FONT, BORDER
                if c in (3, 4):
                    cell.number_format = "yyyy-mm-dd"
            if w.planned_start and w.planned_end:
                for i, wk in enumerate(weeks):
                    if wk <= w.planned_end and wk + timedelta(days=6) >= w.planned_start:
                        ws2.cell(row=r, column=len(fixed) + 1 + i).fill = (
                            PHASE_FILL if w.parent_id is None else GANTT_FILL
                        )
        ws2.freeze_panes = "E2"
        for c, width in zip(range(1, 5), (10, 32, 12, 12), strict=False):
            ws2.column_dimensions[get_column_letter(c)].width = width

    ws3 = wb.create_sheet(SHEET_DEPS)
    dep_rows = [
        [by_id[d.predecessor_id].code, by_id[d.successor_id].code, d.type.value, d.lag_days]
        for d in ctx.dependencies
        if d.predecessor_id in by_id and d.successor_id in by_id
    ]
    write_table(ws3, ("선행 WBS", "후행 WBS", "유형", "지연(일)"), dep_rows, widths=(12, 12, 8, 10))

    ws4 = wb.create_sheet(SHEET_BASIS)
    basis_rows = [
        [
            w.code,
            w.name,
            float(w.effort_md),
            w.estimate_basis,
            "자동 생성" if w.auto_generated else "에이전트/사용자",
        ]
        for w in ctx.wbs
    ]
    write_table(
        ws4,
        ("WBS ID", "Task 명", "공수(M/D)", "산정 근거", "출처"),
        basis_rows,
        widths=(10, 32, 10, 60, 14),
        number_formats={3: "0.0"},
    )
    add_note(
        ws4,
        len(basis_rows) + 3,
        f"총 공수 {float(ctx.total_effort_md):.1f} M/D · 1 M/M = 20 M/D 가정",
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
