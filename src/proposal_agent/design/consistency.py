"""요구사항 ↔ 설계 객체 추적·누락·모순·DB 호환성 검사 (지시문 §12.4, 단계 6 ②·③).

순수 함수라 설계 서비스와 QA(QA-CON-15) 가 같은 판정을 쓴다.
- 실패: 수용된 필수 기능 요구에 화면·API·테이블 연결이 전혀 없음, API 가 가리키는 화면·테이블·모듈이 없음, 모듈 의존이 없는
  모듈을 가리키거나 순환, FK 가 없는 테이블을 가리킴, 설계 객체가 존재하지 않는 요구 ID 를 가리킴.
- 검토: 비필수 요구의 연결 없음, 개인정보 컬럼이 있는데 인증·권한이 비어 있는 API, DB 종류 미지정 또는 아키텍처·조사·RFP 지정
  기술에 없는 DB 종류(호환성 확인 필요), 상태 메시지 없는 화면.
"""

from __future__ import annotations

from typing import Any

from proposal_agent.models import (
    AcceptanceStatus,
    ApiSpec,
    CodeModule,
    DbTable,
    Requirement,
    RequirementType,
    Screen,
)

_DB_WORDS = (
    "oracle",
    "postgres",
    "mysql",
    "mariadb",
    "mssql",
    "sql server",
    "tibero",
    "cubrid",
    "sqlite",
    "db2",
    "altibase",
)


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def _db_token(text: str) -> str:
    low = _norm(text)
    for w in _DB_WORDS:
        if w in low:
            return w
    return ""


