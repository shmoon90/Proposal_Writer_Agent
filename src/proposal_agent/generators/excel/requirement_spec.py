"""요구사항 정의서 Excel: 기능/비기능 분리 시트 + 제약·평가·제출 시트 + 변경이력."""

from __future__ import annotations

import io

from openpyxl import Workbook

from proposal_agent.generators.base import (
    ACCEPTANCE_OPTIONS,
    GenerationContext,
    acceptance_label,
    requirement_note,
)
from proposal_agent.generators.excel.style import add_note, write_table
from proposal_agent.models import Requirement, RequirementType

SHEET_FUNCTIONAL = "기능요구사항"
SHEET_NON_FUNCTIONAL = "비기능요구사항"
SHEET_OTHER = "제약·평가·제출조건"
SHEET_HISTORY = "변경이력"
SHEET_CHANGE_LOG = "변경관리대장"
CHANGE_LOG_HEADERS = (
    "CR ID",
    "변경 유형",
    "요청자",
    "요청일",
    "사유",
    "기존 요구사항 ID",
    "변경 전",
    "변경 후",
    "분류 근거",
    "승인 상태",
    "승인자",
    "승인일",
    "관련 산출물",
    "일정 영향",
    "공수 영향",
    "비용 영향",
    "결과",
)
REQUIRED_COLUMNS: tuple[str, ...] = (
    "요구사항 ID",
    "요구사항 명",
    "요구사항 상세 내용",
    "구현방안",
    "수용여부",
    "비고",
)
HEADERS: tuple[str, ...] = (
    *REQUIRED_COLUMNS[:5],
    "범위 분류",
    "필수 여부",
    "중요도",
    "검증 방법",
    "원본 출처",
    "검토 상태",
    "검증 상태",
    "연결 산출물",
    "추가 요청자",
    "추가일",
    "변경 상태",
    "변경 내용",
    REQUIRED_COLUMNS[5],
)
WIDTHS = (12, 28, 50, 36, 12, 12, 9, 9, 14, 30, 10, 12, 18, 12, 12, 12, 30, 40)
ACCEPT_COL = 5
CHANGE_STATE_LABELS = {
    "none": "",
    "added": "추가",
    "modified": "변경",
    "delete_requested": "삭제 요청",
    "deleted": "삭제",
}


def _row(r: Requirement) -> list[object]:
    source = (
        "; ".join(ref.location_label or ref.document_id for ref in r.source_refs) or "(출처 없음)"
    )
    return [
        r.id,
        r.name,
        r.description,
        r.implementation_approach or "검토 필요",
        acceptance_label(r),
        r.scope_class.label,
        "필수" if r.is_mandatory else "선택",
        r.priority.value,
        r.verification_method or "",
        source,
        r.review_status.value,
        r.verification_status.value,
        ", ".join(r.linked_deliverables),
        r.added_by or "",
        r.added_on,
        CHANGE_STATE_LABELS.get(r.change_state, r.change_state),
        r.change_summary,
        requirement_note(r),
    ]


def build_requirement_spec(ctx: GenerationContext) -> bytes:
    wb = Workbook()
    groups: list[tuple[str, list[Requirement]]] = [
        (SHEET_FUNCTIONAL, [r for r in ctx.requirements if r.type == RequirementType.FUNCTIONAL]),
        (
            SHEET_NON_FUNCTIONAL,
            [r for r in ctx.requirements if r.type == RequirementType.NON_FUNCTIONAL],
        ),
        (
            SHEET_OTHER,
            [
                r
                for r in ctx.requirements
                if r.type not in (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL)
            ],
        ),
    ]
    first = True
    for title, reqs in groups:
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        first = False
        rows = [_row(r) for r in reqs]
        if title == SHEET_OTHER:
            headers = ("종류", *HEADERS)
            rows = [[r.type.label, *row] for r, row in zip(reqs, rows, strict=True)]
            last = write_table(
                ws,
                headers,
                rows,
                widths=(10, *WIDTHS),
                validations={ACCEPT_COL + 1: ACCEPTANCE_OPTIONS},
            )
        else:
            last = write_table(
                ws, HEADERS, rows, widths=WIDTHS, validations={ACCEPT_COL: ACCEPTANCE_OPTIONS}
            )
        add_note(
            ws,
            last + 2,
            f"{ctx.project.name} · 생성 {ctx.generated_on} · {ctx.version} · 수용여부: 수용/조건부 수용/미수용/검토 필요",
        )
    ws = wb.create_sheet(SHEET_HISTORY)
    hist_rows = []
    for r in ctx.requirements:
        for h in r.history:
            hist_rows.append(
                [r.id, h.at, h.actor, h.action, h.note, str(h.changes) if h.changes else ""]
            )
    write_table(
        ws,
        ("요구사항 ID", "일시", "작업자", "작업", "메모", "변경 내용"),
        hist_rows,
        widths=(12, 22, 22, 18, 40, 50),
    )
    if ctx.change_log:
        ws = wb.create_sheet(SHEET_CHANGE_LOG)
        write_table(
            ws,
            CHANGE_LOG_HEADERS,
            ctx.change_log,
            widths=(10, 14, 12, 12, 30, 14, 40, 40, 50, 12, 12, 12, 40, 16, 30, 14, 40),
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
