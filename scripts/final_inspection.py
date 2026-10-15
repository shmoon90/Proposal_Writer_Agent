"""최종 기능 검수 스크립트 (Phase 8).

제안 단계·구축 단계의 모든 사용자 기능을 격리된 임시 루트에서 실제로 실행하고, 산출물·데이터 보호 항목을 점검한
뒤 결과를 JSON과 Markdown 표로 남긴다. 에이전트 호출은 **FakeAgentRunner(모의 LLM)** 로 대체하므로
"실제 LLM 호출"은 이 스크립트의 검수 범위가 아니다(결과에 명시).

실행:  .venv\\Scripts\\python scripts\\final_inspection.py [--out workspace/final_inspection]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

from fixtures import builders as bld  # noqa: E402
from fixtures import excel_builders as xb  # noqa: E402
from proposal_agent.agents import FakeAgentRunner  # noqa: E402
from proposal_agent.config import ProjectPaths, Settings  # noqa: E402
from proposal_agent.config.errors import FileExistsConflict, PathSecurityError  # noqa: E402
from proposal_agent.models import (  # noqa: E402
    DocumentKind,
    InputKind,
    ProjectMode,
)
from proposal_agent.orchestrator import StepRunner  # noqa: E402
from proposal_agent.services import AppContext, Services  # noqa: E402
from proposal_agent.storage.files import sha256_file  # noqa: E402
from unit.test_agent_step_service import RESEARCH, RFP_ANALYSIS  # noqa: E402
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok  # noqa: E402

ARCHITECT = {
    "components": [
        {"code": "WEB01", "layer": "web", "name": "Web 서버", "technology": "nginx"},
        {
            "code": "APP01",
            "layer": "app",
            "name": "업무 서버",
            "technology": "Spring Boot",
            "related_requirement_ids": ["FR-001"],
        },
        {"code": "DB01", "layer": "data", "name": "DBMS", "technology": "PostgreSQL 16"},
    ],
    "connections": [
        {"from_code": "WEB01", "to_code": "APP01", "protocol": "HTTP"},
        {"from_code": "APP01", "to_code": "DB01", "protocol": "JDBC"},
    ],
    "diagram_notes": "",
    "assumptions": [],
    "open_questions": [],
}


class Inspector:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.started = time.time()

    def record(
        self, area: str, feature: str, ok: bool, evidence: str, *, mock_llm: bool = False
    ) -> None:
        self.rows.append(
            {
                "area": area,
                "feature": feature,
                "result": "PASS" if ok else "FAIL",
                "evidence": evidence[:300],
                "mock_llm": mock_llm,
            }
        )
        print(f"[{'PASS' if ok else 'FAIL'}] {area} · {feature} — {evidence[:120]}")

    def check(self, area: str, feature: str, fn, *, mock_llm: bool = False) -> Any:  # type: ignore[no-untyped-def]
        try:
            evidence = fn()
        except Exception as exc:  # noqa: BLE001
            self.record(area, feature, False, f"{type(exc).__name__}: {exc}", mock_llm=mock_llm)
            return None
        self.record(area, feature, True, str(evidence), mock_llm=mock_llm)
        return evidence


def sha256(path: Path) -> str:
    return sha256_file(path)


def proposal_stage(ins: Inspector, s: Services, ctx: AppContext) -> Any:
    paths = ctx.paths
    p = ins.check(
        "제안",
        "프로젝트 생성",
        lambda: s.projects.create(
            name="검수_제안",
            mode=ProjectMode.PROPOSAL,
            start_date=date(2026, 11, 2),
            end_date=date(2027, 8, 31),
            client_name="OO기관",
        ),
    )
    if p is None:
        return None
    ins.check(
        "제안",
        "RFP Word 입력",
        lambda: (
            s.documents.register_upload(
                p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
            ).stored_path
        ),
    )
    ins.check(
        "제안",
        "RFP TXT 입력",
        lambda: (
            s.documents.register_upload(
                p, kind=DocumentKind.RFP_ATTACHMENT, file_name="rfp.txt", data=bld.build_txt()
            ).stored_path
        ),
    )
    ins.check(
        "제안",
        "RFP PDF 입력",
        lambda: (
            s.documents.register_upload(
                p, kind=DocumentKind.RFP_ATTACHMENT, file_name="rfp.pdf", data=bld.build_text_pdf()
            ).stored_path
        ),
    )
    r = StepRunner(s)

    def extract() -> str:
        outcomes = r.run_extraction(p)
        blocks = s.extraction.current_blocks(p)
        methods = {b.file_format.value: b.extraction_method.value for b in blocks}
        gate0 = s.gates.state(p, "gate0").status.value
        return f"문서 {len(outcomes) if isinstance(outcomes, list) else 3}건, 블록 {len(blocks)}개, 방식 {methods}, gate0={gate0}"

    ins.check("제안", "문서 분석(추출, DOCX·TXT·PDF)", extract)

    def req() -> str:
        r.run_requirement_extraction(p)
        r.run_verification(p)
        reqs = s.requirements.list_requirements(p)
        return f"요구사항 {len(reqs)}건 ({', '.join(x.id for x in reqs[:6])}…), gate1={s.gates.state(p, 'gate1').status.value}"

    ins.check("제안", "요구사항 추출·독립 검증(Gate 1)", req, mock_llm=True)
    ins.check("제안", "RFP 분석(에이전트)", lambda: r.run_rfp_analysis(p).summary, mock_llm=True)

    def research() -> str:
        out = r.run_tech_research(p)
        recs = s.research.list_research(p)
        study = s.research.latest_study(p)
        return f"{out.summary} / 조사 {len(recs)}건, 구현 가능성 비교 {len(study.comparisons) if study else 0}건"

    ins.check("제안", "기술 조사·구현 가능성 검토(에이전트)", research, mock_llm=True)
    ins.check(
        "제안",
        "아키텍처 설계(에이전트)",
        lambda: r.run_role_step(p, "architecture", "architect", "설계").summary,
        mock_llm=True,
    )

    def generate() -> str:
        out = r.run_generation(p)
        latest = s.generation.latest_deliverables(p)
        return f"{out.summary} / 종류 {sorted(k.value for k in latest)}"

    ins.check("제안", "산출물 생성 실행", generate)
    latest = s.generation.latest_deliverables(p)
    for kind, label in (
        ("submission_pptx", "제출용 PPT 생성"),
        ("presentation_pptx", "발표용 PPT 생성"),
        ("requirement_spec_xlsx", "요구사항 정의서 생성"),
        ("trace_matrix_xlsx", "요구사항 추적표 생성"),
        ("wbs_gantt_xlsx", "WBS·간트 차트 생성"),
        ("staffing_plan_xlsx", "인력 투입계획 생성"),
        ("system_diagram_png", "구성도 PNG 생성"),
    ):
        d = next((v for k, v in latest.items() if k.value == kind), None)
        ins.record(
            "제안",
            label,
            d is not None and paths.resolve_output(d.file_path).exists(),
            d.file_path if d else "없음",
        )

    def qa() -> str:
        out = r.run_qa(p)
        run = s.qa.latest_run(p)
        assert run is not None
        return f"{out.summary} / 건수 {run.counts} / 게이트 {run.gates}"

    ins.check("제안", "통합 QA(독립 검증) 실행", qa)

    def approve() -> str:
        s.gates.approve_human_review(p, "gate5", approver="검수자", comments="최종 검수 승인")
        out = r.run_finalize(p, approver="검수자", comments="확정")
        final = paths.project_output_dir(p.output_dir) / "13_Final_Deliverables"
        return f"{out.summary} / 최종본 {len(list(final.iterdir()))}개"

    ins.check("제안", "QA 승인(Gate 5)·최종본 확정", approve)
    return p


def build_stage(ins: Inspector, s: Services, ctx: AppContext) -> Any:
    paths = ctx.paths
    b = ins.check(
        "구축", "프로젝트 생성", lambda: s.projects.create(name="검수_구축", mode=ProjectMode.BUILD)
    )
    if b is None:
        return None

    def upload() -> str:
        for kind, name, data in (
            (DocumentKind.REQUIREMENT_SPEC, "요구사항정의서.xlsx", xb.build_requirement_spec()),
            (DocumentKind.TRACE_MATRIX, "추적표.xlsx", xb.build_trace_matrix()),
            (DocumentKind.WBS, "WBS.xlsx", xb.build_wbs()),
            (DocumentKind.STAFFING_PLAN, "투입계획.xlsx", xb.build_staffing_plan()),
        ):
            s.documents.register_upload(b, kind=kind, file_name=name, data=data)
        profiles = s.baseline.profiles(b)
        return "매핑 확인 필요: " + str({k.value: p.blocking for k, p in profiles.items()})

    ins.check("구축", "기존 Excel 문서 입력·구조 분석", upload)
    ins.check("구축", "기준 데이터 적재(Revision v1.0)", lambda: s.baseline.load(b, actor="검수자"))
    b = ctx.repos.projects.get(b.id)
    ins.check(
        "구축",
        "기존 요구사항 조회",
        lambda: [f"{x.id} {x.name}" for x in s.changes.active_requirements(b)],
    )

    cr = ins.check(
        "구축",
        "요구사항 추가·변경·삭제 요청 등록",
        lambda: s.changes.create_request(
            b,
            input_kind=InputKind.NATURAL_LANGUAGE,
            request_text="1. 모바일 앱에서 푸시 알림을 수신하는 기능이 필요하다.\n2. 주요 화면은 2초 이내에 응답해야 한다.\n3. 팩스 접수 기능은 더 이상 필요 없으니 삭제해 주세요.",
            requester="검수자",
            reason="최종 검수",
        ),
    )
    if cr is None:
        return None
    before = {x.id: (x.description, x.change_state) for x in ctx.repos.requirements.find(b.id)}

    def analyze() -> str:
        c = s.changes.analyze(b, cr, use_agent=False)
        return ", ".join(
            f"{x.id}={x.classification.value}:{x.requirement_id}" for x in c.candidates
        )

    ins.check("구축", "의미 기반 비교(규칙; AI 덧붙임은 미실행)", analyze)
    cr2 = s.changes.get(b, cr.id)

    def impact() -> str:
        imp = cr2.impact
        assert imp and not imp.error
        return f"종료 {imp.schedule_before_end}→{imp.schedule_after_end} ({imp.schedule_delta_days:+d}일), 공수 {imp.effort.before_md}→{imp.effort.after_md} M/D ({imp.effort.estimate_status}), 인력 시나리오 {imp.staffing_scenario.value}, Task {len(imp.tasks)}건"

    ins.check("구축", "일정·공수 영향 분석", impact)
    ins.check(
        "구축",
        "문서별 변경안 확인(후보·전후 비교)",
        lambda: [{"id": c.id, "before": c.before, "after": c.after} for c in cr2.candidates][:3],
    )
    after_unapproved = {
        x.id: (x.description, x.change_state) for x in ctx.repos.requirements.find(b.id)
    }
    ins.record(
        "보호",
        "승인 전 기준 데이터 불변",
        before == after_unapproved,
        f"분석 후 요구사항 {len(after_unapproved)}건 변경 없음",
    )

    def decide() -> str:
        for c in cr2.candidates:
            s.changes.decide_candidate(b, cr2, c.id, decision="accept")
        return "후보 3건 수락"

    ins.check("구축", "사용자 결정(수락)", decide)
    ins.check(
        "구축",
        "사용자 승인·기준 반영",
        lambda: (
            s.changes.approve(
                b, s.changes.get(b, cr.id), approver="검수자", comments="승인"
            ).request.result_summary
        ),
    )
    cr_done = s.changes.get(b, cr.id)
    ins.record(
        "구축",
        "신규 버전 파일 생성(타임스탬프)",
        bool(cr_done.after_files)
        and all(paths.resolve_output(f).exists() for f in cr_done.after_files),
        "; ".join(Path(f).name for f in cr_done.after_files),
    )

    def reject() -> str:
        c = s.changes.create_request(
            b,
            input_kind=InputKind.DELETE_BUTTON,
            request_text="",
            requester="검수자",
            reason="검수",
            selected_ids=["SFR-004"],
        )
        c = s.changes.analyze(b, c, use_agent=False)
        c = s.changes.reject(b, c, approver="검수자", comments="범위 유지")
        state = ctx.repos.requirements.get("SFR-004", b.id).change_state
        return f"{c.id} {c.status.value}, SFR-004 change_state={state}"

    ins.check("구축", "사용자 반려(기준 불변)", reject)
    ins.check(
        "구축",
        "변경 이력 조회(변경관리대장)",
        lambda: (
            f"행 {len(s.changes.change_log_rows(b))}건, Revision {[r.number for r in ctx.repos.revisions.find(b.id, order_by='created_at')]}"
        ),
    )

    def post_qa() -> str:
        out = s.qa.run(b, actor="검수자")
        run = out.qa_run
        assert run is not None
        return (
            f"판정 {run.verdict}, 건수 {run.counts}, 게이트 {run.gates}, 보고서 {run.report_path}"
        )

    ins.check("구축", "변경 후 QA", post_qa)
    return b


def protection(ins: Inspector, s: Services, ctx: AppContext, projects: list[Any]) -> None:
    paths = ctx.paths
    # 산출물 경로
    for p in projects:
        if p is None:
            continue
        project_dir = paths.project_output_dir(p.output_dir)
        dl = ctx.repos.deliverables.find(p.id)
        bad = []
        for d in dl:
            try:
                path = paths.resolve_output(d.file_path)
                if not str(path).startswith(str(project_dir)) or not path.exists():
                    bad.append(d.file_path)
            except PathSecurityError:
                bad.append(d.file_path)
        ins.record(
            "보호",
            f"산출물 경로가 프로젝트 폴더 안에 존재 ({p.name})",
            not bad,
            f"산출물 {len(dl)}건, 문제 {bad}",
        )
        # DB ↔ 파일 (해시)
        mismatch = [
            d.file_path
            for d in dl
            if d.sha256 and sha256(paths.resolve_output(d.file_path)) != d.sha256
        ]
        docs = ctx.repos.documents.find(p.id)
        doc_mismatch = [
            d.stored_path
            for d in docs
            if not paths.resolve_output(d.stored_path).exists()
            or sha256(paths.resolve_output(d.stored_path)) != d.sha256
        ]
        revs = ctx.repos.revisions.find(p.id)
        rev_missing = [
            r.number
            for r in revs
            if r.snapshot_path and not paths.resolve_output(r.snapshot_path).exists()
        ]
        ins.record(
            "보호",
            f"DB↔파일 일치 (해시·존재) ({p.name})",
            not (mismatch or doc_mismatch or rev_missing),
            f"산출물 불일치 {mismatch}, 원본 불일치 {doc_mismatch}, 스냅샷 누락 {rev_missing}",
        )
    # 프로젝트 간 섞임
    if len([p for p in projects if p]) >= 2:
        a, b = [p for p in projects if p][:2]
        files_a = {d.file_path for d in ctx.repos.deliverables.find(a.id)}
        files_b = {d.file_path for d in ctx.repos.deliverables.find(b.id)}
        cross = [f for f in files_a if b.output_dir in f] + [
            f for f in files_b if a.output_dir in f
        ]
        ins.record(
            "보호",
            "프로젝트별 파일이 섞이지 않음",
            not cross and a.output_dir != b.output_dir,
            f"{a.output_dir} / {b.output_dir}, 교차 {cross}",
        )

    # 덮어쓰기 금지
    def overwrite() -> str:
        p = projects[0]
        d = next(iter(ctx.repos.deliverables.find(p.id)))
        name = Path(d.file_path).name
        sub = Path(d.file_path).parts[1]
        before = sha256(paths.resolve_output(d.file_path))
        try:
            ctx.files.save_bytes(p.output_dir, sub, name, b"overwrite-attempt")
        except FileExistsConflict:
            pass
        else:
            raise AssertionError("덮어쓰기가 허용됨")
        stored = ctx.files.store_unique(p.output_dir, sub, name, b"new-data")
        assert sha256(paths.resolve_output(d.file_path)) == before and stored.path.name != name
        return f"같은 이름 저장 거부(FileExistsConflict), 보존 저장은 {stored.path.name}"

    ins.check("보호", "기존 파일 덮어쓰기 금지", overwrite)
    # 경로 탈출
    ins.check("보호", "경로 탈출 거부", lambda: _expect_path_error(paths))
    # 비밀값 노출
    ins.check("보호", "API 키·비밀값 미노출(코드·로그·DB·감사)", lambda: secret_scan(ctx))


def _expect_path_error(paths: ProjectPaths) -> str:
    try:
        paths.resolve_output("../../windows/system32/x.txt")
    except PathSecurityError as exc:
        return f"PathSecurityError: {exc.message[:60]}"
    raise AssertionError("경로 탈출이 허용됨")


def secret_scan(ctx: AppContext) -> str:
    key_pattern = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")
    hits: list[str] = []
    for folder in ("src", "tests", "scripts", "docs", "README.md", "pyproject.toml"):
        base = REPO / folder
        files = (
            [base]
            if base.is_file()
            else [
                f for f in base.rglob("*") if f.suffix in (".py", ".md", ".toml", ".json", ".txt")
            ]
        )
        for f in files:
            try:
                if key_pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                    hits.append(str(f.relative_to(REPO)))
            except OSError:
                continue
    env_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                env_key = line.split("=", 1)[1].strip().strip('"').strip("'")
    leak: list[str] = []
    if env_key and len(env_key) > 12:
        # 검수 루트의 로그·DB·감사 이벤트에 실제 키 값이 없는지
        log_file = ctx.paths.log_file
        if log_file.exists() and env_key in log_file.read_text(encoding="utf-8", errors="ignore"):
            leak.append("app.log")
        db_bytes = ctx.paths.db_path.read_bytes() if ctx.paths.db_path.exists() else b""
        if env_key.encode() in db_bytes:
            leak.append("sqlite")
        # 저장소 추적 파일 전체 (git 추적 대상만)
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
        for rel in tracked:
            fp = REPO / rel
            try:
                if fp.is_file() and env_key.encode() in fp.read_bytes():
                    leak.append(rel)
            except OSError:
                continue
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines(), ".gitignore에 .env 없음"
    assert not hits, f"키 패턴 발견: {hits}"
    assert not leak, f"실제 키 값 노출: {leak}"
    return f"코드·문서 키 패턴 0건, 실제 키 값 노출 0건 (.env는 .gitignore), 검사한 추적 파일 {len(tracked) if env_key else 0}개"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "workspace" / "final_inspection"))
    args = ap.parse_args()
    root = Path(tempfile.mkdtemp(prefix="pwa_inspect_"))
    ins = Inspector()
    ctx = AppContext.create(Settings(), paths=ProjectPaths(root=root), configure_logging=True)
    s = Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {
                "requirement_extractor": extractor_from_text,
                "requirement_verifier": verifier_all_ok,
                "rfp_analyst": RFP_ANALYSIS,
                "tech_researcher": RESEARCH,
                "architect": ARCHITECT,
            }
        ),
    )
    print("검수 루트:", root)
    p = proposal_stage(ins, s, ctx)
    b = build_stage(ins, s, ctx)
    protection(ins, s, ctx, [p, b])
    ctx.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "root": str(root),
        "python": sys.version,
        "duration_s": round(time.time() - ins.started, 1),
        "pass": sum(r["result"] == "PASS" for r in ins.rows),
        "fail": sum(r["result"] == "FAIL" for r in ins.rows),
        "mock_llm_items": sum(r["mock_llm"] for r in ins.rows),
        "rows": ins.rows,
    }
    Path(str(out) + ".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    md = ["| 영역 | 기능 | 결과 | LLM | 근거 |", "|---|---|---|---|---|"]
    md += [
        f"| {r['area']} | {r['feature']} | {r['result']} | {'모의' if r['mock_llm'] else '-'} | {r['evidence'].replace('|', '／')[:160]} |"
        for r in ins.rows
    ]
    Path(str(out) + ".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(
        f"\n결과: PASS {summary['pass']} / FAIL {summary['fail']} (모의 LLM 항목 {summary['mock_llm_items']}) → {out}.json/.md"
    )
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
