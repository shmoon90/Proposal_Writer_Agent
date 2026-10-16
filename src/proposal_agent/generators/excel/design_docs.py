"""설계서 산출물 (지시문 §12, 단계 6): 화면 설계·DB 설계·API 명세·모듈·업무 규칙·추적 — Excel 한 파일 + Markdown.

입력은 저장된 설계 엔티티(Screen·DbTable·ApiSpec·CodeModule·DesignItem) 와 요구사항이다. 값이 없는 칸은 비워 두고
'미정' 을 지어내지 않는다.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook

from proposal_agent.generators.excel.style import add_note, write_table
from proposal_agent.models import ApiSpec, CodeModule, DbTable, DesignItem, Requirement, Screen

SHEET_SCREENS = "화면목록"
SHEET_SCREEN_FIELDS = "화면항목"
SHEET_SCREEN_FUNCS = "화면기능"
SHEET_TABLES = "DB테이블"
SHEET_COLUMNS = "DB컬럼"
SHEET_APIS = "API목록"
SHEET_API_DETAIL = "API상세"
SHEET_MODULES = "모듈"
SHEET_RULES = "업무규칙"
SHEET_TRACE = "요구-설계추적"


def _j(values: Any, sep: str = ", ") -> str:
    if not values:
        return ""
    if isinstance(values, (list, tuple)):
        return sep.join(str(v) for v in values)
    return str(values)


def build_design_workbook(
    requirements: list[Requirement],
    screens: list[Screen],
    tables: list[DbTable],
    apis: list[ApiSpec],
    modules: list[CodeModule],
    rules: list[DesignItem],
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_SCREENS
    write_table(
        ws,
        (
            "화면 ID",
            "화면명",
            "유형",
            "목적",
            "사용자 역할",
            "배치",
            "항목 수",
            "동작 수",
            "상태 메시지",
            "관련 요구사항",
            "상태",
        ),
        [
            [
                s.code or s.id,
                s.name,
                s.screen_type,
                getattr(s, "purpose", "") or s.description,
                _j(getattr(s, "user_roles", [])),
                (getattr(s, "layout", {}) or {}).get("description", ""),
                len(getattr(s, "fields", []) or []),
                len(getattr(s, "actions", []) or []),
                "; ".join(
                    f"{x.get('state', '')}: {x.get('message', '')}"
                    for x in (getattr(s, "states", []) or [])
                ),
                _j(getattr(s, "related_requirement_ids", [])),
                s.status,
            ]
            for s in screens
        ],
        widths=(10, 22, 8, 30, 14, 24, 7, 7, 36, 18, 8),
    )
    ws2 = wb.create_sheet(SHEET_SCREEN_FIELDS)
    rows2: list[list[object]] = []
    for s in screens:
        for f in getattr(s, "fields", []) or []:
            rows2.append(
                [
                    s.code or s.id,
                    s.name,
                    f.get("name", ""),
                    f.get("label", ""),
                    f.get("field_type", ""),
                    "Y" if f.get("required") else "N",
                    _j(f.get("validation_rules", []), "; "),
                    f.get("error_message", ""),
                    _j(f.get("requirement_ids", [])),
                ]
            )
        for a in getattr(s, "actions", []) or []:
            rows2.append(
                [
                    s.code or s.id,
                    s.name,
                    f"[동작] {a.get('label', '')}",
                    a.get("description", ""),
                    "action",
                    "",
                    a.get("expected_result", ""),
                    a.get("api_ref", ""),
                    _j(a.get("requirement_ids", [])),
                ]
            )
    write_table(
        ws2,
        (
            "화면 ID",
            "화면명",
            "항목명",
            "라벨·설명",
            "형식",
            "필수",
            "검증 규칙 · 기대 결과",
            "오류 메시지 · 호출 API",
            "관련 요구사항",
        ),
        rows2,
        widths=(10, 20, 20, 24, 10, 6, 40, 30, 16),
    )
    ws3 = wb.create_sheet(SHEET_SCREEN_FUNCS)
    write_table(
        ws3,
        (
            "화면 ID",
            "화면명",
            "기능명",
            "실행 계기",
            "입력",
            "처리 규칙·검증·상태 변화",
            "출력",
            "관련 요구사항",
        ),
        [
            [
                s.code or s.id,
                s.name,
                fn.get("name", ""),
                fn.get("trigger", ""),
                _j(fn.get("inputs", [])),
                fn.get("process", ""),
                _j(fn.get("outputs", [])),
                _j(fn.get("requirement_ids", [])),
            ]
            for s in screens
            for fn in (getattr(s, "functions", []) or [])
        ],
        widths=(10, 20, 22, 18, 24, 50, 24, 16),
    )
    ws4 = wb.create_sheet(SHEET_TABLES)
    write_table(
        ws4,
        (
            "테이블 ID",
            "물리명",
            "논리명",
            "설명",
            "DB 종류",
            "컬럼 수",
            "개인정보 컬럼",
            "인덱스",
            "관계",
            "보존·삭제 정책",
            "이관 영향",
            "관련 요구사항",
        ),
        [
            [
                t.code or t.id,
                t.name,
                t.logical_name,
                t.description,
                t.db_engine,
                len(t.columns),
                ", ".join(c.name for c in t.columns if c.is_personal_data),
                _j(t.indexes, "; "),
                _j(t.relations, "; "),
                t.retention_policy,
                t.migration_note,
                _j(t.related_requirement_ids),
            ]
            for t in tables
        ],
        widths=(10, 20, 18, 28, 12, 7, 18, 20, 20, 24, 24, 16),
    )
    ws5 = wb.create_sheet(SHEET_COLUMNS)
    write_table(
        ws5,
        (
            "테이블 ID",
            "테이블",
            "컬럼 ID",
            "컬럼명",
            "자료형",
            "길이",
            "NULL",
            "PK",
            "FK 참조",
            "제약",
            "개인정보",
            "기본값",
            "설명",
        ),
        [
            [
                t.code or t.id,
                t.name,
                c.code,
                c.name,
                c.data_type,
                c.length,
                "Y" if c.nullable else "N",
                "Y" if c.is_pk else "",
                c.fk_ref,
                c.constraint,
                "Y" if c.is_personal_data else "",
                c.default,
                c.description,
            ]
            for t in tables
            for c in t.columns
        ],
        widths=(10, 18, 9, 20, 12, 7, 6, 5, 20, 18, 8, 10, 30),
    )
    ws6 = wb.create_sheet(SHEET_APIS)
    write_table(
        ws6,
        (
            "API ID",
            "이름",
            "메서드",
            "경로",
            "설명",
            "인증·권한",
            "버전",
            "화면",
            "테이블",
            "관련 요구사항",
            "상태",
        ),
        [
            [
                a.code or a.id,
                a.name,
                a.method,
                a.path,
                a.request_schema.get("description", ""),
                a.auth,
                a.api_version,
                _j(a.related_screen_ids),
                _j(a.related_table_ids),
                _j(a.related_requirement_ids),
                a.status,
            ]
            for a in apis
        ],
        widths=(10, 24, 8, 30, 30, 18, 6, 16, 16, 16, 8),
    )
    ws7 = wb.create_sheet(SHEET_API_DETAIL)
    write_table(
        ws7,
        (
            "API ID",
            "이름",
            "요청 필드",
            "응답",
            "오류 코드",
            "검증 규칙",
            "멱등성",
            "타임아웃·재시도",
            "페이징·한도",
            "로깅·감사",
        ),
        [
            [
                a.code or a.id,
                a.name,
                _j(a.request_schema.get("fields", []), "; "),
                a.response_schema.get("description", ""),
                _j(a.error_codes, "; "),
                _j(a.validation_rules, "; "),
                a.idempotency,
                a.timeout_retry,
                a.paging_limits,
                a.logging_audit,
            ]
            for a in apis
        ],
        widths=(10, 22, 36, 28, 30, 30, 16, 16, 16, 20),
    )
    ws8 = wb.create_sheet(SHEET_MODULES)
    write_table(
        ws8,
        (
            "모듈 ID",
            "이름",
            "경로",
            "계층",
            "책임",
            "의존 모듈",
            "API",
            "화면",
            "테이블",
            "관련 요구사항",
            "상태",
        ),
        [
            [
                m.code or m.id,
                m.name,
                m.path,
                m.layer,
                m.description,
                _j(getattr(m, "depends_on", []), "; "),
                _j(m.related_api_ids),
                _j(m.related_screen_ids),
                _j(m.related_table_ids),
                _j(m.related_requirement_ids),
                m.status,
            ]
            for m in modules
        ],
        widths=(10, 20, 40, 10, 32, 30, 16, 16, 16, 16, 8),
    )
    ws9 = wb.create_sheet(SHEET_RULES)
    write_table(
        ws9,
        ("규칙 ID", "코드", "내용", "적용 모듈", "관련 요구사항"),
        [
            [
                d.name,
                d.code,
                d.description,
                (d.decisions[0].replace("적용 모듈: ", "") if d.decisions else ""),
                _j(d.related_requirement_ids),
            ]
            for d in rules
        ],
        widths=(10, 10, 60, 30, 18),
    )
    ws10 = wb.create_sheet(SHEET_TRACE)
    by_req: dict[str, dict[str, list[str]]] = {}
    for s in screens:
        for rid in getattr(s, "related_requirement_ids", []) or []:
            by_req.setdefault(rid, {}).setdefault("screen", []).append(s.code or s.id)
    for t in tables:
        for rid in t.related_requirement_ids:
            by_req.setdefault(rid, {}).setdefault("table", []).append(t.code or t.id)
    for a in apis:
        for rid in a.related_requirement_ids:
            by_req.setdefault(rid, {}).setdefault("api", []).append(a.code or a.id)
    for m in modules:
        for rid in m.related_requirement_ids:
            by_req.setdefault(rid, {}).setdefault("module", []).append(m.code or m.id)
    rows10 = []
    for r in requirements:
        if r.change_state == "deleted" or r.type.value in ("evaluation", "submission"):
            continue
        links = by_req.get(r.id, {})
        rows10.append(
            [
                r.id,
                r.name,
                r.type.value,
                _j(links.get("screen", [])) or "미정",
                _j(links.get("api", [])) or "미정",
                _j(links.get("table", [])) or "미정",
                _j(links.get("module", [])) or "미정",
                "연결" if links else "연결 없음",
            ]
        )
    write_table(
        ws10,
        ("요구사항 ID", "요구사항명", "유형", "화면", "API", "테이블", "모듈", "판정"),
        rows10,
        widths=(12, 30, 12, 20, 20, 20, 20, 10),
    )
    add_note(
        ws10,
        len(rows10) + 3,
        "화면·API·테이블·모듈은 상세 설계(detail_designer) 결과에서 연결된 것만 적고, 없는 것은 '미정'으로 둔다 (QA-CON-15 검사 대상).",
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_design_markdown(
    project_name: str,
    requirements: list[Requirement],
    screens: list[Screen],
    tables: list[DbTable],
    apis: list[ApiSpec],
    modules: list[CodeModule],
    rules: list[DesignItem],
    issues: tuple[list[str], list[str]] | None = None,
) -> str:
    lines = [f"# 설계서 — {project_name}", "", "## 1. 화면 설계", ""]
    for s in screens:
        lines.append(f"### {s.code or s.id} {s.name} ({s.screen_type})")
        lines.append(f"- 목적: {getattr(s, 'purpose', '') or s.description}")
        if getattr(s, "user_roles", None):
            lines.append(f"- 사용자: {_j(s.user_roles)}")
        if getattr(s, "related_requirement_ids", None):
            lines.append(f"- 요구사항: {_j(s.related_requirement_ids)}")
        lay = getattr(s, "layout", {}) or {}
        if lay.get("regions"):
            lines.append(
                "- 배치: "
                + "; ".join(
                    f"{r.get('name', '')}({_j(r.get('components', []))})" for r in lay["regions"]
                )
            )
        if getattr(s, "fields", None):
            lines += [
                "",
                "| 항목 | 라벨 | 형식 | 필수 | 검증 규칙 | 오류 메시지 |",
                "|---|---|---|---|---|---|",
            ]
            for f in s.fields:
                lines.append(
                    f"| {f.get('name', '')} | {f.get('label', '')} | {f.get('field_type', '')} | {'Y' if f.get('required') else ''} | {_j(f.get('validation_rules', []), '; ')} | {f.get('error_message', '')} |"
                )
        if getattr(s, "functions", None):
            lines += ["", "| 기능 | 계기 | 처리 | 출력 |", "|---|---|---|---|"]
            for fn in s.functions:
                lines.append(
                    f"| {fn.get('name', '')} | {fn.get('trigger', '')} | {fn.get('process', '')} | {_j(fn.get('outputs', []))} |"
                )
        if getattr(s, "states", None):
            lines.append(
                "- 상태: "
                + "; ".join(f"{x.get('state', '')}={x.get('message', '')}" for x in s.states)
            )
        lines.append("")
    lines += ["## 2. DB 설계", ""]
    for t in tables:
        lines.append(
            f"### {t.code or t.id} {t.name} ({t.logical_name}) — {t.db_engine or 'DB 종류 미지정'}"
        )
        lines.append(f"- {t.description}")
        if t.retention_policy:
            lines.append(f"- 보존·삭제: {t.retention_policy}")
        lines += [
            "",
            "| 컬럼 | 자료형 | 길이 | NULL | PK | FK | 개인정보 | 설명 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for c in t.columns:
            lines.append(
                f"| {c.name} | {c.data_type} | {c.length} | {'Y' if c.nullable else 'N'} | {'Y' if c.is_pk else ''} | {c.fk_ref} | {'Y' if c.is_personal_data else ''} | {c.description} |"
            )
        lines.append("")
    lines += [
        "## 3. API 명세",
        "",
        "| ID | 메서드 | 경로 | 설명 | 요청 | 응답 | 인증 | 오류 코드 | 멱등성 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for a in apis:
        lines.append(
            f"| {a.code or a.id} | {a.method} | {a.path} | {a.request_schema.get('description', '')} | {_j(a.request_schema.get('fields', []), '; ')} | {a.response_schema.get('description', '')} | {a.auth} | {_j(a.error_codes, '; ')} | {a.idempotency} |"
        )
    lines += [
        "",
        "## 4. 코드 모듈",
        "",
        "| ID | 경로 | 계층 | 책임 | 의존 | 요구사항 |",
        "|---|---|---|---|---|---|",
    ]
    for m in modules:
        lines.append(
            f"| {m.code or m.id} | {m.path or m.name} | {m.layer} | {m.description} | {_j(getattr(m, 'depends_on', []), '; ')} | {_j(m.related_requirement_ids)} |"
        )
    lines += ["", "## 5. 업무 규칙", ""]
    for d in rules:
        lines.append(f"- {d.name}: {d.description} ({_j(d.related_requirement_ids)})")
    if issues is not None:
        fails, revs = issues
        lines += ["", "## 6. 추적·모순 검사", ""]
        lines += [f"- 실패: {x}" for x in fails] or ["- 실패 없음"]
        lines += [f"- 검토: {x}" for x in revs] or ["- 검토 없음"]
    return "\n".join(lines) + "\n"


__all__ = [
    "SHEET_APIS",
    "SHEET_API_DETAIL",
    "SHEET_COLUMNS",
    "SHEET_MODULES",
    "SHEET_RULES",
    "SHEET_SCREENS",
    "SHEET_SCREEN_FIELDS",
    "SHEET_SCREEN_FUNCS",
    "SHEET_TABLES",
    "SHEET_TRACE",
    "build_design_markdown",
    "build_design_workbook",
]
