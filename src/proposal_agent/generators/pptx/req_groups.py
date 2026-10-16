"""요구사항 묶음별 구현 방안 소절 (Phase 22).

제안서는 요구사항을 하나씩 나열하지 않고 **내용상 묶어야 하는 요구사항을 한 소절**로 다룬다(예: 민원 접수·배정·종결을
한 워크플로로). 묶음은 ① 제안 문안 에이전트가 ``requirement_groups`` 로 지정한 것을 우선 쓰고, ② 없으면 코드가
RFP 고유번호(같은 RFP 항목의 세부 요구) → 분류(category) 순으로 묶는다. 각 묶음은 정의서의 구현방안 **전문**을
표로 싣는다(잘라 쓰지 않음). 덱에 실린 내용이 정의서와 같은지는 QA-CON-12 가 대조한다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from proposal_agent.generators.base import GenerationContext
from proposal_agent.models import Requirement, RequirementType
from proposal_agent.requirements.design import (
    LAYER_ORDER,
    layer_label,
    resolve_design_ids,
)

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
    source: str = "code"  # design | agent | code
    rfp_ids: list[str] = field(default_factory=list)
    design: dict[str, Any] | None = None  # 구현 설계 (Phase 23, design_writer 출력 한 묶음)

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


def _design_groups(ctx: GenerationContext, pool: list[Requirement]) -> list[RequirementGroup]:
    """구현 설계(design_writer)가 정한 묶음을 최우선으로. 남는 요구는 문안 묶음 → 코드 묶음."""
    used: set[str] = set()
    by_id = {r.id: r for r in pool}
    groups: list[RequirementGroup] = []
    for d in ctx.designs:
        if not isinstance(d, dict):
            continue
        ids = [x for x in resolve_design_ids(d, pool) if x not in used]
        reqs = [by_id[x] for x in ids if x in by_id]
        if not reqs:
            continue
        used.update(r.id for r in reqs)
        groups.append(
            RequirementGroup(
                title=str(d.get("title", "") or "요구사항 묶음")[:60],
                requirements=reqs,
                key_message=str(d.get("key_message", "") or ""),
                summary=[str(x) for x in d.get("overview", []) or []][:4],
                notes=[str(x) for x in d.get("premises", []) or []][:3],
                source="design",
                rfp_ids=sorted({r.rfp_requirement_id for r in reqs if r.rfp_requirement_id}),
                design=d,
            )
        )
    rest = [r for r in pool if r.id not in used]
    if not rest:
        return groups
    tail = (
        _agent_groups(ctx, rest)
        if (ctx.proposal_content or {}).get("requirement_groups")
        else _code_groups(rest)
    )
    return groups + tail


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
        if len(g.requirements) <= MAX_GROUP_SIZE or g.design is not None:
            out.append(g)  # 설계 묶음은 나누지 않는다 (구현방안 표는 행 단위로 장을 나눈다)
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


def group_requirements(
    ctx: GenerationContext, *, use_designs: bool = True
) -> list[RequirementGroup]:
    """제안서에 실을 요구사항 묶음: ① 구현 설계(design_writer) ② 문안 에이전트 지정 ③ 코드(RFP 번호·분류).
    구현방안이 없는 요구는 제외(설계 묶음은 예외 — 설계 자체가 구현 내용이다)."""
    pool = _eligible(ctx)
    if use_designs and ctx.designs:
        designed = {x for d in ctx.designs for x in resolve_design_ids(d, ctx.requirements)}
        extra = [
            r
            for r in ctx.requirements
            if r.id in designed
            and r not in pool
            and r.type in (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL)
            and r.change_state != "deleted"
            and r.acceptance_status.value != "rejected"
        ]
        pool = pool + extra
    if not pool:
        return []
    if use_designs and ctx.designs:
        groups = _design_groups(ctx, pool)
    elif (ctx.proposal_content or {}).get("requirement_groups"):
        groups = _agent_groups(ctx, pool)
    else:
        groups = _code_groups(pool)
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
    seen: set[str] = set()
    for r in group.requirements:
        for line in approach_lines(r):
            if (line.startswith("전제") or "협의" in line) and line not in seen:
                seen.add(line)  # 같은 전제가 여러 요구에 반복되면 한 번만
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


# --- Phase 23: 구현 설계 → 도식·표 ---------------------------------------------------------------


def design_structure_spec(design: dict[str, Any]) -> dict[str, Any]:
    """구현 구조(structure[]) → 계층 띠 도식(layers) spec. 계층 순서: 사용자 → 웹 → 응용 → 배치 → 연계 → 데이터 → 인프라 → 외부."""
    comps = [c for c in design.get("structure", []) or [] if isinstance(c, dict)]
    comps.sort(
        key=lambda c: next(
            (i for i, k in enumerate(LAYER_ORDER) if k == str(c.get("layer", "")).casefold()),
            len(LAYER_ORDER),
        )
    )
    items = []
    for c in comps[:16]:
        text = str(c.get("technology", "") or "")
        role = str(c.get("role", "") or "")
        if role:
            text = f"{text} — {role}" if text else role
        items.append(
            {
                "title": str(c.get("name", ""))[:30],
                "group": layer_label(str(c.get("layer", ""))),
                "text": text[:70],
            }
        )
    return {"kind": "layers", "title": "구현 구조", "items": items}


def design_flow_spec(design: dict[str, Any]) -> dict[str, Any]:
    """처리 절차(flows[]) → 담당별 레인 절차 도식(procedure) spec. 상자에는 단계 제목만(분기 있으면 ◆ 표시),
    처리 내용·분기는 ``flow_table_rows`` 의 '처리 절차 상세' 표에 싣는다 (상자 글자 잘림 방지)."""
    items = []
    for st in (design.get("flows", []) or [])[:10]:
        if not isinstance(st, dict):
            continue
        items.append(
            {
                "title": str(st.get("title", ""))[:24],
                "group": str(st.get("actor", "") or "")[:16],
                "text": "◆ 분기" if st.get("decision") else "",
            }
        )
    return {"kind": "procedure", "title": "처리 절차", "items": items}


FLOW_HEADERS = ["단계", "담당", "처리 내용", "분기·예외"]
FLOW_WIDTHS = [0.5, 1.7, 4.6, 3.2]


def flow_table_rows(design: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for i, st in enumerate((design.get("flows", []) or [])[:10], start=1):
        if not isinstance(st, dict):
            continue
        rows.append(
            [
                str(i),
                str(st.get("actor", "") or "-"),
                f"{st.get('title', '')}: {st.get('action', '')}".strip(": "),
                str(st.get("decision", "") or "-"),
            ]
        )
    return rows


TECH_HEADERS = ["구분", "적용 기술·방식", "선정 이유 · 검토한 대안", "근거"]
TECH_WIDTHS = [1.3, 2.6, 4.8, 1.3]


def tech_choice_rows(design: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for t in design.get("tech_choices", []) or []:
        if not isinstance(t, dict):
            continue
        reason = str(t.get("reason", "") or "")
        alts = [str(x) for x in t.get("alternatives", []) or [] if str(x).strip()]
        if alts:
            reason += "\n" + "\n".join(f"대안: {a}" for a in alts[:3])
        src = str(t.get("source", "") or "설계 제안").strip()
        mark = " (확인)" if t.get("verified") else " (미확인)"
        if src.startswith(
            ("http://", "https://")
        ):  # URL 은 도메인만 (전체 URL 은 설계 JSON·조사 기록에)
            m = re.match(r"https?://([^/]+)", src)
            src = (m.group(1) if m else src[:40]) + mark
        elif src in ("설계 제안", "자체 설계"):
            src = "자체 설계"
        elif src.upper() == "RFP":
            src = "RFP 명시"
        elif src.startswith("TR-"):
            src = f"조사 {src}"
        else:
            src = src[:30] + mark
        rows.append([str(t.get("area", "")), str(t.get("choice", "")), reason, src])
    return rows


def design_data_lines(design: dict[str, Any]) -> list[str]:
    return [str(x) for x in design.get("data_interfaces", []) or [] if str(x).strip()][:8]


def design_risk_lines(design: dict[str, Any]) -> list[str]:
    return [str(x) for x in design.get("risks", []) or [] if str(x).strip()][:4]


def design_texts(design: dict[str, Any]) -> list[str]:
    """QA 대조용: 덱에 실려야 하는 설계 문구(구성 요소 이름·절차 제목·적용 기술)."""
    out = [str(c.get("name", "")) for c in design.get("structure", []) or [] if isinstance(c, dict)]
    out += [str(s.get("title", "")) for s in design.get("flows", []) or [] if isinstance(s, dict)]
    out += [
        str(t.get("choice", ""))
        for t in design.get("tech_choices", []) or []
        if isinstance(t, dict)
    ]
    return [x for x in out if len(x.strip()) >= 2]


__all__ = [
    "FLOW_HEADERS",
    "FLOW_WIDTHS",
    "MAX_GROUP_SIZE",
    "TECH_HEADERS",
    "TECH_WIDTHS",
    "flow_table_rows",
    "design_data_lines",
    "design_flow_spec",
    "design_risk_lines",
    "design_structure_spec",
    "design_texts",
    "tech_choice_rows",
    "RequirementGroup",
    "approach_lines",
    "approach_table_rows",
    "default_key_message",
    "function_block_spec",
    "group_requirements",
    "premises",
]
