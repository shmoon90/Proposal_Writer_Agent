"""산출물 manifest (``Output/<프로젝트>/manifest.json``, Phase 16).

생성 실행(run)마다 산출물 목록(종류·경로·버전·해시·크기)과 시각을 **누적** 기록하고, 통합 QA가 끝나면 그 실행에
QA 결과(판정·건수·게이트·보고서 경로·그림 예외)를 붙인다. 산출물 파일 자체는 버전 파일명으로 보존되므로 manifest는
덮어쓰되 과거 run 항목은 지우지 않는다. 기존 ``00_~13_`` 폴더 구조는 그대로 두고, 요청서의 submission/presentation/
excel/qa/source 구분은 ``category`` 필드로 대응한다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proposal_agent.config.paths import ProjectPaths
from proposal_agent.models import Deliverable, DeliverableKind, Project, QaRun

MANIFEST_NAME = "manifest.json"
CATEGORY_BY_KIND: dict[DeliverableKind, str] = {
    DeliverableKind.SUBMISSION_PPTX: "submission",
    DeliverableKind.PRESENTATION_PPTX: "presentation",
    DeliverableKind.REQUIREMENT_SPEC_XLSX: "excel",
    DeliverableKind.TRACE_MATRIX_XLSX: "excel",
    DeliverableKind.WBS_GANTT_XLSX: "excel",
    DeliverableKind.STAFFING_PLAN_XLSX: "excel",
    DeliverableKind.SYSTEM_DIAGRAM_PNG: "source",
    DeliverableKind.SW_DIAGRAM_PNG: "source",
    DeliverableKind.SERVICE_DIAGRAM_PNG: "source",
    DeliverableKind.QA_REPORT_MD: "qa",
    DeliverableKind.PROJECT_SUMMARY_MD: "qa",
}


def manifest_path(paths: ProjectPaths, project: Project) -> Path:
    return paths.project_output_dir(project.output_dir) / MANIFEST_NAME


def load_manifest(paths: ProjectPaths, project: Project) -> dict[str, Any]:
    p = manifest_path(paths, project)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("runs"), list):
                return data
        except (OSError, ValueError):
            pass
    return {
        "project_id": project.id,
        "project_name": project.name,
        "mode": project.mode.value,
        "output_dir": project.output_dir,
        "updated_at": "",
        "runs": [],
    }


def _save(paths: ProjectPaths, project: Project, data: dict[str, Any]) -> Path:
    data["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    p = manifest_path(paths, project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def record_generation(
    paths: ProjectPaths,
    project: Project,
    deliverables: list[Deliverable],
    *,
    run_kind: str,
    version: str,
    run_id: str,
    extra_files: dict[str, str] | None = None,
    errors: list[str] | None = None,
    actor: str = "",
) -> Path:
    """생성 실행 1건을 manifest에 추가한다. ``extra_files``는 산출물 엔티티가 아닌 보조 파일(구성도 PNG·목차 결정 등)."""
    data = load_manifest(paths, project)
    items: list[dict[str, Any]] = []
    for d in deliverables:
        size = None
        try:
            size = paths.resolve_output(d.file_path).stat().st_size
        except OSError:
            pass
        items.append(
            {
                "kind": d.kind.value,
                "category": CATEGORY_BY_KIND.get(d.kind, "source"),
                "path": d.file_path,
                "version": d.version,
                "sha256": d.sha256,
                "bytes": size,
                "deliverable_id": d.id,
            }
        )
    data["runs"].append(
        {
            "run_id": run_id,
            "run_kind": run_kind,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "version": version,
            "actor": actor,
            "deliverables": items,
            "extra_files": dict(extra_files or {}),
            "errors": list(errors or []),
            "qa": None,
        }
    )
    return _save(paths, project, data)


def record_qa(paths: ProjectPaths, project: Project, qa_run: QaRun) -> Path | None:
    """가장 최근 run에 QA 결과를 붙인다 (run이 없으면 QA만 담은 run을 만든다)."""
    data = load_manifest(paths, project)
    photo_exceptions = [
        issue
        for c in qa_run.checks
        if c.check_id == "QA-FILE-12"
        for issue in c.issues
        if issue.startswith("예외:")
    ]
    summary = {
        "qa_run_id": qa_run.id,
        "verdict": qa_run.verdict,
        "counts": dict(qa_run.counts),
        "gates": dict(qa_run.gates),
        "report": qa_run.report_path,
        "json": qa_run.json_path,
        "fix_rounds": qa_run.fix_rounds,
        "failed_checks": [
            c.check_id for c in qa_run.checks if c.executed and c.final_result.value == "FAIL"
        ],
        "review_checks": [
            c.check_id
            for c in qa_run.checks
            if c.executed and c.final_result.value == "NEEDS_HUMAN_REVIEW"
        ],
        "not_run_checks": [c.check_id for c in qa_run.checks if not c.executed],
        "picture_exceptions": photo_exceptions,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if data["runs"]:
        data["runs"][-1]["qa"] = summary
    else:
        data["runs"].append(
            {
                "run_id": qa_run.id,
                "run_kind": "qa_only",
                "generated_at": summary["recorded_at"],
                "version": "",
                "deliverables": [],
                "extra_files": {},
                "errors": [],
                "qa": summary,
            }
        )
    return _save(paths, project, data)


__all__ = ["MANIFEST_NAME", "load_manifest", "manifest_path", "record_generation", "record_qa"]
