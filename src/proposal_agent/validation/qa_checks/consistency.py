"""QA-CON: 문서 간 일관성 검사 (independent_qa 분할)."""

from __future__ import annotations

import re
from typing import Any

from proposal_agent.config.errors import PathSecurityError
from proposal_agent.models import (
    AcceptanceStatus,
    ChangeStatus,
    DeliverableKind,
    DependencyType,
    ProjectMode,
    ProjectSettings,
    QaCategory,
    QaCheck,
    RequirementType,
    ValidationLevel,
)
from proposal_agent.models.change import CandidateClass
from proposal_agent.requirements.id_policy import normalize_text
from proposal_agent.validation.qa_checks.common import (
    ABSTRACT_WORDS,
    ACRONYM_RE,
    COMMON_ACRONYMS,
    FIX_REGENERATE,
    ID_IN_TEXT_RE,
    NUMBER_CLAIM_RE,
    ROMAN_RE,
    CheckArtifacts,
    QaInputs,
    _cap,
    _check,
    _finish,
    _ids_from_sheets,
    _kind_files,
    _looks_like_req_id,
    _not_run,
    _spec_rows,
)


# --- 문서 간 일관성 ----------------------------------------------------------------------------
def check_consistency_rules(inp: QaInputs, art: CheckArtifacts) -> list[QaCheck]:
    cat = QaCategory.CONSISTENCY
    checks = [
        _check(
            "QA-CON-01",
            cat,
            "PPT ↔ 요구사항 정의서",
            "제출용 PPT가 모든 필수 요구사항 ID를 다루고 없는 ID를 언급하지 않으며, PPT 핵심 수치가 Excel과 같은가",
            gate="gate5",
            fixable=FIX_REGENERATE,
            fix_suggestion="공통 데이터로 산출물을 재생성",
        ),
        _check(
            "QA-CON-02",
            cat,
            "요구사항 정의서 ↔ 추적표",
            "두 파일의 요구사항 ID 집합이 같고 기준 데이터와 일치하는가",
            gate="gate4",
            fixable=FIX_REGENERATE,
            fix_suggestion="공통 데이터로 Excel을 재생성",
        ),
        _check(
            "QA-CON-03",
            cat,
            "요구사항 ↔ WBS",
            "수용된 필수 요구사항마다 WBS Task가 있고, WBS가 없는 요구사항을 참조하지 않는가",
            gate="gate3",
            fix_suggestion="계획(WBS)을 다시 세워 누락 요구사항에 Task를 배정",
        ),
        _check(
            "QA-CON-04",
            cat,
            "WBS ↔ 일정",
            "선후행(FS) 관계·상위 항목 범위·기간(영업일)이 날짜와 맞는가",
            gate="gate3",
            fix_suggestion="일정을 재계산(계획 재생성)하거나 의존 관계를 수정",
        ),
        _check(
            "QA-CON-05",
            cat,
            "WBS ↔ 인력 투입계획",
            "WBS 총 공수 = 인력 계획 합계 = 배정 합계인가",
            gate="gate3",
            fix_suggestion="계획을 재생성해 배정을 다시 계산",
        ),
        _check(
            "QA-CON-06",
            cat,
            "기술 조사 ↔ 아키텍처",
            "구성 요소 기술이 조사 권고 스택과 모순되지 않는가",
            gate="gate2",
            mandatory=False,
            fix_suggestion="아키텍처 기술을 조사 권고와 맞추거나 선택 사유를 기록",
        ),
        _check(
            "QA-CON-07",
            cat,
            "변경 이력 ↔ 현재 기준 데이터",
            "반영된 변경 요청의 요구사항 상태·Revision·변경 후 파일이 현재 데이터와 맞는가",
            gate="gate5",
            fix_suggestion="변경 요청을 재반영하거나 기준 데이터를 점검",
        ),
        _check(
            "QA-CON-08",
            cat,
            "발표용 PPT 미확정 표기",
            "'검토 필요/미정' 표기가 과다하지 않은가",
            gate="gate5",
            mandatory=False,
            fix_suggestion="기술·수용 여부를 확정한 뒤 재생성",
        ),
        _check(
            "QA-CON-09",
            cat,
            "요구사항 정의서 구현 방안·난이도",
            "수용된 구현 대상 요구사항마다 구현 방안(글머리 요약)·구현 난이도(상/중/하)·검사 기준이 기준 데이터와 정의서 파일에 있는가. 규칙 초안([자동 초안])은 사람 확인 대상(조사 검토 게이트)",
            gate="gate2",
            fix_suggestion="'구현 방안 작성(에이전트)'을 실행하거나 요구사항 화면에서 구현 방안·난이도를 확정한 뒤 재생성",
        ),
        _check(
            "QA-CON-10",
            cat,
            "제안 문안 추상 표현·근거 없는 수치",
            "제안 문안(소절 제목·결론형 제목·리드·글머리·표)에 근거 없는 과장 표현(최적의·완벽한·세계적 등)이 없고, 단위가 붙은 수치가 기준 데이터(요구사항·조사·RFP 본문·WBS·인력)나 소절 근거(evidence)에 있는 값인가. 제안 문안이 없으면 제출용 PPT 본문의 추상 표현만 검사",
            gate="gate5",
            mandatory=False,
            fix_suggestion="과장 표현은 근거 있는 사실로 바꾸고, 수치는 출처(요구사항·조사·RFP)를 evidence에 적거나 unverified_claims로 분리",
        ),
        _check(
            "QA-CON-12",
            cat,
            "정의서 구현방안 ↔ 제안서 반영",
            "요구사항 정의서의 구현방안(요구사항별 줄)이 제출용 PPT에 실제로 실려 있는가. 수용된 필수 기능 요구의 구현방안이 한 줄도 없으면 실패, 일부만 있으면 검토",
            gate="gate5",
            fixable=FIX_REGENERATE,
            fix_suggestion="산출물 재생성 (코드가 요구사항 묶음별 구현 방안 소절에 정의서 전문을 싣는다)",
        ),
        _check(
            "QA-CON-11",
            cat,
            "약어·전문 용어 설명",
            "제안 문안(없으면 제출용 PPT 본문)에 쓴 영문 약어가 용어집(glossary)에 있거나 첫 등장 시 괄호로 풀어쓰여 있는가 (RFP·WBS·PM 등 일반 약어와 요구사항 ID 제외)",
            gate="gate5",
            mandatory=False,
            fix_suggestion="glossary에 용어·풀이·비전문가용 설명을 추가하거나 본문 첫 등장 시 '약어(풀이)'로 표기",
        ),
        _check(
            "QA-CON-13",
            cat,
            "구현 설계 깊이 ↔ 제안서 반영",
            "요구사항 묶음마다 구현 설계(구현 구조 2개 이상·처리 절차 3단계 이상·적용 기술과 선정 이유·데이터/인터페이스)가 있고, 그 구성 요소·절차·적용 기술이 제출용 PPT 본문에 실려 있는가. 설계가 없으면 검토(구현 설계 작성 필요), 최소 요건 미달·미반영은 실패, 출처 미확인 기술 선택과 설계에서 빠진 요구사항은 검토",
            gate="gate5",
            fixable=FIX_REGENERATE,
            fix_suggestion="'구현 설계 작성(에이전트, 웹 검색)'을 실행해 묶음마다 구조·절차·적용 기술·근거를 채우고 산출물을 재생성",
        ),
        _check(
            "QA-CON-14",
            cat,
            "결정·협상 ↔ 기준선 반영 통제",
            "권한 미확인 결정이 승인 상태가 아니고, 협상은 고객 합의·승인 없이 '반영'이 아니며, 결정·협상에서 온 변경 요청이 승인된 원천만 가리키는가(실패). 기한 지난 미결·조치 항목과 승인 없이 변경 요청으로 이어진 결정은 검토",
            gate="gate5",
            fix_suggestion="회의·결정·협상 화면에서 권한 확인·고객 합의를 기록하고, 미결·조치 항목을 해결·보류 처리",
        ),
        _check(
            "QA-CON-15",
            cat,
            "요구사항 ↔ 설계 객체 추적·모순",
            "수용된 필수 기능 요구마다 화면·API·테이블 연결이 있고, API 가 가리키는 화면·테이블·모듈과 FK 참조·모듈 의존이 실제로 있으며(순환 없음), 설계 객체가 존재하지 않는 요구를 가리키지 않는가(실패). 비필수 연결 없음·개인정보 API 인증 누락·DB 종류 미지정/불일치·상태 메시지 없음은 검토 (단계 6 ②·③)",
            gate="gate5",
            fix_suggestion="설계 화면에서 상세 설계를 다시 실행하거나 설계 객체를 수정해 연결·참조를 맞춤",
        ),
    ]
    f = art.outcome.findings
    by_rule: dict[str, list[tuple[ValidationLevel, str]]] = {}
    for x in f:
        by_rule.setdefault(x.rule, []).append((x.level, x.message))

    def split(rules: tuple[str, ...]) -> tuple[list[str], list[str]]:
        fails: list[str] = []
        revs: list[str] = []
        for r in rules:
            for lvl, msg in by_rule.get(r, []):
                (fails if lvl == ValidationLevel.ERROR else revs).append(msg)
        return fails, revs

    req_ids = {r.id for r in inp.requirements}
    # 01
    f01, r01 = split(("traceability.requirements", "consistency.ppt_figures"))
    sub_text = "\n".join(art.ppt_texts.get("submission", []))
    rfp_ids = {r.rfp_requirement_id for r in inp.requirements if r.rfp_requirement_id}
    unknown = sorted(
        {
            m
            for m in ID_IN_TEXT_RE.findall(sub_text)
            if _looks_like_req_id(m, inp.id_prefixes) and m not in req_ids and m not in rfp_ids
        }
    )
    if unknown:
        f01.append(f"제출용 PPT가 기준에 없는 요구사항 ID를 언급: {', '.join(unknown[:8])}")
    if inp.mode != ProjectMode.PROPOSAL:
        _not_run(checks[0], "구축 단계는 PPT를 생성하지 않음")
    else:
        _finish(
            checks[0],
            fail=f01,
            review=r01,
            files=_kind_files(
                inp, DeliverableKind.SUBMISSION_PPTX, DeliverableKind.PRESENTATION_PPTX
            ),
        )
    # 02
    f02, r02 = split(("xlsx.ids",))
    spec = art.excel.get(DeliverableKind.REQUIREMENT_SPEC_XLSX, {})
    trace = art.excel.get(DeliverableKind.TRACE_MATRIX_XLSX, {})
    spec_ids = _ids_from_sheets(spec, ("기능요구사항", "비기능요구사항", "제약·평가·제출조건"))
    trace_ids = _ids_from_sheets(trace, ("추적표",))
    if spec and trace and spec_ids != trace_ids:
        f02.append(
            f"정의서 ID {len(spec_ids)}건 ≠ 추적표 ID {len(trace_ids)}건 (차이 {sorted(spec_ids ^ trace_ids)[:6]})"
        )
    _finish(
        checks[1],
        fail=f02,
        review=r02,
        files=_kind_files(
            inp, DeliverableKind.REQUIREMENT_SPEC_XLSX, DeliverableKind.TRACE_MATRIX_XLSX
        ),
    )
    # 03
    linked: set[str] = set()
    leaf_codes = []
    parents = {w.parent_id for w in inp.ctx.wbs if w.parent_id}
    for w in inp.ctx.wbs:
        if w.id not in parents and w.status.value != "보류":
            leaf_codes.append(w.code)
            linked.update(w.related_requirement_ids)
    need = [
        r
        for r in inp.requirements
        if r.is_mandatory
        and r.acceptance_status != AcceptanceStatus.REJECTED
        and r.change_state != "deleted"
        and r.type in (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL)
    ]
    missing = [r.id for r in need if r.id not in linked]
    f03 = [f"WBS Task가 없는 수용 요구사항: {', '.join(missing[:10])}"] if missing else []
    dangling = sorted(
        {
            rid
            for w in inp.ctx.wbs
            for rid in w.related_requirement_ids
            if rid not in {x.id for x in inp.all_requirements}
        }
    )
    if dangling:
        f03.append(f"WBS가 없는 요구사항을 참조: {', '.join(dangling[:6])}")
    if not inp.ctx.wbs:
        f03.append("WBS가 없음")
    _finish(checks[2], fail=f03, req_ids=missing + dangling)
    # 04
    f04: list[str] = []
    by_id = {w.id: w for w in inp.ctx.wbs}
    for d in inp.ctx.dependencies:
        p, s = by_id.get(d.predecessor_id), by_id.get(d.successor_id)
        if not p or not s or not (p.planned_end and s.planned_start):
            continue
        if (
            d.type == DependencyType.FS
            and s.status.value != "보류"
            and p.status.value != "보류"
            and s.planned_start <= p.planned_end
            and d.lag_days >= 0
        ):
            f04.append(
                f"{s.code} 시작({s.planned_start})이 선행 {p.code} 종료({p.planned_end}) 이후가 아님"
            )
    for w in inp.ctx.wbs:
        par = by_id.get(w.parent_id) if w.parent_id else None
        if (
            par
            and w.planned_start
            and w.planned_end
            and par.planned_start
            and par.planned_end
            and (w.planned_start < par.planned_start or w.planned_end > par.planned_end)
            and w.status.value != "보류"
        ):
            f04.append(f"{w.code} 기간이 상위 {par.code} 범위를 벗어남")
        if w.id not in parents and w.planned_start and w.planned_end and w.duration_days:
            actual = inp.calendar.business_days_between(w.planned_start, w.planned_end)
            if abs(actual - w.duration_days) > 1:
                f04.append(f"{w.code} 기간 {w.duration_days}영업일 ≠ 날짜 차이 {actual}영업일")
    _finish(checks[3], fail=_cap(f04), files=_kind_files(inp, DeliverableKind.WBS_GANTT_XLSX))
    # 05
    f05, r05 = split(("consistency.effort", "consistency.allocation"))
    _finish(
        checks[4],
        fail=f05,
        review=r05,
        files=_kind_files(inp, DeliverableKind.WBS_GANTT_XLSX, DeliverableKind.STAFFING_PLAN_XLSX),
    )
    # 06
    stack = " ".join(s for tr in inp.research for s in tr.recommended_stack).casefold()
    r06 = []
    if stack:
        for c in inp.components:
            if (
                c.technology
                and "미정" not in c.technology
                and not any(
                    tok.casefold() in stack
                    for tok in re.split(r"[\s/,+]+", c.technology)
                    if len(tok) >= 3
                )
            ):
                r06.append(f"{c.name} 기술 '{c.technology}'이 조사 권고 스택에 없음")
    _finish(checks[5], review=r06)
    # 07
    f07: list[str] = []
    all_reqs = {r.id: r for r in inp.all_requirements}
    applied = [cr for cr in inp.change_requests if cr.status == ChangeStatus.APPLIED]
    for cr in applied:
        for rid in cr.applied_requirement_ids:
            r = all_reqs.get(rid)
            if r is None:
                f07.append(f"{cr.id}: 반영 요구사항 {rid}가 기준 데이터에 없음")
                continue
            cands = [
                cand
                for cand in cr.accepted_candidates
                if (cand.requirement_id or cand.user_override.get("requirement_id")) == rid
            ]
            for cand in cands:
                if cand.classification == CandidateClass.ADD and r.change_state != "added":
                    f07.append(f"{cr.id}: {rid} 추가 반영인데 상태가 '{r.change_state}'")
                if (
                    cand.classification == CandidateClass.DELETE_REQUEST
                    and r.change_state != "deleted"
                ):
                    f07.append(f"{cr.id}: {rid} 삭제 요청 반영인데 상태가 '{r.change_state}'")
                if cand.classification == CandidateClass.MODIFY and (
                    r.change_state not in ("modified", "deleted") or not r.previous_versions
                ):
                    f07.append(f"{cr.id}: {rid} 수정 반영인데 이전 버전 기록이 없음")
        for fp in cr.after_files:
            try:
                if not inp.paths.resolve_output(fp).exists():
                    f07.append(f"{cr.id}: 변경 후 파일 없음 {fp}")
            except PathSecurityError:
                f07.append(f"{cr.id}: 변경 후 파일 경로가 Output 밖 {fp}")
        if cr.revision_id and not any(rv.id == cr.revision_id for rv in inp.revisions):
            f07.append(f"{cr.id}: Revision {cr.revision_id} 없음")
    for rv in inp.revisions:
        if rv.snapshot_path and not inp.paths.resolve_output(rv.snapshot_path).exists():
            f07.append(f"Revision {rv.number} 스냅샷 파일 없음")
    if not applied and inp.mode == ProjectMode.BUILD:
        _finish(checks[6], review=["반영된 변경 요청이 없음 (검증할 이력 없음)"])
    else:
        _finish(
            checks[6],
            fail=_cap(f07),
            req_ids=[
                x.split(" ")[1]
                for x in f07
                if x.startswith("CR-") and len(x.split(" ")) > 1 and x.split(" ")[1] in all_reqs
            ],
        )
    # 08
    f08, r08 = split(("quality.placeholders",))
    if inp.mode != ProjectMode.PROPOSAL:
        _not_run(checks[7], "구축 단계는 PPT를 생성하지 않음")
    else:
        _finish(checks[7], review=r08 + f08)
    # 09: 정의서 구현 방안·난이도·검사 기준 (Phase 14) — 수용된 구현 대상 요구사항마다 채워져 있는가
    f09: list[str] = []
    r09: list[str] = []
    spec_rows = _spec_rows(spec)
    for r in inp.requirements:
        if (
            r.type.value in ("evaluation", "submission")
            or r.acceptance_status == AcceptanceStatus.REJECTED
            or r.change_state == "deleted"
        ):
            continue
        if not r.implementation_approach:
            f09.append(f"{r.id}: 구현 방안 없음")
        elif r.approach_source == "rule" or "[자동 초안]" in r.implementation_approach:
            r09.append(f"{r.id}: 규칙 초안([자동 초안]) — 사람 확인 필요")
        if r.difficulty is None:
            r09.append(f"{r.id}: 구현 난이도 미기재 (변경 영향 산정 시 '중' 가중치 적용)")
        if not r.acceptance_criteria:
            r09.append(f"{r.id}: 검사 기준 없음")
        row = spec_rows.get(r.id)
        if row is not None:
            if not row.get("구현방안") or row.get("구현방안") == "검토 필요":
                f09.append(f"{r.id}: 정의서 파일의 구현방안 칸이 비어 있음")
            if row.get("구현 난이도") not in ("상", "중", "하"):
                r09.append(f"{r.id}: 정의서 파일의 구현 난이도가 상/중/하가 아님")
    _finish(
        checks[8],
        fail=_cap(f09),
        review=_cap(r09),
        req_ids=[x.split(":")[0] for x in f09 + r09],
        files=_kind_files(inp, DeliverableKind.REQUIREMENT_SPEC_XLSX),
    )
    # 14: 결정·협상 ↔ 기준선 반영 통제 (단계 5, 지시문 §10·§11) — 두 모드 공통
    f14, r14 = _decision_control_issues(inp)
    _finish(checks[13], fail=_cap(f14), review=_cap(r14))
    # 15: 요구 ↔ 설계 객체 추적·모순 (단계 6) — 설계 객체가 있을 때만
    design_screens = [x for x in inp.screens if getattr(x, "source", "design") == "design"]
    if not (design_screens or inp.db_tables or inp.api_specs):
        _not_run(checks[14], "상세 설계 객체 없음 (설계 단계 전)")
    else:
        from proposal_agent.design.consistency import design_consistency_issues

        st = ProjectSettings.from_project_settings(inp.project.settings)
        f15, r15 = design_consistency_issues(
            list(inp.requirements),
            list(inp.screens),
            list(inp.db_tables),
            list(inp.api_specs),
            list(inp.code_modules),
            component_techs=[c.technology for c in inp.components],
            research_stack=[x for t in inp.research for x in t.recommended_stack],
            rfp_specified_tech=[str(x) for x in st.rfp_specified_tech],
        )
        _finish(
            checks[14],
            fail=_cap(f15),
            review=_cap(r15, 12),
            req_ids=[x.split(" ")[0] for x in f15 if x.split(" ")[0] in all_reqs],
        )
    # 10·11: 제안 문안 추상 표현·근거 없는 수치, 약어 미설명 (Phase 19)
    if inp.mode != ProjectMode.PROPOSAL:
        for i in (9, 10, 11, 12):
            _not_run(checks[i], "구축 단계는 PPT를 생성하지 않음")
        return checks
    content = inp.ctx.proposal_content or {}
    sections = [x for x in content.get("sections") or [] if isinstance(x, dict)]
    ppt_files = _kind_files(inp, DeliverableKind.SUBMISSION_PPTX)
    _finish(
        checks[9],
        review=_cap(_abstract_and_number_issues(inp, sections, sub_text), 12),
        files=ppt_files,
    )
    f12, r12, ids12 = _approach_coverage_issues(inp, sub_text)
    _finish(checks[10], fail=_cap(f12), review=_cap(r12), req_ids=ids12, files=ppt_files)
    _finish(
        checks[11],
        review=_cap(_unexplained_acronyms(content, sections, sub_text), 6),
        files=ppt_files,
    )
    f13, r13, ids13 = _design_depth_issues(inp, sub_text)
    _finish(checks[12], fail=_cap(f13), review=_cap(r13), req_ids=ids13, files=ppt_files)
    return checks


