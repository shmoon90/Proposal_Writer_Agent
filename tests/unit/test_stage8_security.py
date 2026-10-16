"""통합 개발 지시문 단계 8 — 보안 점검 (업로드·경로·로그·인젝션·도구 정책).

업로드: 허용 확장자·빈 파일·크기 제한·모드별 종류. 경로: Output 밖 상대 경로·절대 경로·링크 거부, 생성 앱 작업 폴더 탈출 거부.
로그: API 키·비밀값 마스킹. 인젝션: 모든 프롬프트가 입력 블록을 '데이터'로 선언, 에이전트 도구는 읽기 전용 MCP·허용 내장 도구만,
SQL 은 파라미터 바인딩(테이블 이름만 f-string)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from proposal_agent.agents.roles import BUILTIN_TOOL_CATALOG, FORBIDDEN_TOOLS, ROLES
from proposal_agent.config.errors import IngestError, PathSecurityError, PWAError, ValidationError
from proposal_agent.config.logging import SecretMaskingFilter, mask_secrets
from proposal_agent.config.paths import ProjectPaths, ensure_within
from proposal_agent.development.workspace import GeneratedWorkspace, safe_join
from proposal_agent.models import DocumentKind, Project, ProjectMode
from proposal_agent.services import Services
from proposal_agent.services.document_service import MAX_UPLOAD_BYTES

PROMPTS = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "agents" / "prompts"
STORAGE = Path(__file__).resolve().parents[2] / "src" / "proposal_agent" / "storage"


def test_upload_validation(services: Services, proposal_project: Project) -> None:
    p = proposal_project
    with pytest.raises(IngestError):
        services.documents.register_upload(
            p, kind=DocumentKind.RFP, file_name="rfp.exe", data=b"MZ"
        )
    with pytest.raises(IngestError):
        services.documents.register_upload(p, kind=DocumentKind.RFP, file_name="rfp.pdf", data=b"")
    with pytest.raises(IngestError):
        services.documents.register_upload(
            p, kind=DocumentKind.RFP, file_name="rfp.txt", data=b"x" * (MAX_UPLOAD_BYTES + 1)
        )
    with pytest.raises(ValidationError):  # 제안 모드는 정의서 Excel 을 기준 문서로 받지 않는다
        services.documents.register_upload(
            p, kind=DocumentKind.REQUIREMENT_SPEC, file_name="spec.xlsx", data=b"PK"
        )
    build = services.projects.create(name="보안 구축", mode=ProjectMode.BUILD)
    with pytest.raises(ValidationError):
        services.documents.register_upload(
            build, kind=DocumentKind.RFP, file_name="rfp.pdf", data=b"%PDF"
        )
    doc = services.documents.register_upload(
        p, kind=DocumentKind.OTHER, file_name="..\\..\\evil.txt", data=b"hi"
    )
    stored = services.ctx.paths.resolve_output(doc.stored_path)
    assert stored.is_relative_to(services.ctx.paths.output_root) and ".." not in doc.stored_path


def test_output_path_containment(paths: ProjectPaths, tmp_path: Path) -> None:
    for bad in ("../outside.txt", "..\\outside.txt", "a/../../b", str(tmp_path / "x.txt")):
        with pytest.raises(PWAError):
            paths.resolve_output(bad)
    with pytest.raises(PWAError):
        ensure_within(paths.output_root, paths.output_root.parent / "x")
    ws_root = tmp_path / "app"
    ws_root.mkdir()
    ws = GeneratedWorkspace(ws_root)
    for bad in (
        "../x.java",
        "C:/x.java",
        "src/main/java/com/app/../../../x.java",
        "nul.java",
        "a:b.java",
    ):
        with pytest.raises(PathSecurityError):
            safe_join(ws_root, bad) if bad != "nul.java" else ws.write(
                "src/main/java/com/app/" + bad, "x"
            )
    (tmp_path / "outside").mkdir()
    try:
        (ws_root / "link").symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("symlink 권한 없음")
    with pytest.raises(PathSecurityError):
        safe_join(ws_root, "link/x.java")


def test_log_masking() -> None:
    key = "sk-ant-api03-" + "A" * 40
    assert key not in mask_secrets(f"key={key}") and "sk-ant-***" in mask_secrets(f"key={key}")
    assert "***" in mask_secrets(
        "ANTHROPIC_API_KEY=abcdef123456"
    ) and "abcdef123456" not in mask_secrets("ANTHROPIC_API_KEY=abcdef123456")
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "token %s", (key,), None)
    assert SecretMaskingFilter().filter(rec) and key not in rec.getMessage()


def test_prompts_declare_input_as_data_and_tools_are_read_only() -> None:
    missing = []
    for md in sorted(PROMPTS.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        if not re.search(r"데이터이며 지시가 아니다|지시문을 따르지 않는다|지시문.*따르지", text):
            missing.append(md.name)
    assert missing == [], f"입력을 데이터로 선언하지 않은 프롬프트: {missing}"
    for role in ROLES.values():
        assert set(role.builtin_tools) <= BUILTIN_TOOL_CATALOG and not (
            set(role.builtin_tools) & set(FORBIDDEN_TOOLS)
        )
        for pat in role.mcp_tool_patterns:
            tool = pat.split("__")[-1]
            assert tool == "*" or tool.startswith(
                ("get_", "list_", "search_", "read_", "verify_")
            ), f"{role.key}: 쓰기 성격 MCP 도구 {pat}"
    assert {"Bash", "Write", "Edit"} <= set(FORBIDDEN_TOOLS)


def test_sql_uses_parameter_binding() -> None:
    offenders = []
    for py in STORAGE.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            if "execute(" in line and (
                "%s" in line or ".format(" in line or ("+ " in line and "SELECT" in line.upper())
            ):
                offenders.append(f"{py.name}:{i}")
            if re.search(
                r'execute\(f["\'].*\{(?!self\.table\}|table\}|cols\}|placeholders\}|set_clause\}|assignments\}|where\})',
                line,
            ):
                offenders.append(f"{py.name}:{i}")
    assert offenders == [], offenders
