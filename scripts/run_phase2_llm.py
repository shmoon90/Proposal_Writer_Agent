"""Phase 2 실제 LLM 실행 스크립트 (수동).

모의 RFP(DOCX + 같은 내용의 PDF)를 임시 프로젝트에 올리고 추출 → 요구사항 추출(에이전트) → 독립 검증(에이전트)
→ Gate 1 평가를 실제 Claude Agent SDK로 수행한 뒤 결과·비용을 출력하고 JSON으로 남긴다.

실행:  .venv\\Scripts\\python scripts\\run_phase2_llm.py  (ANTHROPIC_API_KEY 필요, 비용 발생)
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from fixtures import builders as bld  # noqa: E402
from proposal_agent.config import ProjectPaths, load_settings  # noqa: E402
from proposal_agent.models import DocumentKind, ProjectMode  # noqa: E402
from proposal_agent.orchestrator import StepRunner  # noqa: E402
from proposal_agent.requirements.id_policy import normalize_text  # noqa: E402
from proposal_agent.services import AppContext, Services  # noqa: E402


def run_project(services: Services, name: str, file_name: str, data: bytes) -> dict:
    project = services.projects.create(name=name, mode=ProjectMode.PROPOSAL)
    services.documents.register_upload(
        project, kind=DocumentKind.RFP, file_name=file_name, data=data
    )
    runner = StepRunner(services)
    t0 = time.time()
    ext = runner.run_extraction(project)
    _, ex = runner.run_requirement_extraction(project)
    vo, vr = runner.run_verification(project)
    elapsed = time.time() - t0
    reqs = services.requirements.list_requirements(project)
    findings = services.requirements.open_findings(project)
    return {
        "file": file_name,
        "gate0": ext.gate.status.value if ext.gate else None,
        "gate1": vo.gate.status.value if vo.gate else None,
        "gate1_reasons": vo.gate.evaluation.reasons if vo.gate and vo.gate.evaluation else [],
        "requirements": [
            {
                "id": r.id,
                "type": r.type.value,
                "name": r.name,
                "scope": r.scope_class.value,
                "mandatory": r.is_mandatory,
                "conf": r.confidence,
                "verify": r.verification_status.value,
                "source": [s.location_label for s in r.source_refs],
            }
            for r in reqs
        ],
        "findings": [
            {"rule": f.rule_id, "level": f.level.value, "msg": f.message} for f in findings
        ],
        "unresolved": ex.unresolved,
        "dropped": ex.dropped_missing_source,
        "cost_usd": round(ex.cost_usd + vr.cost_usd, 4),
        "turns": ex.turns,
        "chunks": ex.chunks,
        "coverage": vr.coverage,
        "elapsed_s": round(elapsed, 1),
        "names_norm": sorted(normalize_text(r.name) for r in reqs),
    }


def main() -> int:
    settings = load_settings(ROOT / ".env")
    settings.require_api_key()
    root = Path(tempfile.mkdtemp(prefix="pwa_llm_"))
    ctx = AppContext.create(settings, paths=ProjectPaths(root), configure_logging=True)
    services = Services.from_context(ctx)
    print(f"model={settings.model_primary} workspace={root}")
    results = [
        run_project(services, "LLM 검증 DOCX", "rfp.docx", bld.build_docx()),
        run_project(services, "LLM 검증 PDF", "rfp.pdf", bld.build_text_pdf()),
    ]
    a, b = results
    docx_types = sorted(r["type"] for r in a["requirements"])
    pdf_types = sorted(r["type"] for r in b["requirements"])
    overlap = len(set(a["names_norm"]) & set(b["names_norm"]))
    summary = {
        "results": results,
        "docx_vs_pdf": {
            "docx_count": len(a["requirements"]),
            "pdf_count": len(b["requirements"]),
            "exact_name_overlap": overlap,
            "type_counts_docx": {t: docx_types.count(t) for t in set(docx_types)},
            "type_counts_pdf": {t: pdf_types.count(t) for t in set(pdf_types)},
        },
        "total_cost_usd": round(sum(r["cost_usd"] for r in results), 4),
    }
    out = ROOT / "workspace" / "phase2_llm_result.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        print(
            f"\n== {r['file']}: gate0={r['gate0']} gate1={r['gate1']} reqs={len(r['requirements'])} findings={len(r['findings'])} "
            f"cost=${r['cost_usd']} turns={r['turns']} chunks={r['chunks']} {r['elapsed_s']}s"
        )
        for q in r["requirements"]:
            print(
                f"   {q['id']:8} {q['type']:15} {q['scope']:10} conf={q['conf']:.2f} {q['verify']:14} {q['name'][:40]}  <- {q['source'][0] if q['source'] else '-'}"
            )
        for f in r["findings"]:
            print(f"   ! {f['level']} {f['rule']}: {f['msg'][:100]}")
        print("   gate1 reasons:", r["gate1_reasons"])
    print("\nDOCX vs PDF:", summary["docx_vs_pdf"], "total cost:", summary["total_cost_usd"])
    print("saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