def _design_depth_issues(inp: QaInputs, sub_text: str) -> tuple[list[str], list[str], list[str]]:
    """QA-CON-13: 구현 설계(design_writer)의 깊이와 제출용 PPT 반영 (Phase 23).

    - 설계가 없는데 설계 대상 요구가 있으면 검토(설계 작성 필요).
    - 묶음마다 구조 2·절차 3·적용 기술 1·데이터/인터페이스 1 미만이면 실패; 구성 요소 이름·절차 제목·적용 기술이
      덱 본문에 없으면 실패(재생성). 출처 미확인(verified=false) 기술 선택, 설계에서 빠진 요구사항은 검토.
    """
    from proposal_agent.generators.pptx.req_groups import design_texts
    from proposal_agent.requirements.design import (
        design_min_issues,
        design_targets,
        needs_verification,
        resolve_design_ids,
    )

    fails: list[str] = []
    revs: list[str] = []
    ids: list[str] = []
    designs = [d for d in (inp.ctx.designs or []) if isinstance(d, dict)]
    targets = design_targets(list(inp.requirements))
    if not designs:
        if targets:
            revs.append(
                f"구현 설계 없음 — 설계 대상 요구 {len(targets)}건: '구현 설계 작성(에이전트, 웹 검색)' 실행 필요 "
                "(묶음 소절은 정의서 구현방안 표와 기능 블록 도식만 싣는다)"
            )
        return fails, revs, ids
    deck = normalize_text(sub_text)
    covered: set[str] = set()
    for d in designs:
        title = str(d.get("title", "") or "묶음")[:30]
        rids = resolve_design_ids(d, targets)
        covered.update(rids)
        issues = design_min_issues(d)
        if issues:
            fails.append(f"{title}: {', '.join(issues)}")
            ids.extend(rids)
        if deck:
            missing = [t for t in design_texts(d) if normalize_text(t[:25]) not in deck]
            if missing:
                fails.append(
                    f"{title}: 설계 문구 {len(missing)}건이 제출용 PPT에 없음 ({'; '.join(x[:20] for x in missing[:3])})"
                )
                ids.extend(x for x in rids if x not in ids)
        unverified = [
            str(t.get("choice", ""))[:24]
            for t in d.get("tech_choices") or []
            if isinstance(t, dict) and needs_verification(t)
        ]
        if unverified:
            revs.append(
                f"{title}: 출처 미확인 기술 선택 {len(unverified)}건 ({', '.join(unverified[:3])}) — 공식 문서 확인 필요"
            )
    left = [r.id for r in targets if r.id not in covered]
    if left:
        revs.append(f"설계에 없는 요구사항 {len(left)}건: {', '.join(left[:8])}")
        ids.extend(x for x in left if x not in ids)
    return fails, revs, ids


