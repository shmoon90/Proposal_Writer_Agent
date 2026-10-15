"""실제 Claude Code 프로세스(번들 CLI)로 MCP 연결을 점검한다 (``sdk`` 마커).

모델 호출 전에 세션을 중단하므로 API 비용은 들지 않지만 API 키와 번들 CLI가 필요하다.
키가 없으면 skip. 외부 HTTP MCP(Claude Code 문서 서버)는 네트워크가 필요하므로 별도 테스트로 둔다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proposal_agent.agents.roles import MCP_PROJECT
from proposal_agent.agents.tools import TOOL_NAMES, ToolContext, build_project_server
from proposal_agent.config import ProjectPaths, load_settings
from proposal_agent.models import ProjectMode
from proposal_agent.services import AppContext, Services

pytestmark = pytest.mark.sdk

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sdk_services(tmp_path_factory: pytest.TempPathFactory) -> Services:
    settings = load_settings(ROOT / ".env")
    if not settings.has_api_key:
        pytest.skip("ANTHROPIC_API_KEY 없음 — SDK 연결 테스트 실행하지 않음")
    ctx = AppContext.create(
        settings, paths=ProjectPaths(tmp_path_factory.mktemp("sdk")), configure_logging=False
    )
    return Services.from_context(ctx)


def test_in_process_mcp_server_connects_and_broken_server_fails(sdk_services: Services) -> None:
    project = sdk_services.projects.create(name="SDK 연결", mode=ProjectMode.PROPOSAL)
    servers = {
        MCP_PROJECT: build_project_server(
            ToolContext(sdk_services.ctx.repos, sdk_services.ctx.paths, project)
        ),
        "broken-stdio": {"command": "nonexistent-command-xyz", "args": []},
    }
    report = sdk_services.runner.test_connection(servers, ("WebSearch", "WebFetch"), timeout_s=120)
    assert report.status(MCP_PROJECT) == "connected", report
    assert report.status("broken-stdio") == "failed", report
    assert set(TOOL_NAMES) <= set(report.tools), report.tools
    assert "WebSearch" in report.tools and "WebFetch" in report.tools


def test_role_connection_check_for_qa_reviewer(sdk_services: Services) -> None:
    project = sdk_services.projects.create(name="SDK 역할", mode=ProjectMode.PROPOSAL)
    report = sdk_services.steps.check_connections(project, "qa_reviewer")
    assert report.status(MCP_PROJECT) == "connected"
    assert "mcp__pwa__verify_deliverable_file" in report.tools


@pytest.mark.slow
def test_external_http_mcp_docs_server_connects(sdk_services: Services) -> None:
    report = sdk_services.runner.test_connection(
        {"claude-code-docs": {"type": "http", "url": "https://code.claude.com/docs/mcp"}},
        timeout_s=120,
    )
    if report.status("claude-code-docs") != "connected":
        pytest.skip(f"외부 문서 MCP 서버에 연결하지 못함 (네트워크?): {report.servers}")
    assert any(t.startswith("mcp__claude-code-docs__") for t in report.tools)
