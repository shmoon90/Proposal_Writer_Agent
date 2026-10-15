"""MCP 서버·도구 연결 점검 (실제 Claude Code 프로세스, 모델 호출 없음 → 비용 0).

인프로세스 ``pwa`` 서버, 외부 HTTP MCP(Claude Code 문서 서버), 일부러 깨진 stdio 서버를 함께 연결해
init 메시지의 상태와 노출된 도구 이름을 출력한다. 결과는 workspace/mcp_check.json에 저장된다.

실행: .venv\\Scripts\\python scripts\\check_mcp.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from proposal_agent.agents.roles import MCP_PROJECT, ROLES  # noqa: E402
from proposal_agent.agents.tools import ToolContext, build_project_server  # noqa: E402
from proposal_agent.config import ProjectPaths, load_settings  # noqa: E402
from proposal_agent.models import ProjectMode  # noqa: E402
from proposal_agent.services import AppContext, Services  # noqa: E402

DOCS_SERVER = {"type": "http", "url": "https://code.claude.com/docs/mcp"}


def main() -> int:
    settings = load_settings(ROOT / ".env")
    settings.require_api_key()
    ctx = AppContext.create(
        settings,
        paths=ProjectPaths(Path(tempfile.mkdtemp(prefix="pwa_mcp_"))),
        configure_logging=False,
    )
    services = Services.from_context(ctx)
    project = services.projects.create(name="MCP 점검", mode=ProjectMode.PROPOSAL)
    servers = {
        MCP_PROJECT: build_project_server(ToolContext(ctx.repos, ctx.paths, project)),
        "claude-code-docs": DOCS_SERVER,
        "broken-stdio": {"command": "nonexistent-command-xyz", "args": []},
    }
    report = services.runner.test_connection(servers, ("WebSearch", "WebFetch"), timeout_s=120)
    out = {
        "model": report.model,
        "servers": {
            k: {"status": v.get("status"), "error": v.get("error")}
            for k, v in report.servers.items()
        },
        "tools": report.tools,
        "error": report.error,
        "roles": {
            k: {"builtin": list(r.builtin_tools), "mcp": list(r.mcp_servers)}
            for k, r in ROLES.items()
        },
    }
    (ROOT / "workspace" / "mcp_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if report.status(MCP_PROJECT) == "connected" else 1


if __name__ == "__main__":
    sys.exit(main())
