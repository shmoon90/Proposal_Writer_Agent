"""에이전트 역할 정의: 9역할, 프롬프트 존재, 스키마 유효, 도구 최소 권한."""

from __future__ import annotations

import pytest

from proposal_agent.agents import PROMPTS_DIR, load_prompt
from proposal_agent.agents.control import FORBIDDEN_TOOLS
from proposal_agent.agents.roles import (
    BUILTIN_TOOL_CATALOG,
    MCP_PROJECT,
    ROLES,
    AgentRole,
    get_role,
)
from proposal_agent.agents.tools import TOOL_NAMES

EXPECTED_ROLES = {
    "rfp_analyst",
    "requirement_extractor",
    "requirement_verifier",
    "tech_researcher",
    "architect",
    "planner",
    "proposal_writer",
    "document_generator",
    "qa_reviewer",
    "semantic_differ",  # Phase 6: 구축 단계 변경 요청 의미 비교
    "approach_writer",  # Phase 14: 요구사항별 구현 방안·난이도·검사 기준
}


def test_all_roles_defined_with_prompts_and_schemas() -> None:
    assert set(ROLES) == EXPECTED_ROLES
    for role in ROLES.values():
        assert (PROMPTS_DIR / f"{role.prompt_name}.md").exists(), role.key
        text = load_prompt(role.prompt_name)
        assert "JSON" in text and ("지시" in text or "지시문" in text)  # 출력 형식·인젝션 방어 문구
        schema = role.output_schema.model_json_schema()
        assert schema["type"] == "object" and "$schema" not in schema
        assert role.max_turns > 0 and role.max_budget_usd > 0 and role.timeout_s > 0


def test_no_role_has_write_or_shell_tools() -> None:
    for role in ROLES.values():
        assert not set(role.builtin_tools) & set(FORBIDDEN_TOOLS), role.key
        assert set(role.builtin_tools) <= BUILTIN_TOOL_CATALOG, role.key
        for pat in role.mcp_tool_patterns:
            assert pat.startswith("mcp__") and pat.split("__")[1] in role.mcp_servers


def test_only_researcher_has_web_tools() -> None:
    web = {
        k
        for k, r in ROLES.items()
        if "WebSearch" in r.builtin_tools or "WebFetch" in r.builtin_tools
    }
    assert web == {"tech_researcher", "approach_writer"}  # 조사·구현 방안 역할만 웹 검색


def test_mcp_tool_patterns_exist_on_project_server() -> None:
    for role in ROLES.values():
        for pat in role.mcp_tool_patterns:
            if pat.startswith(f"mcp__{MCP_PROJECT}__"):
                assert pat in TOOL_NAMES, (role.key, pat)


def test_role_validation_rejects_bad_tools() -> None:
    with pytest.raises(ValueError):
        AgentRole(
            key="x",
            title="x",
            description="",
            inputs=(),
            output_schema=ROLES["architect"].output_schema,
            prompt_name="architect",
            builtin_tools=("Bash",),
        ).validate()
    with pytest.raises(ValueError):
        AgentRole(
            key="x",
            title="x",
            description="",
            inputs=(),
            output_schema=ROLES["architect"].output_schema,
            prompt_name="architect",
            mcp_tool_patterns=("mcp__other__t",),
        ).validate()
    with pytest.raises(KeyError):
        get_role("nope")


def test_roles_declare_reuse_chain() -> None:
    assert "rfp_analyst" in ROLES["tech_researcher"].reuses
    assert {"tech_researcher", "rfp_analyst"} <= set(ROLES["architect"].reuses)
    assert "architect" in ROLES["planner"].reuses
    assert {"rfp_analyst", "tech_researcher", "architect", "planner"} <= set(
        ROLES["proposal_writer"].reuses
    )
