"""WBS 를 설계 항목(코드 모듈) 까지 분해 (지시문 §13.1, 단계 7 ①).

모듈마다 '구현: <모듈>' Task 를, 모듈의 요구사항과 가장 많이 겹치는 기존 Task 의 상위(Activity) 아래에 추가한다(코드 3단계 유지).
공수는 계층별 기준 MD × 요구 난이도 가중치이며 산정 근거를 남긴다. 상위 항목 공수는 자식 합계로 다시 계산한다.
"""

from __future__ import annotations

from decimal import Decimal

from proposal_agent.models import CodeModule, Project, Requirement, WBSItem, WBSLevel
from proposal_agent.planning.effort import rollup
from proposal_agent.storage.repositories import Repositories

LAYER_BASE_MD: dict[str, Decimal] = {
    "controller": Decimal("2"),
    "service": Decimal("3"),
    "repository": Decimal("2"),
    "domain": Decimal("2"),
    "web": Decimal("3"),
    "batch": Decimal("3"),
    "integration": Decimal("4"),
    "common": Decimal("1"),
}
DIFFICULTY_FACTOR = {"high": Decimal("1.5"), "medium": Decimal("1.0"), "low": Decimal("0.7")}


def module_effort(module: CodeModule, reqs: dict[str, Requirement]) -> tuple[Decimal, str]:
    base = LAYER_BASE_MD.get((module.layer or "").lower(), Decimal("2"))
    levels = [
        d.value
        for d in (reqs[r].difficulty for r in module.related_requirement_ids if r in reqs)
        if d is not None
    ]
    worst = (
        "high"
        if "high" in levels
        else "medium"
        if "medium" in levels
        else "low"
        if levels
        else "medium"
    )
    factor = DIFFICULTY_FACTOR[worst]
    md = (base * factor).quantize(Decimal("0.5"))
    return (
        md,
        f"계층 {module.layer or '미지정'} 기준 {base}MD × 난이도 {worst} 가중 {factor} (설계 모듈 분해)",
    )


def decompose_wbs_to_modules(
    repos: Repositories, project: Project, *, actor: str = "user"
) -> tuple[list[WBSItem], list[str]]:
    items = repos.wbs.tree(project.id)
    if not items:
        return [], ["WBS 가 없어 분해할 수 없습니다 — 계획(WBS) 을 먼저 세우십시오."]
    modules = [
        m for m in repos.code_modules.find(project.id, order_by="code") if m.status != "dropped"
    ]
    if not modules:
        return [], ["코드 모듈이 없습니다 — 상세 설계를 먼저 실행하십시오."]
    reqs = {r.id: r for r in repos.requirements.find(project.id)}
    by_id = {i.id: i for i in items}
    by_code = {i.code: i for i in items}
    existing_names = {i.name for i in items}
    added: list[WBSItem] = []
    warnings: list[str] = []
    for m in modules:
        name = f"구현: {m.name or m.path}"
        if name in existing_names:
            continue
        mreq = set(m.related_requirement_ids)
        best, best_score = None, 0
        for it in items:
            score = len(mreq & set(it.related_requirement_ids))
            if score > best_score:
                best, best_score = it, score
        if best is None:
            best = next(
                (
                    i
                    for i in items
                    if i.level == WBSLevel.ACTIVITY and any(k in i.name for k in ("구현", "개발"))
                ),
                None,
            )
        if best is None:
            warnings.append(f"{m.code}: 겹치는 WBS 항목이 없어 분해하지 않음")
            continue
        parent = best if best.level == WBSLevel.ACTIVITY else by_id.get(best.parent_id or "", None)
        if parent is None or parent.level == WBSLevel.PHASE and best.level == WBSLevel.TASK:
            parent = best if best.level != WBSLevel.TASK else parent
        if parent is None:
            warnings.append(f"{m.code}: 상위 Activity 를 찾지 못해 분해하지 않음")
            continue
        siblings = [i for i in items + added if i.parent_id == parent.id]
        code = f"{parent.code}.{len(siblings) + 1}"
        while code in by_code:
            code = code.rsplit(".", 1)[0] + "." + str(int(code.rsplit(".", 1)[1]) + 1)
        md, basis = module_effort(m, reqs)
        item = WBSItem(
            project_id=project.id,
            code=code,
            parent_id=parent.id,
            level=WBSLevel.TASK,
            name=name,
            description=m.description,
            related_requirement_ids=list(m.related_requirement_ids),
            role="개발자",
            category=parent.category,
            quantity=f"모듈 1 ({m.path})",
            planned_start=parent.planned_start,
            planned_end=parent.planned_end,
            effort_md=md,
            estimate_basis=basis,
            created_by=actor,
        )
        repos.wbs.insert(item)
        by_code[code] = item
        added.append(item)
        existing_names.add(name)
    if added:
        all_items = repos.wbs.tree(project.id)
        parent_of = {
            i.code: (
                by_id.get(i.parent_id or "", None)
                or next((x for x in all_items if x.id == i.parent_id), None)
            )
            for i in all_items
        }
        totals = rollup(
            {i.code: i.effort_md for i in all_items},
            {c: (p.code if p else None) for c, p in parent_of.items()},
        )
        for i in all_items:
            kids = [x for x in all_items if x.parent_id == i.id]
            if kids and totals.get(i.code) is not None and i.effort_md != totals[i.code]:
                i.effort_md = totals[i.code]
                i.touch()
                repos.wbs.update(i)
    return added, warnings


__all__ = ["DIFFICULTY_FACTOR", "LAYER_BASE_MD", "decompose_wbs_to_modules", "module_effort"]
