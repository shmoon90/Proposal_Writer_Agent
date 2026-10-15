"""Agent SDK 훅: PreToolUse(정책 거부), PostToolUse(호출 기록), can_use_tool 폴백.

반환 형식은 공식 문서(hooks)의 ``hookSpecificOutput`` 규격을 따른다:
``{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}``
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from proposal_agent.agents.control import (
    ToolCallRecord,
    ToolCallRecorder,
    ToolPolicy,
    summarize_tool_input,
)
from proposal_agent.config.logging import get_logger

log = get_logger("agents.hooks")

HookFn = Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]


def make_pre_tool_use_hook(policy: ToolPolicy, recorder: ToolCallRecorder) -> HookFn:
    async def pre_tool_use(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        tool_name = str(input_data.get("tool_name", ""))
        tool_input = input_data.get("tool_input") or {}
        reason = policy.decide(tool_name, tool_input)
        if reason:
            log.warning("tool denied %s: %s", tool_name, reason)
            recorder.add(
                ToolCallRecord(
                    tool_name, summarize_tool_input(tool_input), ok=False, denied_reason=reason
                )
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "역할 정책 허용",
            }
        }

    return pre_tool_use


def make_post_tool_use_hook(recorder: ToolCallRecorder) -> HookFn:
    async def post_tool_use(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        tool_name = str(input_data.get("tool_name", ""))
        tool_input = input_data.get("tool_input") or {}
        response = input_data.get("tool_response")
        ok = True
        if isinstance(response, dict) and response.get("is_error"):
            ok = False
        recorder.add(
            ToolCallRecord(
                tool_name,
                summarize_tool_input(tool_input),
                ok=ok,
                duration_ms=int(input_data.get("duration_ms") or 0),
            )
        )
        log.info("tool %s ok=%s %s", tool_name, ok, summarize_tool_input(tool_input, 120))
        return {}

    return post_tool_use


def make_post_tool_failure_hook(recorder: ToolCallRecorder) -> HookFn:
    async def post_failure(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        tool_name = str(input_data.get("tool_name", ""))
        recorder.add(
            ToolCallRecord(
                tool_name,
                summarize_tool_input(input_data.get("tool_input") or {}),
                ok=False,
                denied_reason=str(input_data.get("error", "tool failure"))[:200],
            )
        )
        return {}

    return post_failure


def make_can_use_tool(policy: ToolPolicy) -> Callable[..., Awaitable[Any]]:
    """권한 프롬프트까지 내려온 호출은 정책으로 판단하고, 그 밖은 모두 거부한다 (사람 프롬프트 없음)."""

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any) -> Any:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        reason = policy.decide(tool_name, input_data)
        if reason:
            return PermissionResultDeny(message=reason)
        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool


def build_hook_config(policy: ToolPolicy, recorder: ToolCallRecorder) -> dict[str, list[Any]]:
    from claude_agent_sdk import HookMatcher

    return {
        "PreToolUse": [
            HookMatcher(hooks=[cast(Any, make_pre_tool_use_hook(policy, recorder))], timeout=30)
        ],
        "PostToolUse": [
            HookMatcher(hooks=[cast(Any, make_post_tool_use_hook(recorder))], timeout=30)
        ],
        "PostToolUseFailure": [
            HookMatcher(hooks=[cast(Any, make_post_tool_failure_hook(recorder))], timeout=30)
        ],
    }


__all__ = [
    "build_hook_config",
    "make_can_use_tool",
    "make_post_tool_use_hook",
    "make_pre_tool_use_hook",
    "time",
]
