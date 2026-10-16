"""발주처 업무·기존 시스템 문맥 (단계 6 ⑤, D-21): RFP 분석 결과와 프로젝트 설정에서 구조화해 설계·구현 방안 에이전트 입력으로 준다.

구현 방안이 일반론이 되지 않으려면 "왜 이 방식인가"의 근거가 되는 발주처 사정(현행 문제점·기존 시스템·연계 대상·명시 솔루션·
개발 환경·보안 규정)이 프롬프트에 있어야 한다. 값은 RFP 분석(rfp_analyst 출력)과 설정에 있는 것만 쓰고, 없으면 "(없음)" 으로
남겨 에이전트가 추정하지 않게 한다.
"""

from __future__ import annotations

import json
from typing import Any

from proposal_agent.models import Project, ProjectSettings

_FIELDS: tuple[tuple[str, str], ...] = (
    ("overview", "사업 목적·배경"),
    ("client_goals", "발주처 목표"),
    ("current_issues", "현행 시스템 문제점"),
    ("integration_targets", "연계 대상 시스템"),
    ("named_solutions", "명시된 솔루션·기술"),
    ("dev_environment", "개발 환경·기술 제약"),
    ("security_privacy", "정보보호·개인정보 규정"),
    ("data_migration_operation", "데이터 이관·운영 요구"),
    ("constraints", "제약"),
)


def client_context(
    analysis: dict[str, Any] | None, settings: ProjectSettings | None
) -> dict[str, Any]:
    """RFP 분석 + 프로젝트 설정 → 발주처 문맥 dict (값이 없는 항목은 빈 값)."""
    a = analysis or {}
    out: dict[str, Any] = {}
    for key, _label in _FIELDS:
        v = a.get(key)
        if isinstance(v, list):
            out[key] = [str(x)[:200] for x in v[:12]]
        elif isinstance(v, str):
            out[key] = v[:600]
        else:
            out[key] = [] if key != "overview" else ""
    st = settings or ProjectSettings()
    out["existing_system"] = {
        "exists": st.has_existing_system,
        "note": (st.existing_system_note or "")[:400],
    }
    if st.integration_systems:
        out["integration_targets"] = list(
            dict.fromkeys([*out["integration_targets"], *[str(x) for x in st.integration_systems]])
        )[:16]
    if st.external_solutions:
        out["named_solutions"] = list(
            dict.fromkeys([*out["named_solutions"], *[str(x) for x in st.external_solutions]])
        )[:16]
    if st.security_privacy_requirements:
        out["security_privacy"] = list(
            dict.fromkeys(
                [*out["security_privacy"], *[str(x) for x in st.security_privacy_requirements]]
            )
        )[:16]
    if st.description:
        out["project_description"] = st.description[:400]
    if st.rfp_specified_tech:
        out["rfp_specified_tech"] = [str(x) for x in st.rfp_specified_tech][:12]
    return out


def client_context_block(
    project: Project, analysis: dict[str, Any] | None, settings: ProjectSettings | None
) -> str:
    """프롬프트에 넣는 `<client_context>` 블록. 값이 없으면 '(없음)' 을 명시해 추정을 막는다."""
    ctx = client_context(analysis, settings)
    lines = [
        f'<client_context project="{project.name}" client="{project.client_name or "(미기재)"}">'
    ]
    for key, label in _FIELDS:
        v = ctx.get(key)
        if isinstance(v, list):
            lines.append(f"- {label}: " + ("; ".join(v) if v else "(없음)"))
        else:
            lines.append(f"- {label}: {v or '(없음)'}")
    es = ctx["existing_system"]
    lines.append(
        "- 기존 시스템: "
        + ("있음 — " + (es["note"] or "설명 없음") if es["exists"] else "없음 또는 미확인")
    )
    if ctx.get("rfp_specified_tech"):
        lines.append("- RFP 지정 기술: " + "; ".join(ctx["rfp_specified_tech"]))
    if ctx.get("project_description"):
        lines.append("- 프로젝트 설명(설정): " + ctx["project_description"])
    lines.append(
        "위 문맥에 없는 발주처 사정은 추정하지 말고 전제·확인 필요로 남겨라. 구현 방안·설계에는 "
        "'왜 이 방식인가'를 현행 문제점·연계 대상·제약과 연결해 적어라."
    )
    lines.append("</client_context>")
    return "\n".join(lines)


def client_context_json(analysis: dict[str, Any] | None, settings: ProjectSettings | None) -> str:
    return json.dumps(client_context(analysis, settings), ensure_ascii=False)


__all__ = ["client_context", "client_context_block", "client_context_json"]
