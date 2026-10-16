"""QA-TECH: 기술 타당성 검사 (independent_qa 분할)."""

from __future__ import annotations

import re

from proposal_agent.models import (
    AcceptanceStatus,
    FeasibilityVerdict,
    ProjectMode,
    QaCategory,
    QaCheck,
    RequirementCategory,
    RequirementType,
)
from proposal_agent.validation.qa_checks.common import VERSION_RE, QaInputs, _cap, _check, _finish


# --- 기술 타당성 -------------------------------------------------------------------------------
def check_tech_feasibility(inp: QaInputs, ppt_texts: dict[str, list[str]]) -> list[QaCheck]:
    gate = "gate2"
    cat = QaCategory.TECH_FEASIBILITY
    checks = [
        _check(
            "QA-TECH-01",
            cat,
            "기술 조사 구현 가능성 ↔ 수용 요구사항",
            "구현 불가(infeasible)로 조사된 요구사항이 수용으로 표시되지 않았는가, 미확인(unknown)인 필수 요구사항이 없는가",
            gate=gate,
            fix_suggestion="해당 요구사항의 수용 여부를 '조건부 수용/미수용'으로 바꾸거나 추가 조사를 수행",
        ),
        _check(
            "QA-TECH-02",
            cat,
            "조사 미확인 사항",
            "확인되지 않은 솔루션 기능·주장이 남아 있지 않은가",
            gate=gate,
            mandatory=False,
            fix_suggestion="미확인 항목을 공식 문서로 확인하거나 제안서에서 '확인 필요'로 표기",
        ),
        _check(
            "QA-TECH-03",
            cat,
            "버전 호환성",
            "같은 제품이 서로 다른 버전으로 조사·명시되지 않았는가",
            gate=gate,
            mandatory=False,
            fix_suggestion="적용 버전을 하나로 확정하고 구성 요소·조사 기록을 맞춤",
        ),
        _check(
            "QA-TECH-04",
            cat,
            "기술 간 연계",
            "구성 요소 연결이 존재하는 구성 요소를 가리키고, RFP 연계 대상마다 연계 구성 요소가 있는가",
            gate=gate,
            fix_suggestion="아키텍처 구성 요소·연결을 보완",
        ),
        _check(
            "QA-TECH-05",
            cat,
            "보안·성능·운영 위험",
            "조사에서 식별된 위험과 보안·성능 요구사항에 대응 구성 요소가 있는가",
            gate=gate,
            mandatory=False,
            fix_suggestion="위험 대응 방안을 제안서·아키텍처에 반영",
        ),
        _check(
            "QA-TECH-07",
            cat,
            "기능 요구사항 구현 근거",
            "수용된 필수 기능 요구사항마다 구현 방안이 있고, 구현 가능(feasible/with_risk)으로 조사된 근거 기록이 연결되어 있는가 (조사 선행 원칙)",
            gate=gate,
            fix_suggestion="기술 조사를 실행해 해당 요구사항을 조사 주제에 연결하고 구현 방안을 확정",
        ),
        _check(
            "QA-TECH-06",
            cat,
            "기술 주장 근거",
            "구성 요소·제안서가 언급한 기술이 출처 있는 조사 기록으로 뒷받침되는가",
            gate=gate,
            mandatory=False,
            fix_suggestion="기술 조사를 실행하거나 근거 없는 기술명을 '검토 필요'로 바꿈",
        ),
        _check(
            "QA-TECH-08",
            cat,
            "구현 설계 재검증 (구현 후)",
            "구현 설계의 적용 기술이 아키텍처 구성 요소·조사 사실과 모순되지 않고, 대안 비교의 추천안이 비교 대안 중 하나이며, PoC 필요 항목과 필수 기능 요구사항의 14항목 기술 검토 누락이 검토 목록에 드러나는가 (지시문 §4.4)",
            gate=gate,
            mandatory=False,
            fix_suggestion="설계·아키텍처·조사를 맞추고, PoC 를 수행하거나 미검증으로 남기며, 구현 방안 에이전트로 analysis 를 채움",
        ),
    ]
    reqs = {r.id: r for r in inp.requirements}
    research = inp.research
    # 01
    fail01: list[str] = []
    rev01: list[str] = []
    for tr in research:
        for rid in tr.related_requirement_ids:
            r = reqs.get(rid)
            if r is None:
                continue
            if tr.feasibility == FeasibilityVerdict.INFEASIBLE and r.acceptance_status in (
                AcceptanceStatus.ACCEPTED,
                AcceptanceStatus.PROPOSED,
            ):
                fail01.append(f"{rid}: 조사 '{tr.topic}' 구현 불가인데 수용/제안 상태")
            elif tr.feasibility == FeasibilityVerdict.UNKNOWN and r.is_mandatory:
                rev01.append(f"{rid}: 조사 '{tr.topic}' 구현 가능성 미확인")
            elif tr.feasibility == FeasibilityVerdict.FEASIBLE_WITH_RISK:
                rev01.append(f"{rid}: '{tr.topic}' 위험 동반 구현 가능 — 위험 수용 여부 확인")
    if not research and inp.mode == ProjectMode.PROPOSAL:
        rev01.append("기술 조사 기록이 없어 구현 가능성을 확인하지 못함 (tech_researcher 미실행)")
    _finish(
        checks[0],
        fail=fail01,
        review=rev01,
        req_ids=[x.split(":")[0] for x in fail01 + rev01 if ":" in x],
    )
    # 02
    unverified = [f"'{tr.topic}': {u}" for tr in research for u in tr.unverified_items]
    _finish(checks[1], review=_cap(unverified) if unverified else [])
    # 03
    versions: dict[str, set[str]] = {}
    for tr in research:
        for s in tr.sources:
            if s.product and s.version:
                versions.setdefault(s.product.casefold(), set()).add(s.version)
    for c in inp.components:
        m = VERSION_RE.search(c.technology)
        if m:
            name = VERSION_RE.sub("", c.technology).strip(" /v").casefold()
            if name:
                versions.setdefault(name, set()).add(m.group(1))
    conflicts = [f"{p}: {', '.join(sorted(v))}" for p, v in versions.items() if len(v) > 1]
    _finish(checks[2], review=conflicts)
    # 04
    comp_ids = {c.id for c in inp.components}
    fail04 = [
        f"{c.name}: 존재하지 않는 구성 요소 {conn.to_component_id} 연결"
        for c in inp.components
        for conn in c.connections
        if conn.to_component_id not in comp_ids
    ]
    rev04: list[str] = []
    targets = (inp.rfp_analysis or {}).get("integration_targets") or []
    integ = [c for c in inp.components if c.layer == "integration"]
    if targets and not integ:
        rev04.append(
            f"RFP 연계 대상 {len(targets)}건({', '.join(map(str, targets[:3]))}…)에 대응하는 연계(integration) 구성 요소 없음"
        )
    _finish(checks[3], fail=fail04, review=rev04)
    # 05
    risks = [f"'{tr.topic}': {rk}" for tr in research for rk in tr.risks]
    sec_reqs = [
        r
        for r in inp.requirements
        if r.category
        in (
            RequirementCategory.SECURITY,
            RequirementCategory.PERFORMANCE,
            RequirementCategory.AVAILABILITY,
        )
    ]
    layers = {c.layer for c in inp.components}
    rev05 = _cap(risks)
    if sec_reqs and "security" not in layers and "infra" not in layers:
        rev05.append(
            f"보안·성능·가용성 요구사항 {len(sec_reqs)}건이 있으나 보안/인프라 구성 요소가 없음"
        )
    _finish(checks[4], review=rev05, req_ids=[r.id for r in sec_reqs] if rev05 else [])
    # 07: 기능 요구사항 구현 근거 (조사 선행)
    fail07: list[str] = []
    rev07: list[str] = []
    ok_verdicts = (FeasibilityVerdict.FEASIBLE, FeasibilityVerdict.FEASIBLE_WITH_RISK)
    for r in inp.requirements:
        if r.type != RequirementType.FUNCTIONAL or not r.is_mandatory:
            continue
        if r.acceptance_status not in (
            AcceptanceStatus.ACCEPTED,
            AcceptanceStatus.PARTIALLY_ACCEPTED,
        ):
            continue
        linked = [
            t
            for t in research
            if r.id in t.related_requirement_ids
            or (r.rfp_requirement_id and r.rfp_requirement_id in t.related_requirement_ids)
        ]
        if not r.implementation_approach:
            rev07.append(f"{r.id}: 구현 방안 미작성")
        elif r.approach_source == "rule" or "[자동 초안]" in r.implementation_approach:
            rev07.append(
                f"{r.id}: 구현 방안 미확정(규칙 초안 [자동 초안] — 에이전트 작성 또는 사람 확정 필요)"
            )
        if not linked:
            rev07.append(f"{r.id}: 근거 조사 없음 (웹 검색 기반 기술 조사 필요)")
        elif not any(t.feasibility in ok_verdicts for t in linked):
            rev07.append(
                f"{r.id}: 연결된 조사가 구현 가능으로 확인되지 않음 ({', '.join(t.feasibility.value for t in linked[:3])})"
            )
    _finish(checks[5], fail=fail07, review=_cap(rev07), req_ids=[x.split(":")[0] for x in rev07])
    # 06
    evidence = " ".join(
        [
            *(f for tr in research for f in tr.confirmed_facts),
            *(s for tr in research for s in tr.recommended_stack),
            *(src.product for tr in research for src in tr.sources),
            *(tr.summary for tr in research),
        ]
    ).casefold()
    techs = {
        c.technology
        for c in inp.components
        if c.technology and "미정" not in c.technology and "검토" not in c.technology
    }
    unbacked = [
        t
        for t in techs
        if not any(
            tok and tok.casefold() in evidence for tok in re.split(r"[\s/,+]+", t) if len(tok) >= 3
        )
    ]
    rev06 = [f"근거 조사 없는 기술: {t}" for t in sorted(unbacked)]
    if not techs and inp.mode == ProjectMode.PROPOSAL:
        rev06.append("구성 요소 기술이 모두 미정 — 아키텍처 확정 필요")
    _finish(checks[6], review=rev06)
    # 08: 구현 설계 재검증 (단계 3)
    if inp.mode != ProjectMode.PROPOSAL:
        from proposal_agent.validation.qa_checks.common import _not_run

        _not_run(checks[7], "구축 단계는 구현 설계 재검증 대상 아님")
        return checks
    f08, r08, ids08 = _design_reverification_issues(
        [d for d in (inp.ctx.designs or []) if isinstance(d, dict)],
        list(inp.requirements),
        inp.components,
        research,
    )
    _finish(checks[7], fail=_cap(f08), review=_cap(r08, 12), req_ids=ids08)
    return checks