def _approach_coverage_issues(
    inp: QaInputs, sub_text: str
) -> tuple[list[str], list[str], list[str]]:
    """QA-CON-12: 정의서 구현방안 줄(8자 이상)의 앞 25자가 제출용 PPT 본문에 있는지."""
    deck = normalize_text(sub_text)
    fails: list[str] = []
    revs: list[str] = []
    ids: list[str] = []
    if not deck:
        return fails, revs, ids
    for r in inp.requirements:
        if r.type.value not in ("functional", "non_functional") or r.change_state == "deleted":
            continue
        if (
            r.acceptance_status == AcceptanceStatus.REJECTED
            or not (r.implementation_approach or "").strip()
        ):
            continue
        lines = [
            x.strip().lstrip("-•·▪ ").strip()
            for x in (r.implementation_approach or "").splitlines()
            if len(x.strip()) >= 8
        ]
        if not lines:
            continue
        hit = sum(1 for x in lines if normalize_text(x[:25]) in deck)
        if hit == 0:
            msg = f"{r.id} {r.name[:24]}: 구현방안 {len(lines)}줄 중 제안서에 없음"
            (fails if (r.is_mandatory and r.type.value == "functional") else revs).append(msg)
            ids.append(r.id)
        elif hit < len(lines):
            revs.append(f"{r.id} {r.name[:24]}: 구현방안 {len(lines)}줄 중 {hit}줄만 제안서에 있음")
            ids.append(r.id)
    return fails, revs, ids


