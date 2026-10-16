"""목차·전략 브리프와 Gate P(목차·전략 승인) (Phase 18, 요청서 §4).

RFP 분석 후 곧바로 전체 제안서를 쓰지 않고, 브리프(RFP 요약·요구사항 대응 방향·목차 초안·전략 3~5·차별화·핵심 기술·
위험·제출/발표 차이·확인 필요 사항)를 만들어 사람이 승인해야 제안 문안 작성과 최종 확정이 열린다.
- 브리프는 ``strategy_planner`` 역할이 쓰고(JSON은 AgentStepService가 저장), 코드가 Markdown 사본을 남긴다.
- Gate P는 항상 ``NEEDS_HUMAN_REVIEW``로 평가된다(사람 승인 필수). 코드는 RFP 지정 목차 보존 여부·전략 수·확인 필요
  사항을 사유로 적고, 승인/반려는 ``GateService``가 Approval로 기록한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from proposal_agent.agents.control import CancellationToken
from proposal_agent.agents.schemas import StrategyBrief
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.models import GateEvaluation, GateStatus, Project, ProjectMode
from proposal_agent.orchestrator.gates import GateService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.generators.service import GenerationService
    from proposal_agent.ingest.service import ExtractionService
    from proposal_agent.services.agent_step_service import AgentStepService
    from proposal_agent.services.audit import AuditService

log = get_logger("services.strategy")

GATEP_KEY = "gateP"
ROLE_STRATEGY = "strategy_planner"
BRIEF_SUBDIR = "07_Submission_Proposal_PPT"
BRIEF_STEM = "전략브리프"


@dataclass
class StrategyRunResult:
    brief: StrategyBrief
    markdown_path: str
    gate: GateEvaluation
    cost_usd: float = 0.0


class StrategyService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        files: FileStore,
        audit: AuditService,
        steps: AgentStepService,
        generation: GenerationService,
        extraction: ExtractionService,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._files = files
        self._audit = audit
        self._steps = steps
        self._generation = generation
        self._extraction = extraction
        self._gates = GateService(repos, audit)

    # --- 조회 ------------------------------------------------------------------------------------
    def latest(self, project: Project) -> StrategyBrief | None:
        data = self._steps.prior_output(project, ROLE_STRATEGY)
        if not data:
            return None
        try:
            return StrategyBrief.model_validate(data)
        except ValueError as exc:
            log.warning("전략 브리프 형식 오류: %s", exc)
            return None

    def gate_state(self, project: Project) -> Any:
        return self._gates.state(project, GATEP_KEY)

    # --- 프롬프트 -----------------------------------------------------------------------------------
    def brief_prompt(self, project: Project, *, reviewer_comments: str = "") -> str:
        # build_context는 계획·구성 요소 기본값을 저장하는 부작용이 있으므로 쓰지 않는다 (브리프는 읽기만)
        requirements = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.status.value != "deleted"
        ]
        research = self._repos.research.find(project.id, order_by="created_at")
        prof = self._extraction.rfp_profile(project)
        parts: list[str] = []
        parts.append(
            "<rfp_profile>\n"
            + (prof.summary_text() if prof else "프로파일 없음")
            + "\n</rfp_profile>"
        )
        tree = self._extraction.rfp_proposal_toc_tree(project)
        if tree:
            lines = []
            for ch in tree:
                lines.append(f"{ch.get('numeral', '')}. {ch.get('title', '')}".strip(". "))
                for i, sec in enumerate(ch.get("sections", []), start=1):
                    guide = "; ".join(sec.get("guide", [])[:3])
                    lines.append(
                        f"  {i}. {sec.get('title', '')}"
                        + (f" — 작성방법: {guide}" if guide else "")
                    )
            parts.append('<rfp_toc mandatory="true">\n' + "\n".join(lines) + "\n</rfp_toc>")
        else:
            parts.append(
                '<rfp_toc mandatory="false">\nRFP 지정 목차 없음 — 규칙 1의 기본 순서로 초안 작성\n</rfp_toc>'
            )
        req_lines = [
            f"- {r.id}{' / ' + r.rfp_requirement_id if r.rfp_requirement_id else ''} [{r.type.value}{', 필수' if r.is_mandatory else ''}, {r.acceptance_status.value}] "
            f"{r.name[:40]} | 구현 방안: {(r.implementation_approach or '미작성')[:120]} | 난이도: {r.difficulty.label if r.difficulty else '-'}"
            for r in requirements
        ]
        parts.append("<requirements>\n" + "\n".join(req_lines[:200]) + "\n</requirements>")
        res_lines = [
            f"- {t.id} {t.topic[:50]} | {t.feasibility.value} | 스택: {', '.join(t.recommended_stack[:4])} | 출처 {len(t.sources)}"
            for t in research
        ]
        parts.append(
            "<research>\n"
            + ("\n".join(res_lines[:60]) if res_lines else "(조사 없음)")
            + "\n</research>"
        )
        if reviewer_comments.strip():
            parts.append(
                "<reviewer_comments>\n" + reviewer_comments.strip() + "\n</reviewer_comments>"
            )
        parts.append(
            "위 자료로 목차·전략 브리프(StrategyBrief)를 작성하라. RFP 지정 목차는 보존하고, 근거 없는 수치·실적은 쓰지 않는다."
        )
        return "\n\n".join(parts)

    # --- 실행 ------------------------------------------------------------------------------------
    def run(
        self,
        project: Project,
        *,
        actor: str = "user",
        step_run_id: str | None = None,
        cancel: CancellationToken | None = None,
        reviewer_comments: str = "",
    ) -> StrategyRunResult:
        prompt = self.brief_prompt(project, reviewer_comments=reviewer_comments)
        result = self._steps.run_role(
            project, ROLE_STRATEGY, prompt, actor=actor, step_run_id=step_run_id, cancel=cancel
        )
        brief: StrategyBrief = result.output  # type: ignore[assignment]
        md = self.markdown(project, brief)
        name = self._files.next_version_name(project.output_dir, BRIEF_SUBDIR, BRIEF_STEM, ".md")
        stored = self._files.save_bytes(project.output_dir, BRIEF_SUBDIR, name, md.encode("utf-8"))
        gate = self.evaluate(project, brief, step_run_id=step_run_id, actor=actor)
        self._audit.record(
            project.id,
            "strategy.brief_written",
            actor=actor,
            payload={
                "markdown": stored.relative_path,
                "strategies": len(brief.strategies),
                "toc_chapters": len(brief.toc),
                "open_questions": len(brief.open_questions),
                "gate": gate.status.value,
                "cost_usd": result.response.cost_usd,
            },
        )
        return StrategyRunResult(
            brief=brief,
            markdown_path=stored.relative_path,
            gate=gate,
            cost_usd=result.response.cost_usd,
        )

    def evaluate(
        self,
        project: Project,
        brief: StrategyBrief | None = None,
        *,
        step_run_id: str | None = None,
        actor: str = "user",
    ) -> GateEvaluation:
        """Gate P 평가: 사람 승인이 필수이므로 항상 NEEDS_HUMAN_REVIEW. 사유에 코드 점검 결과를 적는다."""
        brief = brief or self.latest(project)
        reasons: list[str] = []
        metrics: dict[str, Any] = {}
        if brief is None:
            reasons.append(
                "전략 브리프가 없습니다. 브리프 없이 승인하면 코드 기본 목차·데이터 기반 문안으로 작성됩니다(사람 확인 필요)."
            )
        else:
            tree = (
                self._extraction.rfp_proposal_toc_tree(project)
                if project.mode == ProjectMode.PROPOSAL
                else []
            )
            missing = self._missing_rfp_chapters(brief, tree)
            if missing:
                reasons.append("RFP 지정 목차 장이 브리프 목차에 없음: " + ", ".join(missing[:6]))
            else:
                reasons.append(
                    "RFP 지정 목차 장을 모두 보존함"
                    if tree
                    else "RFP 지정 목차 없음 — 브리프 목차 초안 사용"
                )
            n = len(brief.strategies)
            if not 3 <= n <= 5:
                reasons.append(f"전략 수 {n}개 (권장 3~5)")
            if brief.toc_change_requests:
                reasons.append(
                    f"목차 변경 요청 {len(brief.toc_change_requests)}건 — 사용자 결정 필요"
                )
            if brief.open_questions:
                reasons.append(f"확인 필요 사항 {len(brief.open_questions)}건")
            metrics = {
                "strategies": n,
                "toc_chapters": len(brief.toc),
                "missing_rfp_chapters": missing,
                "open_questions": len(brief.open_questions),
                "requirement_directions": len(brief.requirement_directions),
            }
        reasons.append(
            "목차·전략은 사람이 검토·승인해야 전체 제안서 작성(제안 문안·최종 확정)이 열립니다."
        )
        ev = GateEvaluation(
            project_id=project.id,
            gate_key=GATEP_KEY,
            status=GateStatus.NEEDS_HUMAN_REVIEW,
            reasons=reasons,
            metrics=metrics,
            evaluated_by="code:services.strategy.evaluate",
            step_run_id=step_run_id,
        )
        self._repos.gate_evaluations.insert(ev)
        self._audit.record(
            project.id,
            "gate.evaluated",
            actor=actor,
            entity_type="GateEvaluation",
            entity_id=ev.id,
            payload={"gate": GATEP_KEY, "status": ev.status.value, "reasons": reasons},
        )
        return ev

    def ensure_evaluation(self, project: Project, *, actor: str = "user") -> GateEvaluation:
        ev = self._repos.gate_evaluations.latest(project.id, GATEP_KEY)
        return ev or self.evaluate(project, actor=actor)

    # --- 목차 트리 (덱 생성용) ----------------------------------------------------------------------
    def toc_tree(self, project: Project) -> list[dict[str, Any]]:
        """브리프 목차를 덱 빌더가 쓰는 트리 형식으로. RFP 지정 목차가 있으면 그것이 우선이므로 빈 목록."""
        brief = self.latest(project)
        if brief is None or not brief.toc:
            return []
        return [
            {
                "numeral": ch.numeral or _roman(i),
                "title": ch.title,
                "sections": [
                    {"number": str(j), "title": s, "guide": []}
                    for j, s in enumerate(ch.sections, start=1)
                ],
            }
            for i, ch in enumerate(brief.toc, start=1)
        ]

    @staticmethod
    def _missing_rfp_chapters(brief: StrategyBrief, tree: list[dict[str, Any]]) -> list[str]:
        titles = [str(ch.get("title", "")).strip() for ch in tree if ch.get("title")]
        brief_titles = [c.title.strip() for c in brief.toc]
        missing: list[str] = []
        for t in titles:
            key = _norm(t)
            if not any(key in _norm(b) or _norm(b) in key for b in brief_titles if b):
                missing.append(t)
        return missing

    # --- Markdown ------------------------------------------------------------------------------------
    @staticmethod
    def markdown(project: Project, b: StrategyBrief) -> str:
        lines = [
            f"# 목차·전략 브리프 — {project.name}",
            "",
            "승인 전 검토용. 승인 후 전체 제안서 작성이 시작됩니다.",
            "",
        ]
        lines += ["## 1. RFP 분석 요약", b.rfp_summary or "(없음)", ""]
        lines += [
            "## 2·3. 요구사항 중요도·대응 방향",
            "| ID | 중요도 | 대응 방향 |",
            "|---|---|---|",
        ]
        lines += [
            f"| {d.requirement_id} | {d.priority} | {d.direction} |"
            for d in b.requirement_directions
        ] or ["| (없음) | | |"]
        lines += ["", "## 4. 제안서 목차 초안"]
        for i, ch in enumerate(b.toc, start=1):
            tag = " (RFP 필수)" if ch.rfp_mandatory else ""
            lines.append(
                f"- **{ch.numeral or _roman(i)}. {ch.title}**{tag}"
                + (f" — {ch.note}" if ch.note else "")
            )
            lines += [f"  {j}. {s}" for j, s in enumerate(ch.sections, start=1)]
        if b.toc_change_requests:
            lines += ["", "**목차 변경 요청**"] + [f"- {x}" for x in b.toc_change_requests]
        lines += ["", "## 5·6. 주요 제안 전략과 차별화 근거"]
        for i, s in enumerate(b.strategies, start=1):
            lines += [f"### 전략 {i}. {s.title}", s.description, f"- 차별화: {s.differentiator}"]
            if s.related_requirement_ids:
                lines.append("- 관련 요구사항: " + ", ".join(s.related_requirement_ids))
            if s.evidence:
                lines.append("- 근거: " + " / ".join(s.evidence))
            lines.append("")
        lines += [
            "## 7. 핵심 기술·구현 방향",
            "| 영역 | 선택 | 이유 | 근거 조사 |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {k.area} | {k.choice} | {k.rationale} | {k.feasibility_basis} |"
            for k in b.key_technologies
        ] or ["| (없음) | | | |"]
        lines += ["", "## 8. 예상 위험과 대응", "| 위험 | 대응 | 관련 요구사항 |", "|---|---|---|"]
        lines += [
            f"| {r.risk} | {r.mitigation} | {', '.join(r.related_requirement_ids)} |"
            for r in b.risks
        ] or ["| (없음) | | |"]
        lines += [
            "",
            "## 9. 제출용 PPT와 발표용 PPT의 구성 차이",
            b.submission_vs_presentation or "(없음)",
            "",
        ]
        lines += ["## 10. 자료 부족·사용자 확인 필요 사항"] + (
            [f"- {q}" for q in b.open_questions] or ["- (없음)"]
        )
        return "\n".join(lines) + "\n"

    def brief_json(self, project: Project) -> str:
        brief = self.latest(project)
        return json.dumps(brief.model_dump(), ensure_ascii=False, indent=2) if brief else ""


def _norm(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum()).casefold()


def _roman(i: int) -> str:
    numerals = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ"]
    return numerals[i - 1] if 1 <= i <= len(numerals) else str(i)


__all__ = ["GATEP_KEY", "ROLE_STRATEGY", "StrategyRunResult", "StrategyService"]
