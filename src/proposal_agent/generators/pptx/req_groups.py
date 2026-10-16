"""요구사항 묶음별 구현 방안 소절 (Phase 22).

제안서는 요구사항을 하나씩 나열하지 않고 **내용상 묶어야 하는 요구사항을 한 소절**로 다룬다(예: 민원 접수·배정·종결을
한 워크플로로). 묶음은 ① 제안 문안 에이전트가 ``requirement_groups`` 로 지정한 것을 우선 쓰고, ② 없으면 코드가
RFP 고유번호(같은 RFP 항목의 세부 요구) → 분류(category) 순으로 묶는다. 각 묶음은 정의서의 구현방안 **전문**을
표로 싣는다(잘라 쓰지 않음). 덱에 실린 내용이 정의서와 같은지는 QA-CON-12 가 대조한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from proposal_agent.generators.base import GenerationContext
from proposal_agent.models import Requirement, RequirementType

MAX_GROUP_SIZE = 6  # 한 묶음에 넣는 요구사항 수 상한 (넘으면 (1/2) 로 나눈다)

CATEGORY_TITLES = {
    "ui": "화면·사용자 경험",
    "business": "업무 기능",
    "data": "데이터",
    "interface": "연계",
    "report": "조회·통계",
    "admin": "관리 기능",
    "performance": "성능",
    "security": "보안",
    "availability": "가용성",
    "compatibility": "호환성·표준",
    "operability": "운영·유지관리",
    "constraint": "제약 준수",
    "other": "기타",
}
ACTOR_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("회원사·외부 사용자", ("회원사", "회원", "소비자", "이용자", "민원인", "고객")),
    ("협회·업무 담당자", ("협회", "담당자", "심사", "관리자", "운영자")),
    ("시스템 관리자", ("관리 기능", "코드", "메뉴", "권한", "계정")),
)
EXTERNAL_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("비식별 솔루션", ("비식별", "마스킹", "OCR")),
    ("알림 채널", ("알림", "카카오", "알림톡", "SMS", "문자")),
    ("외부 기관", ("검찰", "기관", "금감원", "외부")),
    ("기존 시스템", ("기존", "현행", "홈페이지", "공시")),
    ("DB", ("DB", "데이터베이스", "저장소")),
)


@dataclass
class RequirementGroup:
    title: str
    requirements: list[Requirement]
    key_message: str = ""
    summary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source: str = "code"  # agent | code
    rfp_ids: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [r.id for r in self.requirements]


def _eligible(ctx: GenerationContext) -> list[Requirement]:
    out: list[Requirement] = []
    for r in ctx.requirements:
        if r.type not in (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL):
            continue
        if r.change_state == "deleted" or r.acceptance_status.value == "rejected":
            continue
        if not (r.implementation_approach or "").strip():
            continue
        out.append(r)
    return out


def _agent_groups(ctx: GenerationContext, pool: list[Requirement]) -> list[RequirementGroup]:
    specs = (ctx.proposal_content or {}).get("requirement_groups") or []
    by_id = {r.id: r for r in pool}
    by_rfp: dict[str, list[Requirement]] = {}
    for r in pool:
        if r.rfp_requirement_id:
            by_rfp.setdefault(r.rfp_requirement_id, []).append(r)
    used: set[str] = set()
    groups: list[RequirementGroup] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        reqs: list[Requirement] = []
        for rid in spec.get("requirement_ids", []) or []:
            rid = str(rid)
            if rid in by_id and rid not in used:
                reqs.append(by_id[rid])
                used.add(rid)
            elif rid in by_rfp:  # RFP 고유번호로 묶음 지정
                for r in by_rfp[rid]:
                    if r.id not in used:
                        reqs.append(r)
                        used.add(r.id)
        if not reqs:
            continue
        groups.append(
            RequirementGroup(
                title=str(spec.get("title", "") or "요구사항 묶음")[:60],
                requirements=reqs,
                key_message=str(spec.get("key_message", "") or ""),
                summary=[str(x) for x in spec.get("summary", []) or []][:4],
                notes=[str(x) for x in spec.get("notes", []) or []][:3],
                source="agent",
                rfp_ids=sorted({r.rfp_requirement_id for r in reqs if r.rfp_requirement_id}),
            )
        )
    rest = [r for r in pool if r.id not in used]
    return groups + _code_groups(rest)


def _code_groups(pool: list[Requirement]) -> list[RequirementGroup]:
    """RFP 고유번호가 같은 세부 요구(2건 이상) → 한 묶음, 나머지는 분류별."""
    by_rfp: dict[str, list[Requirement]] = {}
    for r in pool:
        by_rfp.setdefault(r.rfp_requirement_id or "", []).append(r)
    groups: list[RequirementGroup] = []
    leftovers: list[Requirement] = []
    for rfp_id, reqs in by_rfp.items():
        if rfp_id and len(reqs) >= 2:
            title = _common_title(reqs) or f"{rfp_id} 요구사항"
            groups.append(RequirementGroup(title=title, requirements=reqs, rfp_ids=[rfp_id]))
        else:
            leftovers.extend(reqs)
    by_cat: dict[str, list[Requirement]] = {}
    for r in leftovers:
        by_cat.setdefault(r.category.value, []).append(r)
    for cat, reqs in by_cat.items():
        groups.append(
            RequirementGroup(
                title=f"{CATEGORY_TITLES.get(cat, cat)} 요구사항",
                requirements=reqs,
                rfp_ids=sorted({r.rfp_requirement_id for r in reqs if r.rfp_requirement_id}),
            )
        )
    return groups


def _common_title(reqs: list[Requirement]) -> str:
    areas = [r.business_area for r in reqs if r.business_area]
    if areas:
        return max(set(areas), key=areas.count)[:60]
    names = [r.name for r in reqs]
    first = names[0]
    for n in names[1:]:
        i = 0
        while i < min(len(first), len(n)) and first[i] == n[i]:
            i += 1
        first = first[:i]
    first = first.strip(" ").rstrip("·(-").strip()
    return first if len(first) >= 4 else ""


def _split(groups: list[RequirementGroup]) -> list[RequirementGroup]:
    out: list[RequirementGroup] = []
    for g in groups:
        if len(g.requirements) <= MAX_GROUP_SIZE:
            out.append(g)
            continue
        parts = math.ceil(len(g.requirements) / MAX_GROUP_SIZE)
        size = math.ceil(len(g.requirements) / parts)
        for i in range(parts):
            chunk = g.requirements[i * size : (i + 1) * size]
            out.append(
                RequirementGroup(
                    title=f"{g.title} ({i + 1}/{parts})",
                    requirements=chunk,
                    key_message=g.key_message if i == 0 else "",
                    summary=g.summary if i == 0 else [],
                    notes=g.notes,
                    source=g.source,
                    rfp_ids=g.rfp_ids,
                )
            )
    return out


def group_requirements(ctx: GenerationContext) -> list[RequirementGroup]:
    """제안서에 실을 요구사항 묶음 (에이전트 지정 우선, 나머지 코드 묶음). 구현방안이 없는 요구는 제외."""
    pool = _eligible(ctx)
    if not pool:
        return []
    groups = (
        _agent_groups(ctx, pool)
        if (ctx.proposal_content or {}).get("requirement_groups")
        else _code_groups(pool)
    )
    groups = [g for g in groups if g.requirements]
    for g in groups:
        if not g.key_message:
            g.key_message = default_key_message(g)
    return _split(groups)


def default_key_message(g: RequirementGroup) -> str:
    n = len(g.requirements)
    hard = sum(1 for r in g.requirements if difficulty_label(r) == "상")
    tail = f" (난이도 상 {hard}건은 조사·PoC 근거로 확정)" if hard else ""
    return f"{g.title} 요구 {n}건을 정의서의 구현 방안대로 구현한다{tail}"[:90]


def approach_lines(req: Requirement) -> list[str]:
    """정의서 구현방안을 줄 단위로 (글머리 기호 제거). 전제·협의 문구는 별도 분리 가능."""
    out: list[str] = []
    for raw in (req.implementation_approach or "").splitlines():
        t = raw.strip().lstrip("-•·▪ ").strip()
        if t:
            out.append(t)
    return out


def premises(group: RequirementGroup) -> list[str]:
    """'전제:' 로 시작하거나 '협의' 가 든 줄 → 하단 ※ 주석 후보."""
    out: list[str] = []
    for r in group.requirements:
        for line in approach_lines(r):
            if line.startswith("전제") or "협의" in line:
                out.append(f"{r.id}: {line}")
    return out[:3]


def function_block_spec(group: RequirementGroup) -> dict[str, Any]:
    """묶음을 '사용자 → 시스템 기능 상자 → 연계 대상' 블록 도식(spec)으로."""
    text = " ".join(f"{r.name} {r.implementation_approach or ''}" for r in group.requirements)
    actors = [label for label, hints in ACTOR_HINTS if any(h in text for h in hints)][:3] or [
        "사용자"
    ]
    externals = [label for label, hints in EXTERNAL_HINTS if any(h in text for h in hints)][:3]
    return {
        "title": group.title,
        "actors": actors,
        "functions": [
            {
                "id": r.id,
                "title": _short_name(r.name),
                "text": difficulty_label(r) if r.difficulty else "",
            }
            for r in group.requirements
        ],
        "externals": externals,
    }


def difficulty_label(req: Requirement) -> str:
    d = req.difficulty
    if d is None:
        return "-"
    return str(
        getattr(d, "label", None) or {"high": "상", "medium": "중", "low": "하"}.get(str(d), str(d))
    )


def _short_name(name: str) -> str:
    base = name.split("(")[0].strip()
    return base[:22]


def approach_table_rows(group: RequirementGroup) -> list[list[str]]:
    rows: list[list[str]] = []
    for r in group.requirements:
        rfp = f" / {r.rfp_requirement_id}" if r.rfp_requirement_id else ""
        approach = "\n".join(f"• {x}" for x in approach_lines(r))
        verify = " / ".join(
            x
            for x in ((r.verification_method or "").strip(), (r.acceptance_criteria or "").strip())
            if x
        )
        rows.append([f"{r.id}{rfp}\n{r.name}", approach, difficulty_label(r), verify or "-"])
    return rows


__all__ = [
    "MAX_GROUP_SIZE",
    "RequirementGroup",
    "approach_lines",
    "approach_table_rows",
    "default_key_message",
    "function_block_spec",
    "group_requirements",
    "premises",
]