def design_consistency_issues(
    requirements: list[Requirement],
    screens: list[Screen],
    tables: list[DbTable],
    apis: list[ApiSpec],
    modules: list[CodeModule],
    *,
    component_techs: list[str] | None = None,
    research_stack: list[str] | None = None,
    rfp_specified_tech: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    revs: list[str] = []
    active = [r for r in requirements if r.change_state != "deleted"]
    req_ids = {r.id for r in active}
    linked: dict[str, set[str]] = {}

    def link(rid: str, what: str) -> None:
        linked.setdefault(rid, set()).add(what)

    screen_names = {_norm(s.name): s for s in screens}
    table_names = {_norm(t.name): t for t in tables} | {
        _norm(t.logical_name): t for t in tables if t.logical_name
    }
    table_codes = {t.code for t in tables} | {t.id for t in tables}
    module_paths = {m.path for m in modules} | {m.code for m in modules} | {m.name for m in modules}
    for s in screens:
        for rid in getattr(s, "related_requirement_ids", []) or []:
            if rid not in req_ids:
                fails.append(f"{s.code or s.id} 화면이 존재하지 않는 요구 {rid} 를 가리킴")
            else:
                link(rid, "screen")
        if not (getattr(s, "states", None) or []):
            revs.append(f"{s.code or s.id} {s.name}: 상태 메시지(LOADING/EMPTY/ERROR) 없음")
    for t in tables:
        for rid in t.related_requirement_ids:
            if rid not in req_ids:
                fails.append(f"{t.code or t.id} 테이블이 존재하지 않는 요구 {rid} 를 가리킴")
            else:
                link(rid, "table")
        for c in t.columns:
            if c.fk_ref:
                ref_table = c.fk_ref.split(".")[0].strip()
                if (
                    ref_table
                    and _norm(ref_table) not in table_names
                    and ref_table not in table_codes
                ):
                    fails.append(f"{t.code or t.id}.{c.name}: FK 참조 테이블 {ref_table} 없음")
    personal_tables = {t.code for t in tables if any(c.is_personal_data for c in t.columns)} | {
        _norm(t.name) for t in tables if any(c.is_personal_data for c in t.columns)
    }
    for a in apis:
        for rid in a.related_requirement_ids:
            if rid not in req_ids:
                fails.append(f"{a.code or a.id} API 가 존재하지 않는 요구 {rid} 를 가리킴")
            else:
                link(rid, "api")
        for sid in a.related_screen_ids:
            if (
                sid not in {s.code for s in screens} | {s.id for s in screens}
                and _norm(sid) not in screen_names
            ):
                fails.append(f"{a.code or a.id} {a.name}: 연결 화면 {sid} 없음")
        for tid in a.related_table_ids:
            if tid not in table_codes and _norm(tid) not in table_names:
                fails.append(f"{a.code or a.id} {a.name}: 연결 테이블 {tid} 없음")
        touches_personal = any(
            tid in personal_tables or _norm(tid) in personal_tables for tid in a.related_table_ids
        )
        if touches_personal and not (a.auth or "").strip():
            revs.append(
                f"{a.code or a.id} {a.name}: 개인정보 테이블을 다루는데 인증·권한이 비어 있음"
            )
        if not a.error_codes:
            revs.append(f"{a.code or a.id} {a.name}: 오류 코드 없음")
    for m in modules:
        for rid in m.related_requirement_ids:
            if rid not in req_ids:
                fails.append(f"{m.code or m.id} 모듈이 존재하지 않는 요구 {rid} 를 가리킴")
            else:
                link(rid, "module")
        for dep in (m.review_checklist and []) or _deps(m):
            if dep not in module_paths:
                fails.append(f"{m.code or m.id} {m.path or m.name}: 의존 모듈 {dep} 없음")
    cycle = _find_cycle(modules)
    if cycle:
        fails.append("모듈 의존 순환: " + " → ".join(cycle))
    # 요구 ↔ 설계 연결 누락
    for r in active:
        if r.acceptance_status == AcceptanceStatus.REJECTED or r.type.value in (
            "evaluation",
            "submission",
        ):
            continue
        kinds = linked.get(r.id, set())
        if r.type == RequirementType.FUNCTIONAL and not (kinds & {"screen", "api", "table"}):
            msg = f"{r.id} {r.name}: 화면·API·테이블 연결 없음"
            (fails if r.is_mandatory else revs).append(msg)
        elif r.type == RequirementType.NON_FUNCTIONAL and not kinds:
            revs.append(f"{r.id} {r.name}: 비기능 요구가 어떤 설계 객체에도 연결되지 않음")
    # DB 호환성 (③): 테이블의 DB 종류가 아키텍처·조사·RFP 지정 기술과 맞는가
    known = " ".join(
        [*(component_techs or []), *(research_stack or []), *(rfp_specified_tech or [])]
    )
    known_db = {w for w in _DB_WORDS if w in _norm(known)}
    engines = {t.db_engine for t in tables if t.db_engine}
    if tables and not engines:
        revs.append("테이블 설계에 DB 종류(db_engine)가 없음 — 호환성 확인 불가")
    for e in sorted(engines):
        tok = _db_token(e)
        if known_db and tok and tok not in known_db:
            revs.append(
                f"테이블 DB 종류 '{e}' 가 아키텍처·조사·RFP 지정 기술({', '.join(sorted(known_db))})에 없음 — 호환성 확인"
            )
        elif not tok:
            revs.append(f"테이블 DB 종류 '{e}' 를 식별할 수 없음 — 종류·버전 확인")
    return fails, revs


def _deps(m: CodeModule) -> list[str]:
    extra: Any = getattr(m, "depends_on", None)
    return [str(x) for x in (extra or [])]


def _find_cycle(modules: list[CodeModule]) -> list[str]:
    graph = {m.path or m.name: _deps(m) for m in modules}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> list[str]:
        if state.get(n) == 1:
            return stack[stack.index(n) :] + [n] if n in stack else [n, n]
        if state.get(n) == 2:
            return []
        state[n] = 1
        stack.append(n)
        for d in graph.get(n, []):
            if d in graph:
                c = visit(d)
                if c:
                    return c
        stack.pop()
        state[n] = 2
        return []

    for node in graph:
        c = visit(node)
        if c:
            return c
    return []


__all__ = ["design_consistency_issues"]
