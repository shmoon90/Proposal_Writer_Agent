"""openpyxl 공통 서식: 헤더, 필터, 고정 창, 열 너비, 데이터 유효성, 줄바꿈."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF", name="맑은 고딕", size=10)
BODY_FONT = Font(name="맑은 고딕", size=10)
NOTE_FONT = Font(name="맑은 고딕", size=9, italic=True, color="7F7F7F")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def write_table(
    ws: Worksheet,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    widths: Sequence[int] | None = None,
    freeze: str = "A2",
    start_row: int = 1,
    validations: dict[int, Sequence[str]] | None = None,
    number_formats: dict[int, str] | None = None,
) -> int:
    """헤더+행을 쓰고 필터·고정 창·너비·유효성 검사를 적용한다. 마지막 행 번호를 돌려준다."""
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill, cell.font, cell.alignment, cell.border = HEADER_FILL, HEADER_FONT, CENTER, BORDER
    r = start_row
    for r_off, row in enumerate(rows, start=1):
        r = start_row + r_off
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font, cell.alignment, cell.border = BODY_FONT, WRAP, BORDER
            if number_formats and c in number_formats:
                cell.number_format = number_formats[c]
    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A{start_row}:{last_col}{max(r, start_row + 1)}"
    ws.freeze_panes = freeze
    for c in range(1, len(headers) + 1):
        width = widths[c - 1] if widths and c - 1 < len(widths) else 16
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[start_row].height = 30
    if validations:
        for col, options in validations.items():
            dv = DataValidation(
                type="list",
                formula1='"' + ",".join(options) + '"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="허용되지 않는 값",
                error="목록에서 선택하십시오.",
            )
            ws.add_data_validation(dv)
            dv.add(
                f"{get_column_letter(col)}{start_row + 1}:{get_column_letter(col)}{max(r, start_row + 1) + 200}"
            )
    return r


def add_note(ws: Worksheet, row: int, text: str) -> None:
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = NOTE_FONT
    cell.alignment = Alignment(wrap_text=False)
