"""대용량 RFP 성능 측정 (단계 8): 합성 RFP(요구사항 N건, 장 M개) 로 추출 → 요구사항 추출·검증(모의 에이전트) → 산출물 생성 → 통합 QA
각 단계의 소요 시간·메모리를 재서 workspace/PERFORMANCE.md 에 기록한다. 실제 모델은 호출하지 않는다.

사용: python scripts/measure_large_rfp.py --sizes 50,200,500 [--render]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import tracemalloc
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))


def synthetic_rfp(n_requirements: int) -> bytes:
    from fixtures.builders import Section, build_docx

    sections = [
        Section(
            "제1장 사업 개요",
            [
                "본 사업은 대용량 성능 측정을 위한 합성 제안요청서이다.",
                "사업 기간은 계약일로부터 12개월이며, 사업 예산은 부가세 포함 20억 원이다.",
            ],
        ),
        Section(
            "제2장 현황 및 문제점",
            [f"현행 시스템 문제점 {i + 1}: 수기 처리로 누락이 발생한다." for i in range(10)],
        ),
    ]
    per = 25
    kinds = ["FR", "FR", "FR", "NFR", "CON"]
    for chap in range(0, n_requirements, per):
        bullets = []
        for i in range(chap, min(chap + per, n_requirements)):
            kind = kinds[i % len(kinds)]
            letter = chr(ord("A") + (i % 26))
            bullets.append(
                f"{kind}-{letter}. 요구사항 {i + 1}: 사용자는 업무 {i + 1} 을 화면에서 등록·조회·수정하며 응답은 3초 이내여야 한다. 실패 시 오류 코드를 표시하고 재시도한다."
            )
        sections.append(
            Section(
                f"제{3 + chap // per}장 요구사항 {chap // per + 1}",
                [f"이 장은 요구사항 {chap + 1}~{min(chap + per, n_requirements)} 을 정의한다."],
                bullets,
            )
        )
    sections.append(
        Section(
            "제99장 제안서 작성 지침",
            ["제안서는 100쪽 이내로 작성한다.", "평가 기준: 기술 80점, 가격 20점."],
        )
    )
    return build_docx(sections=sections, title="합성 대용량 RFP")


def measure(n: int, *, render: bool) -> dict[str, object]:
    from proposal_agent.agents import FakeAgentRunner
    from proposal_agent.config import ProjectPaths, Settings
    from proposal_agent.models import DocumentKind, ProjectMode
    from proposal_agent.orchestrator import StepRunner
    from proposal_agent.services import AppContext, Services
    from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok

    root = Path(tempfile.mkdtemp(prefix=f"pwa-perf-{n}-"))
    ctx = AppContext.create(
        Settings(qa_render_check=render), paths=ProjectPaths(root=root), configure_logging=False
    )
    s = Services.from_context(
        ctx,
        runner=FakeAgentRunner(
            {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok},
            cost_per_call=0.0,
        ),
    )
    r = StepRunner(s)
    p = s.projects.create(
        name=f"성능 {n}",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 10, 31),
        client_name="측정",
    )
    data = synthetic_rfp(n)
    out: dict[str, object] = {"requirements_requested": n, "docx_bytes": len(data)}
    tracemalloc.start()
    s.documents.register_upload(p, kind=DocumentKind.RFP, file_name="rfp.docx", data=data)
    steps = [
        ("extract", lambda: r.run_extraction(p)),
        ("req_extract", lambda: r.run_requirement_extraction(p)),
        ("req_verify", lambda: r.run_verification(p)),
        ("generate_docs", lambda: r.run_generation(p)),
        ("qa", lambda: r.run_qa(p)),
    ]
    for key, fn in steps:
        t0 = time.perf_counter()
        fn()
        out[f"{key}_s"] = round(time.perf_counter() - t0, 2)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    out["peak_mb"] = round(peak / 1024 / 1024, 1)
    out["blocks"] = len(s.extraction.current_blocks(p))
    out["requirements_extracted"] = len(s.ctx.repos.requirements.find(p.id))
    qa = s.qa.latest_run(p)
    out["qa_counts"] = dict(qa.counts) if qa else {}
    out["total_s"] = round(
        sum(v for k, v in out.items() if isinstance(v, float) and k.endswith("_s")), 2
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="50,200,500")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    rows = []
    for raw in args.sizes.split(","):
        n = int(raw)
        print(f"측정 중: 요구사항 {n}건 …", flush=True)
        rows.append(measure(n, render=args.render))
        print(rows[-1], flush=True)
    lines = [
        "# 성능 측정 (대용량 RFP, 모의 에이전트, 단계 8)",
        "",
        f"측정일 {date.today()}. 실제 Claude 호출 없음 — 추출·규칙·생성·QA 코드 경로의 시간만 측정.",
        "",
        "| 요구사항 | docx KB | 블록 | 추출 | 요구 추출 | 검증 | 산출물 생성 | QA | 합계(초) | 최대 메모리(MB) | QA 실행/통과/실패 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for o in rows:
        c = o.get("qa_counts", {}) or {}
        lines.append(
            f"| {o['requirements_requested']} (추출 {o['requirements_extracted']}) | {int(o['docx_bytes']) // 1024} | {o['blocks']} | {o['extract_s']} | {o['req_extract_s']} | {o['req_verify_s']} | {o['generate_docs_s']} | {o['qa_s']} | {o['total_s']} | {o['peak_mb']} | {c.get('executed', '')}/{c.get('pass', '')}/{c.get('fail', '')} |"
        )
    (REPO / "workspace" / "PERFORMANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