def _section_texts(sec: dict[str, Any]) -> list[str]:
    out = [
        str(sec.get("title", "") or ""),
        str(sec.get("key_message", "") or ""),
        str(sec.get("lead_message", "") or ""),
        str(sec.get("body", "") or ""),
        *[str(x) for x in sec.get("bullets", []) or []],
        *[str(c) for r in sec.get("table_rows", []) or [] for c in r],
    ]
    vis = sec.get("visual")
    if isinstance(vis, dict):
        out.append(str(vis.get("title", "") or ""))
        out.extend(f"{x.get('title', '')} {x.get('text', '')}" for x in vis.get("items", []) or [])
        out.extend(str(c) for r in vis.get("rows", []) or [] for c in r)
    td = sec.get("tech_detail")
    if isinstance(td, dict):
        for k in ("components", "interfaces", "data", "operations", "security"):
            out.extend(str(x) for x in td.get(k, []) or [])
        out.append(str(td.get("selection_reason", "") or ""))
        for a in td.get("alternatives", []) or []:
            out.append(f"{a.get('name', '')} {a.get('cost_note', '')} {a.get('basis', '')}")
            out.extend(str(x) for x in (a.get("pros") or []) + (a.get("cons") or []))
    return [x for x in out if x]


def _section_label(sec: dict[str, Any]) -> str:
    return str(sec.get("number") or "").strip() or str(sec.get("title", ""))[:20]


