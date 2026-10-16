"""요구사항 묶음별 구현 설계 (Phase 23).

- 에이전트(``design_writer``)가 요구사항 **묶음**마다 "실제로 어떻게 구현하는가"를 설계한다: 구현 구조(구성 요소·계층·기술),
  처리 절차(담당·처리·분기), 적용 기술과 선정 이유·대안·근거, 데이터·인터페이스, 전제·위험.
- 근거는 기술 조사·아키텍처·구현 가능성 비교이며, 새로 확인한 출처는 URL 로 남긴다(열람하지 않은 URL 금지).
- 결과는 에이전트 출력 JSON(``design_writer``)으로 저장되고, 덱 생성기는 묶음 소절에 **구현 구조 도식·처리 절차 도식·
  적용 기술 표**로 싣는다(``generators/pptx/req_groups.py``). 내용 깊이와 반영 여부는 QA-CON-13 이 검사한다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.schemas import DesignReport
from proposal_agent.config.logging import get_logger
from proposal_agent.models import (
    AcceptanceStatus,
    Project,
    Requirement,
    RequirementStatus,
    RequirementType,
)
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.agent_step_service import AgentStepService

log = get_logger("requirements.design")

ROLE_DESIGN = "design_writer"
DESIGN_TYPES = (RequirementType.FUNCTIONAL, RequirementType.NON_FUNCTIONAL)
LAYER_LABELS: dict[str, str] = {
    "client": "사용자·화면",
    "web": "웹 서버",
    "app": "응용(WAS)",
    "batch": "배치·스케줄",
    "integration": "연계",
    "data": "데이터",
    "infra": "인프라",
    "external": "외부 시스템",
    "security": "보안",
}
LAYER_ORDER = tuple(LAYER_LABELS)


def design_targets(requirements: list[Requirement]) -> list[Requirement]:
    """설계 대상: 수용된(거부 아님) 기능·비기능 요구사항."""
    out: list[Requirement] = []
    for r in requirements:
        if r.status == RequirementStatus.DELETED or r.change_state == "deleted":
            continue
        if r.type not in DESIGN_TYPES or r.acceptance_status == AcceptanceStatus.REJECTED:
            continue
        out.append(r)
    return out


def layer_label(layer: str) -> str:
    key = (layer or "").strip().casefold()
    return LAYER_LABELS.get(key, layer or "구성")


def design_min_issues(design: dict[str, Any]) -> list[str]:
    """설계 최소 요건(구조 2·절차 3·기술 선택 1·데이터/인터페이스 1) 미달 항목."""
    issues: list[str] = []
    if len(design.get("structure") or []) < 2:
        issues.append("구현 구조 2개 미만")
    if len(design.get("flows") or []) < 3:
        issues.append("처리 절차 3단계 미만")
    if not design.get("tech_choices"):
        issues.append("적용 기술·선정 이유 없음")
    if not design.get("data_interfaces"):
        issues.append("데이터·인터페이스 없음")
    return issues


SELF_DESIGNED_SOURCES = ("설계 제안", "자체 설계", "RFP")


def needs_verification(choice: dict[str, Any]) -> bool:
    """출처 확인이 필요한 기술 선택: verified 가 아니고 출처가 자체 설계·RFP 명시가 아닌 것(제품·표준 주장)."""
    src = str(choice.get("source", "") or "").strip()
    return not bool(choice.get("verified")) and src not in SELF_DESIGNED_SOURCES


def resolve_design_ids(design: dict[str, Any], requirements: list[Requirement]) -> list[str]:
    """설계의 requirement_ids(내부 ID 또는 RFP 고유번호)를 내부 ID 목록으로."""
    by_id = {r.id for r in requirements}
    by_rfp: dict[str, list[str]] = {}
    for r in requirements:
        if r.rfp_requirement_id:
            by_rfp.setdefault(r.rfp_requirement_id, []).append(r.id)
    out: list[str] = []
    for rid in design.get("requirement_ids") or []:
        rid = str(rid)
        if rid in by_id and rid not in out:
            out.append(rid)
        elif rid in by_rfp:
            out.extend(x for x in by_rfp[rid] if x not in out)
    return out


class DesignService:
    def __init__(self, repos: Repositories, steps: AgentStepService) -> None:
        self._repos = repos
        self._steps = steps

    # --- 입력 -------------------------------------------------------------------------------
    def brief(self, project: Project) -> str:
        """design_writer 프롬프트: 코드 제안 묶음(요구·정의서 구현방안) + 조사·아키텍처·기술 선택."""
        from proposal_agent.generators.base import GenerationContext
        from proposal_agent.generators.pptx.req_groups import group_requirements

        reqs = self._repos.requirements.find(project.id, order_by="id")
        targets = design_targets(reqs)
        ctx = GenerationContext(project=project, requirements=targets)
        groups: list[dict[str, Any]] = []
        for g in group_requirements(ctx, use_designs=False):
            groups.append(
                {
                    "title": g.title,
                    "rfp_ids": g.rfp_ids,
                    "requirements": [
                        {
                            "id": r.id,
                            "rfp_id": r.rfp_requirement_id or "",
                            "type": r.type.value,
                            "category": r.category.value,
                            "name": r.name,
                            "description": (r.description or "")[:240],
                            "approach": r.implementation_approach or "",
                            "difficulty": r.difficulty.value if r.difficulty else "",
                        }
                        for r in g.requirements
                    ],
                }
            )
        ungrouped = [
            {"id": r.id, "rfp_id": r.rfp_requirement_id or "", "name": r.name}
            for r in targets
            if r.id not in {x["id"] for g in groups for x in g["requirements"]}
        ]
        research = [
            {
                "id": t.id,
                "topic": t.topic,
                "related": t.related_requirement_ids,
                "feasibility": t.feasibility.value,
                "facts": t.confirmed_facts[:6],
                "stack": t.recommended_stack[:6],
                "unverified": t.unverified_items[:4],
                "sources": [s.url for s in t.sources[:4]],
            }
            for t in self._repos.research.find(project.id, order_by="created_at")[:40]
        ]
        components = [
            {
                "code": c.id,
                "layer": c.layer,
                "name": c.name,
                "technology": c.technology or "미정",
                "description": (c.description or "")[:120],
            }
            for c in self._repos.components.find(project.id, order_by="id")[:60]
        ]
        prior = self._steps.prior_output(project, "tech_researcher") or {}
        comparisons = prior.get("comparisons") or []
        from proposal_agent.design.context import client_context_block
        from proposal_agent.models import ProjectSettings

        parts = [
            client_context_block(  # 단계 6 ⑤ (D-21): 발주처 업무·기존 시스템 문맥
                project,
                self._steps.prior_output(project, "rfp_analyst"),
                ProjectSettings.from_project_settings(project.settings),
            ),
            "<groups>\n"
            + json.dumps({"groups": groups, "ungrouped": ungrouped}, ensure_ascii=False)[:30000]
            + "\n</groups>",
            "<research>\n" + json.dumps(research, ensure_ascii=False)[:16000] + "\n</research>",
            "<architecture>\n"
            + json.dumps(components, ensure_ascii=False)[:8000]
            + "\n</architecture>",
            "<comparisons>\n"
            + json.dumps(comparisons, ensure_ascii=False)[:8000]
            + "\n</comparisons>",
            "위 묶음을 기준으로(필요하면 합치거나 나눠) 묶음마다 구현 설계(overview·structure·flows·tech_choices·"
            "data_interfaces·premises·risks)를 JSON으로 반환하라. 모든 요구사항 id가 정확히 한 묶음에 들어가야 하며, "
            "제품·버전·표준은 조사·아키텍처·기술 선택에 있는 것만 단정하고 새로 확인한 것은 열람한 URL을 sources에 적는다.",
        ]
        return "\n\n".join(parts)

    # --- 결과 -------------------------------------------------------------------------------
    def latest(self, project: Project) -> dict[str, Any] | None:
        return self._steps.prior_output(project, ROLE_DESIGN)

    def designs(self, project: Project) -> list[dict[str, Any]]:
        """저장된 설계 목록(검증 통과한 것만). 없으면 빈 목록."""
        data = self.latest(project)
        if not data:
            return []
        try:
            report = DesignReport.model_validate(data)
        except Exception as exc:  # noqa: BLE001 — 깨진 출력은 설계 없음으로 처리하고 기록
            log.warning("design_writer 출력 검증 실패: %s", exc)
            return []
        return [d.model_dump(mode="json") for d in report.designs]

    def coverage(self, project: Project) -> tuple[list[str], list[str]]:
        """(설계에 포함된 요구사항 ID, 설계 대상인데 빠진 ID)."""
        reqs = self._repos.requirements.find(project.id, order_by="id")
        targets = design_targets(reqs)
        covered: list[str] = []
        for d in self.designs(project):
            covered.extend(x for x in resolve_design_ids(d, targets) if x not in covered)
        missing = [r.id for r in targets if r.id not in covered]
        return covered, missing

    def summary(self, project: Project) -> str:
        designs = self.designs(project)
        covered, missing = self.coverage(project)
        weak = [d["title"] for d in designs if design_min_issues(d)]
        unverified = sum(
            1
            for d in designs
            for t in d.get("tech_choices") or []
            if isinstance(t, dict) and needs_verification(t)
        )
        text = (
            f"구현 설계 {len(designs)}묶음 — 요구사항 {len(covered)}건 포함"
            + (f", 빠진 요구 {len(missing)}건 ({', '.join(missing[:5])})" if missing else "")
            + (f", 최소 요건 미달 {len(weak)}묶음" if weak else "")
            + (f", 출처 미확인 기술 선택 {unverified}건" if unverified else "")
        )
        return text


__all__ = [
    "LAYER_LABELS",
    "LAYER_ORDER",
    "ROLE_DESIGN",
    "DesignService",
    "design_min_issues",
    "design_targets",
    "layer_label",
    "needs_verification",
    "resolve_design_ids",
]
