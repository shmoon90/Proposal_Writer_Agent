"""요구사항별 구현 방안 자동 작성 (Phase 14).

- 에이전트(``approach_writer``)가 요구사항 묶음마다 '구현방안·난이도·검증 방법·검사 기준'을 짧게 쓴다.
  근거는 기술 조사(``TechnologyResearch``)·아키텍처 구성 요소·구현 가능성 비교이며, 새로 열람한 출처는
  조사 기록으로 남겨 "조사 선행" 원칙(QA-TECH-07)과 이어진다.
- 에이전트를 쓸 수 없거나 빠뜨린 항목은 코드가 **프로젝트 데이터(조사·구성 요소·기술 선택)만으로** 초안을 만들고
  ``approach_source="rule"``로 표시한다(사람 확인 대상). 사람이 쓴 방안(``user``)은 덮어쓰지 않는다.
- 난이도는 변경관리에서 공수·일정 영향의 가중치로 쓰이므로 비어 있으면 규칙으로 추정해 채운다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.control import CancellationToken
from proposal_agent.agents.schemas import ApproachReport
from proposal_agent.config.logging import get_logger
from proposal_agent.models import (
    AcceptanceStatus,
    ActorKind,
    ArchitectureComponent,
    Difficulty,
    FeasibilityVerdict,
    Project,
    Requirement,
    RequirementCategory,
    RequirementStatus,
    RequirementType,
    TechnologyResearch,
)
from proposal_agent.models.research import FeasibilityStudy, ResearchSource
from proposal_agent.requirements.difficulty import (
    NUM_COND_RE,
    approach_lines,
    estimate_difficulty,
)
from proposal_agent.research.sources import classify_url, effective_trust
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService

log = get_logger("requirements.approach")

ROLE_APPROACH = "approach_writer"
BATCH_SIZE = 20
SOURCE_USER = "user"
SOURCE_AGENT = "agent"
SOURCE_RULE = "rule"
SOURCE_RESEARCH = "research"
SOURCE_BASELINE = "baseline"
RULE_MARK = "[자동 초안]"
VERIFICATION_OPTIONS = ("시연", "시험", "검사", "분석")
# 구현 대상이 아닌 종류(평가 기준·제출 조건)는 구현 방안을 쓰지 않는다.
NO_APPROACH_TYPES = (RequirementType.EVALUATION, RequirementType.SUBMISSION)

# 분류별 기본 구현 골격 (프로젝트 데이터가 없을 때의 마지막 보조선. 제품명은 쓰지 않는다)
CATEGORY_SKELETON: dict[RequirementCategory, tuple[str, ...]] = {
    RequirementCategory.UI: (
        "화면: 목록·상세·등록/수정 화면으로 구성, 입력 검증은 화면과 서버 양쪽에서 수행",
        "권한별 메뉴·버튼 제어와 공통 UI 컴포넌트 재사용",
    ),
    RequirementCategory.BUSINESS: (
        "서비스 계층에 업무 규칙을 구현하고 처리 결과·이력을 DB에 기록",
        "예외·반려 흐름과 알림을 같은 트랜잭션 범위에서 설계",
    ),
    RequirementCategory.DATA: (
        "테이블·코드 설계 후 이관/정제 절차 정의, 건수 대사 리포트로 검증",
        "전제: 원천 데이터 구조와 품질은 고객 제공 자료로 확정",
    ),
    RequirementCategory.INTERFACE: (
        "연계 방식(REST/파일/DB 링크)·주기·오류 재처리를 정의하고 연계 로그를 기록",
        "전제: 대상 시스템 인터페이스 규격은 고객 제공 후 확정",
    ),
    RequirementCategory.REPORT: (
        "집계 쿼리 또는 배치로 통계를 생성하고 화면 조회·엑셀 내보내기 제공",
        "집계 기준·주기는 현업 협의로 확정",
    ),
    RequirementCategory.ADMIN: (
        "코드·메뉴·권한·사용자 관리는 공통 관리 모듈로 구현, 변경 이력 기록",
    ),
    RequirementCategory.PERFORMANCE: (
        "목표 수치 기준 부하 시험 계획 수립, 캐시·인덱스·커넥션 풀 튜닝",
        "측정 도구·시나리오는 시험 계획서에서 확정",
    ),
    RequirementCategory.SECURITY: (
        "인증·인가(역할 기반), 전송·저장 구간 암호화, 시큐어코딩 점검과 웹 취약점 진단",
        "전제: 고객 보안 규정·인증 방식은 보안 담당과 협의",
    ),
    RequirementCategory.AVAILABILITY: ("이중화·백업/복구 절차와 장애 감시·알림 체계 적용",),
    RequirementCategory.COMPATIBILITY: ("지원 브라우저·OS 목록 확정 후 호환성 시험 수행",),
    RequirementCategory.OPERABILITY: ("운영 절차·모니터링·로그 관리 정의, 형상관리 등록",),
    RequirementCategory.CONSTRAINT: (
        "해당 제약을 설계 기준으로 반영하고 준수 여부를 검수 항목에 포함",
    ),
    RequirementCategory.OTHER: ("요구 내용에 맞는 구현 방식을 설계 단계에서 확정",),
}
# 분류 → 구현 가능성 비교 영역 / 구성 요소 계층 힌트
CATEGORY_AREAS: dict[RequirementCategory, tuple[str, ...]] = {
    RequirementCategory.UI: ("ui_ux", "framework"),
    RequirementCategory.BUSINESS: ("framework",),
    RequirementCategory.ADMIN: ("framework",),
    RequirementCategory.REPORT: ("framework", "db"),
    RequirementCategory.DATA: ("db",),
    RequirementCategory.INTERFACE: ("api",),
    RequirementCategory.PERFORMANCE: ("web_was", "db"),
    RequirementCategory.SECURITY: ("security",),
    RequirementCategory.AVAILABILITY: ("deploy_ops", "web_was"),
    RequirementCategory.OPERABILITY: ("deploy_ops",),
    RequirementCategory.COMPATIBILITY: ("ui_ux",),
}
CATEGORY_LAYER_HINTS: dict[RequirementCategory, tuple[str, ...]] = {
    RequirementCategory.UI: ("presentation", "ui", "web", "화면", "프론트"),
    RequirementCategory.BUSINESS: ("application", "service", "business", "업무", "서비스"),
    RequirementCategory.ADMIN: ("application", "admin", "관리"),
    RequirementCategory.REPORT: ("application", "report", "통계", "data"),
    RequirementCategory.DATA: ("data", "db", "데이터", "storage"),
    RequirementCategory.INTERFACE: ("integration", "interface", "연계", "api", "gateway"),
    RequirementCategory.PERFORMANCE: ("infra", "was", "cache", "인프라"),
    RequirementCategory.SECURITY: ("security", "보안", "auth"),
    RequirementCategory.AVAILABILITY: ("infra", "인프라", "ha"),
    RequirementCategory.OPERABILITY: ("infra", "ops", "운영", "monitor"),
}
_KEYWORD_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9.+#-]{2,}")


@dataclass
class ApproachRunResult:
    agent_filled: list[str] = field(default_factory=list)
    rule_filled: list[str] = field(default_factory=list)
    skipped_user: list[str] = field(default_factory=list)
    invalid_ids: list[str] = field(default_factory=list)
    research_needed: list[str] = field(default_factory=list)
    research_created: list[str] = field(default_factory=list)
    batches: int = 0
    cost_usd: float = 0.0

    @property
    def summary(self) -> str:
        return (
            f"구현 방안 작성 {len(self.agent_filled)}건(에이전트) + {len(self.rule_filled)}건(규칙 초안), "
            f"사람 작성 유지 {len(self.skipped_user)}건, 추가 조사 필요 {len(self.research_needed)}건, "
            f"묶음 {self.batches}회, 비용 ${self.cost_usd:.3f}"
        )


def research_links(req: Requirement, rec: TechnologyResearch) -> bool:
    ids = set(rec.related_requirement_ids)
    return req.id in ids or (bool(req.rfp_requirement_id) and req.rfp_requirement_id in ids)


def normalize_approach(text: str) -> str:
    lines = approach_lines(text)
    return "\n".join(lines[:6])


def _keywords(text: str) -> set[str]:
    return {w.casefold() for w in _KEYWORD_RE.findall(text or "")}


def default_acceptance_criteria(req: Requirement, verification: str) -> str:
    """검사 기준 기본값: 요구 내용 동작 확인 + 수치 조건."""
    lines = [f"- {req.name[:40]} 요구 내용대로 동작함을 {verification or '시험'}으로 확인"]
    nums = list(dict.fromkeys(n.strip() for n in NUM_COND_RE.findall(req.description or "")))
    if nums:
        lines.append("- 수치 조건 충족: " + ", ".join(nums[:4]))
    return "\n".join(lines)


def default_verification(req: Requirement) -> str:
    if req.verification_method in VERIFICATION_OPTIONS:
        return str(req.verification_method)
    if req.type == RequirementType.NON_FUNCTIONAL and req.category in (
        RequirementCategory.PERFORMANCE,
        RequirementCategory.AVAILABILITY,
    ):
        return "시험"
    if req.type in (RequirementType.CONSTRAINT,) or req.category == RequirementCategory.SECURITY:
        return "검사"
    return "시연"


def draft_rule_based(
    req: Requirement,
    research: list[TechnologyResearch],
    components: list[ArchitectureComponent],
    study: FeasibilityStudy | None,
) -> tuple[str, list[str], str, FeasibilityVerdict | None]:
    """(구현 방안 초안, 근거 목록, 출처 구분, 조사 구현 가능성). 프로젝트 데이터 → 분류 골격 순."""
    lines: list[str] = []
    basis: list[str] = []
    linked = [t for t in research if research_links(req, t)]
    feas: FeasibilityVerdict | None = None
    for t in linked[:2]:
        feas = feas or t.feasibility
        if t.feasibility in (FeasibilityVerdict.FEASIBLE, FeasibilityVerdict.FEASIBLE_WITH_RISK):
            text = (t.impact_on_implementation or t.summary or "").strip()
            if text:
                lines.append(f"{text[:140]} (조사 '{t.topic[:30]}', {t.feasibility.value})")
            if t.recommended_stack:
                lines.append("적용 기술: " + ", ".join(t.recommended_stack[:3]))
        else:
            lines.append(
                f"조사 '{t.topic[:30]}' 결과 {t.feasibility.value} — 대안 검토 후 방식 확정"
            )
        basis.append(t.id)
    kws = _keywords(f"{req.name} {req.description}")
    hints = CATEGORY_LAYER_HINTS.get(req.category, ())
    matched: list[ArchitectureComponent] = []
    for c in components:
        text = f"{c.layer} {c.name} {c.technology} {c.description}".casefold()
        layer_hit = any(h in c.layer.casefold() for h in hints)
        kw_hit = len(kws & _keywords(text)) >= 2
        if layer_hit or kw_hit:
            matched.append(c)
    for c in matched[:2]:
        tech = f"({c.technology})" if c.technology else ""
        lines.append(f"구성 요소: {c.layer} / {c.name}{tech}")
        basis.append(f"component:{c.id}")
    if study:
        for comp in study.comparisons:
            if comp.area in CATEGORY_AREAS.get(req.category, ()) and comp.recommendation:
                spec = f"RFP 명시 {comp.rfp_specified} · " if comp.rfp_specified else ""
                lines.append(f"기술 선택({comp.area}): {spec}{comp.recommendation[:60]}")
                basis.append(f"feasibility:{comp.area}")
                break
    for s in CATEGORY_SKELETON.get(req.category, CATEGORY_SKELETON[RequirementCategory.OTHER]):
        if len(lines) >= 4:
            break
        lines.append(s)
    source = SOURCE_RESEARCH if linked else SOURCE_RULE
    mark = (
        f"{RULE_MARK} 조사·설계 데이터로 코드가 작성 — 설계 단계에서 확인"
        if linked or matched
        else f"{RULE_MARK} 근거 조사 없음 — 기술 조사 후 확정 필요"
    )
    lines.append(mark)
    return "\n".join(f"- {ln}" for ln in lines[:5]), basis, source, feas


class ApproachService:
    def __init__(self, repos: Repositories, audit: AuditService, steps: AgentStepService) -> None:
        self._repos = repos
        self._audit = audit
        self._steps = steps

    # --- 대상 선정 ----------------------------------------------------------------------------
    def targets(
        self,
        project: Project,
        *,
        only_missing: bool = True,
        requirement_ids: list[str] | None = None,
    ) -> list[Requirement]:
        wanted = set(requirement_ids or [])
        out: list[Requirement] = []
        for r in self._repos.requirements.find(project.id, order_by="id"):
            if r.status == RequirementStatus.DELETED or r.change_state == "deleted":
                continue
            if r.type in NO_APPROACH_TYPES:
                continue
            if r.acceptance_status == AcceptanceStatus.REJECTED and not wanted:
                continue
            if wanted and r.id not in wanted:
                continue
            if (
                only_missing
                and not wanted
                and r.implementation_approach
                and r.approach_source not in ("", SOURCE_RULE, SOURCE_RESEARCH)
            ):
                continue  # 에이전트·사람·기준 문서가 쓴 방안은 유지, 초안(규칙·조사 한 줄)은 다시 쓴다
            out.append(r)
        return out

    def missing(self, project: Project) -> list[Requirement]:
        """구현 방안이 비었거나 초안(규칙·조사 한 줄)인 요구사항."""
        return self.targets(project, only_missing=True)

    # --- 에이전트 실행 -------------------------------------------------------------------------
    def run(
        self,
        project: Project,
        *,
        actor: str = "user",
        step_run_id: str | None = None,
        cancel: CancellationToken | None = None,
        only_missing: bool = True,
        requirement_ids: list[str] | None = None,
    ) -> ApproachRunResult:
        result = ApproachRunResult()
        targets = self.targets(project, only_missing=only_missing, requirement_ids=requirement_ids)
        keep = [r for r in targets if r.approach_source == SOURCE_USER and not requirement_ids]
        result.skipped_user = [r.id for r in keep]
        targets = [r for r in targets if r.id not in result.skipped_user]
        if not targets:
            return result
        research = self._repos.research.find(project.id, order_by="created_at")
        components = self._repos.components.find(project.id, order_by="created_at")
        study = self._latest_study(project)
        done: set[str] = set()
        for i in range(0, len(targets), BATCH_SIZE):
            batch = targets[i : i + BATCH_SIZE]
            prompt = self._prompt(batch, research, components, study)
            run = self._steps.run_role(
                project,
                ROLE_APPROACH,
                prompt,
                actor=actor,
                step_run_id=step_run_id,
                cancel=cancel,
                include_prior=(i == 0),
            )
            result.batches += 1
            result.cost_usd += run.response.cost_usd
            report: ApproachReport = run.output  # type: ignore[assignment]
            by_id = {r.id: r for r in batch}
            research_ids = {t.id for t in research}
            for item in report.items:
                req = by_id.get(item.requirement_id)
                if req is None or req.id in done:
                    result.invalid_ids.append(item.requirement_id)
                    continue
                created = self._apply_item(
                    project, req, item, research_ids, actor, run.output_record.id
                )
                if created:
                    research.append(created)
                    research_ids.add(created.id)
                    result.research_created.append(created.id)
                done.add(req.id)
                result.agent_filled.append(req.id)
            result.research_needed.extend(report.research_needed)
        # 에이전트가 빠뜨린 항목은 규칙 초안
        rest = [r for r in targets if r.id not in done]
        if rest:
            result.rule_filled = self._fill_rule(
                project, rest, research, components, study, actor, force=False
            )
        self._audit.record(
            project.id,
            "requirements.approach_written",
            actor=actor,
            actor_kind=ActorKind.AGENT,
            payload={
                "agent": result.agent_filled,
                "rule": result.rule_filled,
                "skipped_user": result.skipped_user,
                "research_needed": result.research_needed[:50],
                "invalid": result.invalid_ids,
                "cost_usd": result.cost_usd,
            },
        )
        return result

    def ensure_filled(self, project: Project, *, actor: str = "system") -> list[str]:
        """산출물 생성 전: 구현 방안·난이도·검사 기준이 빈 요구사항을 규칙 초안으로 채운다 (에이전트 호출 없음)."""
        research = self._repos.research.find(project.id, order_by="created_at")
        components = self._repos.components.find(project.id, order_by="created_at")
        study = self._latest_study(project)
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status != RequirementStatus.DELETED
            and r.change_state != "deleted"
            and r.type not in NO_APPROACH_TYPES
            and r.acceptance_status != AcceptanceStatus.REJECTED
        ]
        filled = self._fill_rule(project, reqs, research, components, study, actor, force=False)
        if filled:
            self._audit.record(
                project.id,
                "requirements.approach_drafted",
                actor=actor,
                payload={"requirement_ids": filled[:100], "count": len(filled)},
            )
        return filled

    # --- 내부 -----------------------------------------------------------------------------------
    def _latest_study(self, project: Project) -> FeasibilityStudy | None:
        rows = self._repos.feasibility.find(
            project.id, order_by="created_at", descending=True, limit=1
        )
        return rows[0] if rows else None

    def _fill_rule(
        self,
        project: Project,
        reqs: list[Requirement],
        research: list[TechnologyResearch],
        components: list[ArchitectureComponent],
        study: FeasibilityStudy | None,
        actor: str,
        *,
        force: bool,
    ) -> list[str]:
        filled: list[str] = []
        for req in reqs:
            changed: dict[str, Any] = {}
            linked = [t for t in research if research_links(req, t)]
            feas = linked[0].feasibility if linked else None
            if force or not req.implementation_approach:
                text, basis, source, feas2 = draft_rule_based(req, research, components, study)
                feas = feas or feas2
                req.implementation_approach = text
                req.approach_source = source
                req.approach_basis = basis
                changed["implementation_approach"] = source
            if req.difficulty is None:
                level, why = estimate_difficulty(
                    f"{req.name}\n{req.description}", category=req.category, feasibility=feas
                )
                req.difficulty, req.difficulty_basis = level, why
                changed["difficulty"] = level.value
            if not req.verification_method:
                req.verification_method = default_verification(req)
                changed["verification_method"] = req.verification_method
            if not req.acceptance_criteria:
                req.acceptance_criteria = default_acceptance_criteria(
                    req, req.verification_method or ""
                )
                changed["acceptance_criteria"] = "default"
            if changed:
                req.add_history(actor, "approach.rule", changes=changed, note=RULE_MARK)
                req.touch()
                self._repos.requirements.update(req)
                if "implementation_approach" in changed:
                    filled.append(req.id)
        return filled

    def _apply_item(
        self,
        project: Project,
        req: Requirement,
        item: Any,
        research_ids: set[str],
        actor: str,
        output_id: str,
    ) -> TechnologyResearch | None:
        before = req.implementation_approach
        req.implementation_approach = normalize_approach(item.approach)
        req.approach_source = SOURCE_AGENT
        refs = [x for x in item.research_refs if x in research_ids]
        created: TechnologyResearch | None = None
        if item.sources:
            created = TechnologyResearch(
                project_id=project.id,
                topic=f"구현 방안 근거: {req.name[:40]}",
                related_requirement_ids=[req.id],
                summary=req.implementation_approach[:300],
                confirmed_facts=[
                    f"{s.title or s.product}: {s.excerpt}".strip(": ")
                    for s in item.sources
                    if s.excerpt
                ],
                unverified_items=[item.notes] if item.notes else [],
                impact_on_implementation=req.implementation_approach[:300],
                feasibility=item.feasibility,
                sources=[self._to_source(s) for s in item.sources],
                agent_output_id=output_id,
                created_by=actor,
            )
            self._repos.research.insert(created)
            refs.append(created.id)
        req.approach_basis = refs + [s.url for s in item.sources]
        level = Difficulty.from_label(item.difficulty)
        if level is None:
            level, why = estimate_difficulty(
                f"{req.name}\n{req.description}",
                category=req.category,
                feasibility=item.feasibility,
            )
            req.difficulty, req.difficulty_basis = level, "에이전트 미기재 → " + why
        else:
            req.difficulty = level
            req.difficulty_basis = item.difficulty_basis or "에이전트 판단"
        if item.verification_method in VERIFICATION_OPTIONS:
            req.verification_method = item.verification_method
        elif not req.verification_method:
            req.verification_method = default_verification(req)
        req.acceptance_criteria = normalize_approach(item.acceptance_criteria) or (
            req.acceptance_criteria
            or default_acceptance_criteria(req, req.verification_method or "")
        )
        if item.response_strategy:
            req.response_strategy = item.response_strategy[:120]
        if item.notes:
            req.review_notes = (
                req.review_notes + "\n" if req.review_notes else ""
            ) + f"@구현 방안 메모: {item.notes}"
        req.add_history(
            actor,
            "approach.agent",
            changes={
                "implementation_approach": (before or "", req.implementation_approach),
                "difficulty": req.difficulty.value if req.difficulty else None,
                "research_refs": refs,
            },
            note=f"approach_writer ({item.feasibility.value})",
        )
        req.touch()
        self._repos.requirements.update(req)
        return created

    @staticmethod
    def _to_source(draft: Any) -> ResearchSource:
        rule = classify_url(draft.url)
        return ResearchSource(
            url=draft.url,
            title=draft.title,
            product=draft.product,
            version=draft.version,
            trust=effective_trust(draft.trust, rule),
            trust_by_rule=rule,
            excerpt=draft.excerpt,
        )

    def _prompt(
        self,
        batch: list[Requirement],
        research: list[TechnologyResearch],
        components: list[ArchitectureComponent],
        study: FeasibilityStudy | None,
    ) -> str:
        req_lines = []
        for r in batch:
            existing = ""
            if r.implementation_approach:
                existing = f' approach_source="{r.approach_source}" approach="{r.implementation_approach[:200]}"'
            req_lines.append(
                f'<req id="{r.id}" rfp_id="{r.rfp_requirement_id or ""}" type="{r.type.value}" '
                f'category="{r.category.value}" mandatory="{r.is_mandatory}"{existing}>\n'
                f"name: {r.name}\ndescription: {r.description[:700]}\n"
                + (f"quote: {r.rfp_quote[:300]}\n" if r.rfp_quote else "")
                + "</req>"
            )
        linked_ids = {r.id for r in batch} | {
            r.rfp_requirement_id for r in batch if r.rfp_requirement_id
        }
        rs = [t for t in research if set(t.related_requirement_ids) & linked_ids] or research
        res_lines = [
            f'<item id="{t.id}" feasibility="{t.feasibility.value}" related="{",".join(t.related_requirement_ids[:8])}" sources="{len(t.sources)}">\n'
            f"topic: {t.topic}\nsummary: {t.summary[:300]}\n"
            + (f"stack: {', '.join(t.recommended_stack[:5])}\n" if t.recommended_stack else "")
            + (
                f"facts: {' | '.join(f[:120] for f in t.confirmed_facts[:3])}\n"
                if t.confirmed_facts
                else ""
            )
            + "</item>"
            for t in rs[:30]
        ]
        comp_lines = [
            f"- {c.layer} / {c.name} ({c.technology}) {c.description[:80]}".rstrip()
            for c in components[:40]
        ]
        cmp_lines = []
        if study:
            for comp in study.comparisons:
                cmp_lines.append(
                    f"- {comp.area}: RFP 명시={comp.rfp_specified or '없음'}; 권고={comp.recommendation[:80]}"
                )
        return (
            "<requirements>\n"
            + "\n".join(req_lines)
            + "\n</requirements>\n<research>\n"
            + ("\n".join(res_lines) if res_lines else "(기술 조사 기록 없음)")
            + "\n</research>\n<architecture>\n"
            + ("\n".join(comp_lines) if comp_lines else "(구성 요소 없음)")
            + "\n</architecture>\n<comparisons>\n"
            + ("\n".join(cmp_lines) if cmp_lines else "(비교 없음)")
            + "\n</comparisons>\n"
            "위 요구사항마다 구현방안(글머리 2~5줄)·난이도·검증 방법·검사 기준을 작성하라."
        )
