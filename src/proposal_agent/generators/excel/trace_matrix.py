"""요구사항 추적표 Excel: 기본 시트(요구사항×화면×단위/통합 테스트) + 테스트 상세 + 미추적.

제안 단계에서는 화면·테스트 ID가 아직 확정되지 않으므로 실제 존재하는 ID만 연결하고, 없으면 '미정'으로 둔다.
테스트 결과는 미실행/성공/실패/보류이며 수행하지 않은 테스트는 '미실행'이다.
"""

from __future__ import annotations

import io

from openpyxl import Workbook

from proposal_agent.generators.base import PENDING_ID, GenerationContext
from proposal_agent.generators.excel.style import add_note, write_table
from proposal_agent.models import IntegrationTest, RequirementTrace, Screen, TestResult, UnitTest

SHEET_MAIN = "추적표"
SHEET_TESTS = "테스트상세"
SHEET_UNTRACED = "미추적"
HEADERS = (
    "요구사항 ID",
    "요구사항 명",
    "화면 ID",
    "단위테스트 ID",
    "단위테스트 결과",
    "통합테스트 ID",
    "통합테스트 결과",
    "WBS",
    "검토 상태",
    "변경 사유",
    "비고",
)
RESULT_OPTIONS = tuple(t.value for t in TestResult)


def build_trace_matrix(
    ctx: GenerationContext,
    traces: list[RequirementTrace],
    screens: list[Screen],
    unit_tests: list[UnitTest],
    integration_tests: list[IntegrationTest],
) -> bytes:
    screen_ids = {s.code or s.id for s in screens}
    ut_ids = {t.code or t.id for t in unit_tests}
    it_ids = {t.code or t.id for t in integration_tests}
    by_req: dict[str, dict[str, list[str]]] = {}
    review: dict[str, list[str]] = {}
    for t in traces:
        bucket = by_req.setdefault(
            t.requirement_id,
            {"screen": [], "unit_test": [], "integration_test": [], "wbs_item": []},
        )
        bucket.setdefault(t.target_type.value, []).append(t.target_id)
        if t.review_status != "유효":
            review.setdefault(t.requirement_id, []).append(
                f"{t.target_id}: {t.review_status} ({t.review_reason})"
            )
    wbs_by_req: dict[str, list[str]] = {}
    for w in ctx.wbs:
        for rid in w.related_requirement_ids:
            wbs_by_req.setdefault(rid, []).append(w.code)

    rows = []
    untraced = []
    for r in ctx.requirements:
        links = by_req.get(r.id, {})
        scr = [s for s in links.get("screen", []) if s in screen_ids]
        uts = [u for u in links.get("unit_test", []) if u in ut_ids]
        its = [i for i in links.get("integration_test", []) if i in it_ids]
        wbs_codes = wbs_by_req.get(r.id, [])
        note = ""
        if not (scr or uts or its):
            note = "제안 단계: 화면·테스트 ID 미확정"
        if not wbs_codes:
            untraced.append([r.id, r.name, "WBS 미연결"])
        rows.append(
            [
                r.id,
                r.name,
                ", ".join(scr) or PENDING_ID,
                ", ".join(uts) or PENDING_ID,
                TestResult.NOT_RUN.value,
                ", ".join(its) or PENDING_ID,
                TestResult.NOT_RUN.value,
                ", ".join(wbs_codes) or PENDING_ID,
                "재검토 필요" if review.get(r.id) else "유효",
                "; ".join(review.get(r.id, [])),
                note,
            ]
        )
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    last = write_table(
        ws,
        HEADERS,
        rows,
        widths=(12, 30, 16, 18, 12, 18, 12, 18, 12, 30, 30),
        validations={5: RESULT_OPTIONS, 7: RESULT_OPTIONS, 9: ("유효", "재검토 필요", "무효")},
    )
    add_note(
        ws,
        last + 2,
        "테스트 결과는 실제 수행 전까지 '미실행'. '미정'은 제안 단계에서 아직 확정되지 않은 ID.",
    )

    ws2 = wb.create_sheet(SHEET_TESTS)
    test_rows = [
        [
            t.code or t.id,
            "단위",
            t.name,
            t.target_component,
            t.status if t.status in RESULT_OPTIONS else TestResult.NOT_RUN.value,
            "",
        ]
        for t in unit_tests
    ]
    test_rows += [
        [
            t.code or t.id,
            "통합",
            t.name,
            t.scenario,
            t.status if t.status in RESULT_OPTIONS else TestResult.NOT_RUN.value,
            "",
        ]
        for t in integration_tests
    ]
    write_table(
        ws2,
        ("테스트 ID", "구분", "테스트 명", "대상/시나리오", "결과", "비고"),
        test_rows,
        widths=(14, 8, 30, 40, 10, 30),
        validations={5: RESULT_OPTIONS},
    )

    ws3 = wb.create_sheet(SHEET_UNTRACED)
    write_table(ws3, ("요구사항 ID", "요구사항 명", "사유"), untraced, widths=(12, 30, 30))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