def _design_reverification_issues(
    designs: list[dict],
    requirements: list,
    components: list,
    research: list,
) -> tuple[list[str], list[str], list[str]]:
    """설계 ↔ 아키텍처·조사 일치, 대안 비교 정합성, PoC 필요, 14항목 분석 누락."""
    fails: list[str] = []
    revs: list[str] = []
    ids: list[str] = []
    evidence = " ".join(
        [
            *(f for tr in research for f in tr.confirmed_facts),
            *(s for tr in research for s in tr.recommended_stack),
            *(src.product for tr in research for src in tr.sources),
            *(tr.summary for tr in research),
            *(c.technology for c in components),
            *(c.name for c in components),
        ]
    ).casefold()
    for d in designs:
        title = str(d.get("title", "") or "묶음")[:30]
        for t in d.get("tech_choices") or []:
            if not isinstance(t, dict):
                continue
            src = str(t.get("source", "") or "").strip()
            choice = str(t.get("choice", "") or "")
            if src in ("설계 제안", "자체 설계", "RFP") or src.upper() == "RFP":
                continue
            toks = [x for x in re.split(r"[\s/,+()·:]+", choice) if len(x) >= 3 and not x.isdigit()]
            if toks and not any(tok.casefold() in evidence for tok in toks):
                revs.append(
                    f"{title}: 적용 기술 '{choice[:30]}' 이 아키텍처 구성 요소·조사 기록에 없음 — 조사 연결 또는 설계 근거 확인"
                )
        for cmp in d.get("comparisons") or []:
            if not isinstance(cmp, dict):
                continue
            names = [
                str(o.get("name", "")) for o in cmp.get("options", []) or [] if isinstance(o, dict)
            ]
            rec = str(cmp.get("recommended", "") or "")
            if rec and rec not in names:
                fails.append(
                    f"{title}: 대안 비교 '{cmp.get('topic', '')}' 의 추천안 '{rec}' 이 비교 대안({', '.join(names)}) 에 없음"
                )
            if cmp.get("poc_needed"):
                revs.append(
                    f"{title}: PoC 필요 — {cmp.get('topic', '')}: {cmp.get('poc_scope', '') or '범위 미정'}"
                )
    missing = [
        r.id
        for r in requirements
        if r.type == RequirementType.FUNCTIONAL
        and r.is_mandatory
        and r.acceptance_status != AcceptanceStatus.REJECTED
        and r.change_state != "deleted"
        and not r.analysis
    ]
    if missing:
        revs.append(
            f"필수 기능 요구사항 {len(missing)}건에 14항목 기술 검토(analysis) 없음: {', '.join(missing[:8])}"
        )
        ids.extend(missing)
    return fails, revs, ids