def _base_number_tokens(inp: QaInputs) -> set[str]:
    """기준 데이터 안의 숫자 토큰(쉼표 제거). 제안 문안의 수치가 여기 없으면 '근거 없는 수치'."""
    parts: list[str] = []
    for r in inp.all_requirements or inp.requirements:
        parts.extend(
            (
                r.name,
                r.description,
                r.implementation_approach or "",
                r.acceptance_criteria,
                r.difficulty_basis,
            )
        )
    for t in inp.research:
        parts.extend((t.topic, t.summary, *t.unverified_items, *t.recommended_stack))
        parts.extend(f"{src.title} {src.url}" for src in t.sources)
    parts.extend(b.text for b in inp.blocks)
    parts.extend(w.name for w in inp.ctx.wbs)
    parts.extend(str(getattr(w, "estimate_basis", "") or "") for w in inp.ctx.wbs)
    parts.extend(str(w.effort_md) for w in inp.ctx.wbs)
    parts.append(str(inp.ctx.total_effort_md))
    parts.extend(f"{r.role_name} {r.headcount_planned}" for r in inp.ctx.roles)
    parts.append(str(len(inp.ctx.requirements)))
    parts.append(str(len(inp.ctx.mandatory_requirements())))
    # 범위 분류·유형·수용 상태별 건수 ("부가 제안 2건" 같은 집계 수치의 근거)
    for attr in ("scope_class", "type", "acceptance_status", "category"):
        cnt: dict[str, int] = {}
        for r in inp.ctx.requirements:
            cnt[str(getattr(r, attr, ""))] = cnt.get(str(getattr(r, attr, "")), 0) + 1
        parts.extend(str(v) for v in cnt.values())
    parts.append(str(len(inp.ctx.roles)))
    parts.append(str(sum(r.headcount_planned for r in inp.ctx.roles)))
    if inp.ctx.period_start and inp.ctx.period_end:
        days = (inp.ctx.period_end - inp.ctx.period_start).days
        parts.extend((str(days), str(round(days / 30)), str(round(days / 30.4)), str(days // 7)))
    analysis = inp.ctx.analysis or {}
    parts.append(str(analysis))
    corpus = " ".join(parts)
    return {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", corpus)}


def _abstract_and_number_issues(
    inp: QaInputs, sections: list[dict[str, Any]], ppt_text: str
) -> list[str]:
    issues: list[str] = []
    if not sections:
        found = sorted({w for w in ABSTRACT_WORDS if w in ppt_text})
        if found:
            issues.append("제출용 PPT 본문의 추상 표현 (제안 문안 없음): " + ", ".join(found[:8]))
        return issues
    base = _base_number_tokens(inp)
    for sec in sections:
        text = "\n".join(_section_texts(sec))
        label_ = _section_label(sec)
        words = [w for w in ABSTRACT_WORDS if w in text]
        if words:
            issues.append(f"[{label_}] 추상 표현: {', '.join(words[:4])}")
        evidence_text = " ".join(
            f"{e.get('ref', '')} {e.get('text', '')}"
            for e in sec.get("evidence", []) or []
            if isinstance(e, dict)
        )
        ev_tokens = {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", evidence_text)}
        unsupported: list[str] = []
        for num, unit in NUMBER_CLAIM_RE.findall(text):
            tok = num.replace(",", "")
            if tok in base or tok in ev_tokens or tok in unsupported:
                continue
            unsupported.append(f"{num}{unit}")
        if unsupported:
            issues.append(
                f"[{label_}] 근거 없는 수치: {', '.join(dict.fromkeys(unsupported).keys())}"
                + ("" if sec.get("evidence") else " (evidence 없음)")
            )
    return issues


def _unexplained_acronyms(
    content: dict[str, Any], sections: list[dict[str, Any]], ppt_text: str
) -> list[str]:
    glossary = {
        str(g.get("term", "")).upper() for g in content.get("glossary") or [] if isinstance(g, dict)
    } | {
        str(g.get("full_form", "")).upper()
        for g in content.get("glossary") or []
        if isinstance(g, dict)
    }
    text = "\n".join(t for sec in sections for t in _section_texts(sec)) if sections else ppt_text
    if not text.strip():
        return []
    first_where: dict[str, str] = {}
    if sections:
        for sec in sections:
            for m in ACRONYM_RE.findall("\n".join(_section_texts(sec))):
                first_where.setdefault(m, _section_label(sec))
    unexplained: list[str] = []
    for acr in dict.fromkeys(ACRONYM_RE.findall(text)):
        parts = [p for p in acr.split("/") if p]
        if all(
            p in COMMON_ACRONYMS or ROMAN_RE.match(p) or p.isdigit() or p in glossary for p in parts
        ):
            continue  # 'UI/UX' 처럼 슬래시로 묶인 약어는 각각 설명되어 있으면 통과
        if re.search(rf"{re.escape(acr)}\s*[\(（]|[\(（]\s*{re.escape(acr)}\s*[\)）]", text):
            continue  # 본문에서 '약어(풀이)' 또는 '풀이(약어)'로 설명됨
        unexplained.append(acr + (f"({first_where[acr]})" if acr in first_where else ""))
    if not unexplained:
        return []
    src = "제안 문안" if sections else "제출용 PPT 본문 (제안 문안 없음)"
    return [
        f"{src} 약어 미설명 {len(unexplained)}건: " + ", ".join(unexplained[:15]),
        "용어집(glossary)에 용어·풀이·비전문가용 설명을 추가하거나 첫 등장 시 괄호로 풀어쓰기",
    ]


def _decision_control_issues(inp: QaInputs) -> tuple[list[str], list[str]]:
    """QA-CON-14: 결정 권한·협상 합의·변경 요청 원천의 정합성 (단계 5).

    - 실패: 권한 미확인인데 승인 상태인 결정, 승인자 없는 승인 결정, 고객 합의·승인자 없이 '반영'인 협상,
      변경 요청이 가리키는 결정·협상이 승인/합의 상태가 아님.
    - 검토: 기한이 지난 미결 질문·조치 항목, 승인된 공식 결정인데 관련 요구가 있으면서 변경 요청이 없는 것.
    """
    from datetime import date as _date

    fails: list[str] = []
    revs: list[str] = []
    dec_by_id = {d.id: d for d in inp.decisions}
    neg_by_id = {n.id: n for n in inp.negotiations}
    today = _date.today()
    for d in inp.decisions:
        status = getattr(d.status, "value", str(d.status))
        kind = getattr(d.kind, "value", str(d.kind))
        if status == "approved" and not d.authority_confirmed:
            fails.append(f"{d.code}: 권한 미확인 결정이 승인 상태")
        if status == "approved" and not d.approved_by:
            fails.append(f"{d.code}: 승인자 없는 승인 결정")
        if (
            kind in ("open_question", "action_item")
            and status not in ("resolved", "rejected")
            and d.due_date
            and d.due_date < today
        ):
            revs.append(f"{d.code}: 기한 경과 미결·조치 항목 ({d.due_date})")
    for n in inp.negotiations:
        status = getattr(n.status, "value", str(n.status))
        if status == "applied" and not (n.customer_agreed is True and n.approved_by):
            fails.append(f"{n.code}: 고객 합의·승인 없이 '반영' 상태")
        if status == "agreed" and n.customer_agreed is not True:
            fails.append(f"{n.code}: 고객 합의 미확인인데 '합의' 상태")
    for cr in inp.change_requests:
        for did in getattr(cr, "decision_ids", []) or []:
            d = dec_by_id.get(did)
            if d is None:
                fails.append(f"{cr.id}: 원천 결정 {did} 없음")
            elif not d.is_binding:
                fails.append(f"{cr.id}: 원천 결정 {d.code} 가 승인된 공식 결정이 아님")
        nid = getattr(cr, "negotiation_id", None)
        if nid:
            n = neg_by_id.get(nid)
            if n is None:
                fails.append(f"{cr.id}: 원천 협상 {nid} 없음")
            elif not (n.customer_agreed is True and n.approved_by):
                fails.append(f"{cr.id}: 원천 협상 {n.code} 가 고객 합의·승인 상태가 아님")
    return fails, revs
