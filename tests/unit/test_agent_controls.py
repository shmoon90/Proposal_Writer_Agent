"""실행 통제: 도구 정책·훅 출력 형식·오류 분류·재시도·시간 초과·취소·API 키 누락·비밀값 마스킹."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proposal_agent.agents import (
    AgentRequest,
    CancellationToken,
    ClaudeAgentRunner,
    FakeAgentRunner,
    classify_failure,
)
from proposal_agent.agents.control import ToolCallRecorder, ToolPolicy, summarize_tool_input
from proposal_agent.agents.hooks import (
    make_can_use_tool,
    make_post_tool_use_hook,
    make_pre_tool_use_hook,
)
from proposal_agent.config import AgentRunError, ConfigError, Settings


class Out(BaseModel):
    ok: bool = True


# --- 정책 ---------------------------------------------------------------------------------


def test_policy_denies_forbidden_and_unlisted_tools(tmp_path: Path) -> None:
    policy = ToolPolicy(
        allowed_tools=("mcp__pwa__get_project",), allowed_dirs=(tmp_path,), allow_web=False
    )
    assert policy.decide("Bash", {"command": "rm -rf /"})
    assert policy.decide("Write", {"file_path": str(tmp_path / "x")})
    assert policy.decide("WebFetch", {"url": "https://example.com"})  # 웹 비허용 역할
    assert policy.decide("mcp__pwa__get_project", {}) is None
    assert policy.decide("mcp__pwa__list_requirements", {})  # 패턴 밖
    assert policy.decide("SomethingElse", {})


def test_policy_restricts_file_reads_to_allowed_dirs(tmp_path: Path) -> None:
    inside = tmp_path / "ws"
    inside.mkdir()
    policy = ToolPolicy(allowed_tools=(), allowed_dirs=(inside,))
    assert policy.decide("Read", {"file_path": str(inside / "a.txt")}) is None
    assert policy.decide("Read", {"file_path": "a.txt"}) is None  # 상대 경로는 허용 폴더 기준
    assert "허용 폴더 밖" in (
        policy.decide("Read", {"file_path": str(tmp_path / "outside.txt")}) or ""
    )
    assert policy.decide("Read", {"file_path": str(inside / ".." / "outside.txt")})
    assert ToolPolicy(allowed_tools=(), allowed_dirs=()).decide("Read", {"file_path": "x"})


def test_policy_web_rules() -> None:
    policy = ToolPolicy(allowed_tools=("WebSearch", "WebFetch"), allow_web=True)
    assert policy.decide("WebSearch", {"query": "spring boot"}) is None
    assert policy.decide("WebFetch", {"url": "https://docs.spring.io/x"}) is None
    assert policy.decide("WebFetch", {"url": "http://localhost:8501/admin"})
    assert policy.decide("WebFetch", {"url": "http://169.254.169.254/latest/meta-data"})
    assert policy.decide("WebFetch", {"url": "http://10.0.0.5/"})
    assert policy.decide("WebFetch", {"url": "file:///etc/passwd"})


# --- 훅 출력 형식 -------------------------------------------------------------------------------


def test_pre_tool_use_hook_returns_documented_shape() -> None:
    recorder = ToolCallRecorder()
    hook = make_pre_tool_use_hook(ToolPolicy(allowed_tools=("mcp__pwa__get_project",)), recorder)
    deny = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "/etc/x"},
            },
            "t1",
            None,
        )
    )
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert deny["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert deny["hookSpecificOutput"]["permissionDecisionReason"]
    allow = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "mcp__pwa__get_project",
                "tool_input": {},
            },
            "t2",
            None,
        )
    )
    assert allow["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert (
        recorder.records and recorder.records[0].ok is False and recorder.records[0].denied_reason
    )


def test_post_tool_use_hook_records_and_masks_secrets() -> None:
    recorder = ToolCallRecorder()
    hook = make_post_tool_use_hook(recorder)
    out = asyncio.run(
        hook(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "WebFetch",
                "tool_input": {"url": "https://x", "api_key": "sk-secret-123"},
                "tool_response": {"ok": True},
                "duration_ms": 12,
            },
            "t",
            None,
        )
    )
    assert out == {}
    rec = recorder.records[0]
    assert (
        rec.ok
        and rec.duration_ms == 12
        and "sk-secret-123" not in rec.input_summary
        and "api_key=***" in rec.input_summary
    )


def test_can_use_tool_fallback_denies_by_policy() -> None:
    fn = make_can_use_tool(ToolPolicy(allowed_tools=("mcp__pwa__get_project",)))
    denied = asyncio.run(fn("Bash", {"command": "ls"}, None))
    assert denied.behavior == "deny" and denied.message
    allowed = asyncio.run(fn("mcp__pwa__get_project", {}, None))
    assert allowed.behavior == "allow"


def test_summarize_tool_input_masks_and_truncates() -> None:
    s = summarize_tool_input({"authorization": "Bearer abc", "query": "x" * 500})
    assert "Bearer" not in s and "authorization=***" in s and len(s) <= 200


# --- 오류 분류 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subtype", "text", "category"),
    [
        ("success", "Credit balance is too low", "credit"),
        ("success", "Invalid API key provided", "auth"),
        ("success", "429 rate limit exceeded", "rate_limit"),
        ("error_max_budget_usd", "", "budget"),
        ("error_max_turns", "", "turns"),
        ("error_max_structured_output_retries", "", "schema"),
    ],
)
def test_classify_failure_categories(subtype: str, text: str, category: str) -> None:
    cause, resolution, cat = classify_failure(subtype, text, True)
    assert cat == category and resolution


# --- 러너 통제 (SDK 호출 없이 _run_async를 대체) ---------------------------------------------------


def _runner_with(monkeypatch: pytest.MonkeyPatch, behaviours: list[Any]) -> ClaudeAgentRunner:
    runner = ClaudeAgentRunner(Settings(anthropic_api_key="sk-test"))
    calls = iter(behaviours)

    async def fake_run_async(request: AgentRequest, schema: type[BaseModel], api_key: str) -> Any:
        assert api_key == "sk-test"
        b = next(calls)
        if isinstance(b, Exception):
            raise b
        from proposal_agent.agents.runner import AgentResponse

        return AgentResponse(role=request.role, output=schema.model_validate(b))

    monkeypatch.setattr(runner, "_run_async", fake_run_async)
    monkeypatch.setattr("proposal_agent.agents.runner.time.sleep", lambda s: None)
    return runner


def test_missing_api_key_raises_config_error_before_sdk() -> None:
    runner = ClaudeAgentRunner(Settings(anthropic_api_key=None))
    with pytest.raises(ConfigError) as info:
        runner.run_structured(AgentRequest(role="r", system_prompt="s", prompt="p"), Out)
    assert "ANTHROPIC_API_KEY" in info.value.message


def test_transient_error_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_with(
        monkeypatch,
        [AgentRunError("rate", subtype="success", detail={"category": "rate_limit"}), {"ok": True}],
    )
    resp = runner.run_structured(
        AgentRequest(role="r", system_prompt="s", prompt="p", retries=1), Out
    )
    assert resp.attempts == 2 and isinstance(resp.output, Out)


def test_non_transient_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_with(
        monkeypatch,
        [AgentRunError("credit", subtype="success", detail={"category": "credit"}), {"ok": True}],
    )
    with pytest.raises(AgentRunError) as info:
        runner.run_structured(AgentRequest(role="r", system_prompt="s", prompt="p", retries=3), Out)
    assert info.value.detail["attempt"] == 1


def test_retry_limit_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    errs = [
        AgentRunError("x", subtype="process", detail={"category": "connection"}) for _ in range(5)
    ]
    runner = _runner_with(monkeypatch, errs)
    with pytest.raises(AgentRunError) as info:
        runner.run_structured(AgentRequest(role="r", system_prompt="s", prompt="p", retries=2), Out)
    assert info.value.detail["attempt"] == 3


def test_cancelled_token_prevents_run(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_with(monkeypatch, [{"ok": True}])
    token = CancellationToken()
    token.cancel()
    with pytest.raises(AgentRunError) as info:
        runner.run_structured(
            AgentRequest(role="r", system_prompt="s", prompt="p", cancel=token), Out
        )
    assert info.value.subtype == "cancelled"


def test_timeout_error_surfaces_with_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_with(
        monkeypatch,
        [
            AgentRunError(
                "timeout",
                subtype="timeout",
                resolution="timeout_s 조정",
                detail={"category": "timeout"},
            )
        ],
    )
    with pytest.raises(AgentRunError) as info:
        runner.run_structured(
            AgentRequest(role="r", system_prompt="s", prompt="p", timeout_s=1), Out
        )
    assert info.value.subtype == "timeout" and "timeout_s" in info.value.resolution


def test_fake_runner_honours_cancel_and_exceptions() -> None:
    fake = FakeAgentRunner({"r": {"ok": True}, "boom": AgentRunError("boom", subtype="x")})
    assert fake.run_structured(AgentRequest(role="r", system_prompt="", prompt=""), Out).output.ok
    with pytest.raises(AgentRunError):
        fake.run_structured(AgentRequest(role="boom", system_prompt="", prompt=""), Out)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(AgentRunError):
        fake.run_structured(AgentRequest(role="r", system_prompt="", prompt="", cancel=token), Out)


def test_runner_logs_never_contain_api_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runner = _runner_with(
        monkeypatch,
        [AgentRunError("rate", subtype="success", detail={"category": "rate_limit"}), {"ok": True}],
    )
    with caplog.at_level(logging.DEBUG, logger="proposal_agent"):
        runner.run_structured(
            AgentRequest(role="r", system_prompt="s", prompt="p sk-test", retries=1), Out
        )
    assert "sk-test" not in caplog.text


def test_build_options_uses_documented_fields() -> None:
    runner = ClaudeAgentRunner(Settings(anthropic_api_key="sk-test"))
    req = AgentRequest(
        role="r",
        system_prompt="s",
        prompt="p",
        builtin_tools=("WebSearch",),
        allowed_tools=("WebSearch", "mcp__pwa__*"),
        mcp_servers={"pwa": {"type": "sdk", "name": "pwa", "instance": object()}},
        cwd=Path(),
    )
    options = runner._build_options(req, Out, "sk-test", runner.policy_for(req), ToolCallRecorder())
    assert options.tools == ["WebSearch"] and options.allowed_tools == ["WebSearch", "mcp__pwa__*"]
    assert options.permission_mode == "dontAsk" and "Bash" in options.disallowed_tools
    assert (
        options.output_format["type"] == "json_schema"
        and options.env["ANTHROPIC_API_KEY"] == "sk-test"
    )
    assert (
        set(options.hooks) == {"PreToolUse", "PostToolUse", "PostToolUseFailure"}
        and options.can_use_tool is not None
    )
    assert options.setting_sources == [] and options.max_turns == 8
