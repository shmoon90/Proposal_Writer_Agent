"""회귀 테스트 + 통합 QA 실행기.

1) pytest를 실제로 실행해 통과·실패·건너뜀 건수를 수집한다 (llm 마커 제외, sdk 포함).
2) 모의 RFP로 제안 단계 전체 흐름을, 표준 Excel로 구축 단계 전체 흐름을 격리된 임시 루트에서 실행하고
   통합 QA(독립 검증)를 돌린다. 또는 ``--root``/``--project-id``로 실제 프로젝트를 지정한다.
3) 보고서(``11_QA_Validation_Reports/통합QA보고서_vX.Y.md``)에 pytest 실제 결과를 첨부한다.

사용:
    python scripts/run_regression.py                 # 임시 루트에서 데모 프로젝트 2개 실행
    python scripts/run_regression.py --root C:\\pwa   # 실제 데이터 루트의 모든 프로젝트에 통합 QA
    python scripts/run_regression.py --skip-pytest
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))


def run_pytest() -> dict[str, object]:
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    counts = {
        k: int(v)
        for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|error|errors)", tail)
    }
    return {
        "name": "pytest (unit·integration·sdk, llm 제외)",
        "exit_code": proc.returncode,
        "summary": tail,
        "duration_s": round(time.time() - started, 1),
        **counts,
    }


def demo_projects(root: Path, tests_executed: list[dict[str, object]]) -> list[dict[str, object]]:
    from fixtures import builders as bld
    from fixtures import excel_builders as xb
    from proposal_agent.agents import FakeAgentRunner
    from proposal_agent.config import ProjectPaths, Settings
    from proposal_agent.models import DocumentKind, InputKind, ProjectMode
    from proposal_agent.orchestrator import StepRunner
    from proposal_agent.services import AppContext, Services
    from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok

    ctx = AppContext.create(Settings(), paths=ProjectPaths(root=root), configure_logging=False)
    s = Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
        ),
    )
    results: list[dict[str, object]] = []
    # 제안 단계
    p = s.projects.create(
        name="회귀_제안",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 8, 31),
        client_name="OO기관",
    )
    s.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    r = StepRunner(s)
    r.run_extraction(p)
    r.run_requirement_extraction(p)
    r.run_verification(p)
    r.run_generation(p)
    qa = s.qa.run(p, actor="regression", tests_executed=tests_executed)
    results.append(
        {
            "project": p.name,
            "mode": "proposal",
            "verdict": qa.gate.status.value,
            "counts": qa.qa_run.counts if qa.qa_run else {},
            "gates": qa.qa_run.gates if qa.qa_run else {},
            "report": str(ctx.paths.resolve_output(qa.report_path)),
        }
    )
    # 구축 단계: 적재 → 변경 승인·반영 → 반려 → 통합 QA
    b = s.projects.create(name="회귀_구축", mode=ProjectMode.BUILD)
    s.documents.register_upload(
        b,
        kind=DocumentKind.REQUIREMENT_SPEC,
        file_name="spec.xlsx",
        data=xb.build_requirement_spec(),
    )
    s.documents.register_upload(
        b, kind=DocumentKind.TRACE_MATRIX, file_name="trace.xlsx", data=xb.build_trace_matrix()
    )
    s.documents.register_upload(b, kind=DocumentKind.WBS, file_name="wbs.xlsx", data=xb.build_wbs())
    s.documents.register_upload(
        b, kind=DocumentKind.STAFFING_PLAN, file_name="staff.xlsx", data=xb.build_staffing_plan()
    )
    s.baseline.load(b, actor="regression")
    b = ctx.repos.projects.get(b.id)
    cr = s.changes.create_request(
        b,
        input_kind=InputKind.NATURAL_LANGUAGE,
        request_text="모바일 앱에서 푸시 알림을 수신하는 기능이 필요하다.\n팩스 접수 기능은 더 이상 필요 없으니 삭제해 주세요.",
        requester="regression",
        reason="회귀",
    )
    cr = s.changes.analyze(b, cr, use_agent=False)
    for c in cr.candidates:
        s.changes.decide_candidate(b, cr, c.id, decision="accept")
    s.changes.approve(b, cr, approver="regression", comments="회귀 승인")
    cr2 = s.changes.create_request(
        b,
        input_kind=InputKind.DELETE_BUTTON,
        request_text="",
        requester="regression",
        reason="회귀",
        selected_ids=["SFR-004"],
    )
    cr2 = s.changes.analyze(b, cr2, use_agent=False)
    s.changes.reject(b, cr2, approver="regression", comments="회귀 반려")
    qa_b = s.qa.run(b, actor="regression", tests_executed=tests_executed)
    results.append(
        {
            "project": b.name,
            "mode": "build",
            "verdict": qa_b.gate.status.value,
            "counts": qa_b.qa_run.counts if qa_b.qa_run else {},
            "gates": qa_b.qa_run.gates if qa_b.qa_run else {},
            "report": str(ctx.paths.resolve_output(qa_b.report_path)),
        }
    )
    ctx.close()
    return results


def existing_projects(
    root: Path, tests_executed: list[dict[str, object]], project_id: str | None
) -> list[dict[str, object]]:
    from proposal_agent.config import ProjectPaths, load_settings
    from proposal_agent.services import AppContext, Services

    ctx = AppContext.create(load_settings(), paths=ProjectPaths(root=root), configure_logging=False)
    s = Services.from_context(ctx)
    out: list[dict[str, object]] = []
    for p in ctx.repos.projects.list_all():
        if project_id and p.id != project_id:
            continue
        try:
            qa = s.qa.run(p, actor="regression", tests_executed=tests_executed)
        except Exception as exc:  # noqa: BLE001
            out.append({"project": p.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        out.append(
            {
                "project": p.name,
                "mode": p.mode.value,
                "verdict": qa.gate.status.value,
                "counts": qa.qa_run.counts if qa.qa_run else {},
                "gates": qa.qa_run.gates if qa.qa_run else {},
                "report": str(ctx.paths.resolve_output(qa.report_path)),
            }
        )
    ctx.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", help="데이터 루트 (없으면 임시 루트에 데모 프로젝트 생성)")
    ap.add_argument("--project-id", help="--root 안의 특정 프로젝트만")
    ap.add_argument("--skip-pytest", action="store_true")
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    args = ap.parse_args()
    tests: list[dict[str, object]] = []
    if not args.skip_pytest:
        tests.append(run_pytest())
        print("pytest:", tests[0]["summary"])
    if args.root:
        results = existing_projects(Path(args.root), tests, args.project_id)
    else:
        root = Path(tempfile.mkdtemp(prefix="pwa_regression_"))
        print("임시 루트:", root)
        results = demo_projects(root, tests)
    payload = {"tests": tests, "projects": results}
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    if args.json:
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
    failed = any(t.get("exit_code") not in (None, 0) for t in tests) or any(
        r.get("verdict") == "FAIL" or r.get("error") for r in results
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
