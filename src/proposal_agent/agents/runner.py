"""Claude Agent SDK 실행 어댑터.

- ``AgentRunner``: 역할별 프롬프트 + Pydantic 스키마 → 검증된 구조화 출력. 유일하게 SDK에 의존하는 모듈.
- ``ClaudeAgentRunner``: ``claude_agent_sdk.query()`` 사용. 도구 없음(``tools=[]``), 권한 프롬프트 없음(``dontAsk``),
  예산·턴 상한, 구조화 출력(``output_format``). 입력 문서는 프롬프트 안의 데이터 블록으로 전달한다.
- ``FakeAgentRunner``: 테스트용. 역할별 고정 응답 또는 콜백.

확인된 SDK 0.2.16x API 기준 (docs/PROJECT_OVERVIEW.md 4절).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from proposal_agent.config.errors import AgentRunError, ConfigError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.settings import Settings

log = get_logger("agents.runner")

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AgentRequest:
    role: str
    system_prompt: str
    prompt: str
    max_turns: int = 8
    max_budget_usd: float = 2.0
    model: str | None = None
    effort: str | None = None
    cwd: Path | None = None


@dataclass
class AgentResponse:
    role: str
    output: BaseModel
    cost_usd: float = 0.0
    num_turns: int = 0
    duration_ms: int = 0
    session_id: str | None = None
    subtype: str = "success"
    usage: dict[str, Any] = field(default_factory=dict)


class AgentRunner(Protocol):
    name: str

    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse: ...


def _run_coroutine_sync(coro: Any) -> Any:
    """Streamlit 등 이미 이벤트 루프가 있는 스레드에서도 안전하게 코루틴을 실행한다."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=target, name="pwa-agent-runner", daemon=True)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


class ClaudeAgentRunner:
    name = "claude-agent-sdk"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse:
        return _run_coroutine_sync(self._run_async(request, schema))

    async def _run_async(self, request: AgentRequest, schema: type[T]) -> AgentResponse:
        api_key = self._settings.require_api_key()
        try:
            from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
        except ImportError as exc:  # pragma: no cover
            raise ConfigError(
                "claude-agent-sdk가 설치되지 않았습니다.",
                cause=str(exc),
                resolution="pip install claude-agent-sdk",
            ) from exc

        options = ClaudeAgentOptions(
            system_prompt=request.system_prompt,
            tools=[],
            allowed_tools=[],
            disallowed_tools=[
                "Bash",
                "Write",
                "Edit",
                "NotebookEdit",
                "WebSearch",
                "WebFetch",
                "Agent",
            ],
            permission_mode="dontAsk",
            output_format={"type": "json_schema", "schema": schema.model_json_schema()},
            max_turns=request.max_turns,
            max_budget_usd=request.max_budget_usd,
            model=request.model or self._settings.model_primary,
            effort=request.effort,  # type: ignore[arg-type]
            cwd=str(request.cwd) if request.cwd else None,
            setting_sources=[],
            env={"ANTHROPIC_API_KEY": api_key, "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "0"},
        )
        started = time.monotonic()
        result: Any = None
        try:
            async for message in query(prompt=request.prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message
        except Exception as exc:
            if result is None:
                raise AgentRunError(
                    f"에이전트 '{request.role}' 실행 실패",
                    subtype="exception",
                    cause=f"{type(exc).__name__}: {exc}",
                    resolution="API 키·네트워크·예산 설정을 확인하고 다시 시도하십시오.",
                ) from exc
        duration = int((time.monotonic() - started) * 1000)
        if result is None:
            raise AgentRunError(
                f"에이전트 '{request.role}'가 결과를 반환하지 않았습니다.", subtype="no_result"
            )

        cost = float(getattr(result, "total_cost_usd", 0.0) or 0.0)
        turns = int(getattr(result, "num_turns", 0) or 0)
        subtype = str(getattr(result, "subtype", ""))
        structured = getattr(result, "structured_output", None)
        result_text = str(getattr(result, "result", "") or "")
        is_error = bool(getattr(result, "is_error", False))
        if subtype != "success" or is_error or not structured:
            cause, resolution = _classify_failure(subtype, result_text, is_error)
            raise AgentRunError(
                f"에이전트 '{request.role}' 실행 실패 ({subtype or 'unknown'})",
                subtype=subtype or "no_structured_output",
                cause=cause,
                resolution=resolution,
                detail={"cost_usd": cost, "num_turns": turns, "is_error": is_error},
            )
        try:
            output = schema.model_validate(structured)
        except PydanticValidationError as exc:
            raise AgentRunError(
                f"에이전트 '{request.role}' 출력이 스키마와 맞지 않습니다.",
                subtype="schema_mismatch",
                cause=str(exc)[:500],
                detail={"cost_usd": cost, "num_turns": turns},
            ) from exc
        log.info("agent %s ok cost=%.4f turns=%d %dms", request.role, cost, turns, duration)
        usage = getattr(result, "usage", None)
        return AgentResponse(
            role=request.role,
            output=output,
            cost_usd=cost,
            num_turns=turns,
            duration_ms=duration,
            session_id=getattr(result, "session_id", None),
            subtype=subtype,
            usage=dict(usage) if isinstance(usage, dict) else {},
        )


_API_FAILURE_HINTS: tuple[tuple[str, str], ...] = (
    ("credit balance", "Anthropic Console에서 API 크레딧을 충전한 뒤 다시 실행하십시오."),
    ("invalid api key", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("authentication", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("not logged in", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("rate limit", "잠시 후 다시 실행하거나 호출 간격을 늘리십시오."),
    ("overloaded", "잠시 후 다시 실행하십시오."),
)


def _classify_failure(subtype: str, result_text: str, is_error: bool) -> tuple[str, str]:
    """ResultMessage의 오류 문구를 사용자 조치로 변환한다."""
    lowered = result_text.lower()
    for marker, resolution in _API_FAILURE_HINTS:
        if marker in lowered:
            return result_text[:300], resolution
    if subtype == "error_max_budget_usd":
        return "단계 예산 초과", "PWA_MAX_BUDGET_USD_PER_STEP 값을 올리거나 입력을 줄이십시오."
    if subtype == "error_max_turns":
        return "턴 상한 초과", "PWA_MAX_TURNS_DEFAULT 값을 올리거나 입력을 줄이십시오."
    if subtype == "error_max_structured_output_retries":
        return (
            "스키마에 맞는 출력을 만들지 못함",
            "입력을 줄이거나(청크 분할) 프롬프트·스키마를 단순화하십시오.",
        )
    if is_error or not result_text:
        return result_text[:300] or "결과 없음", "로그를 확인하고 입력을 줄인 뒤 재실행하십시오."
    return result_text[
        :300
    ], "구조화 출력이 비어 있습니다. 입력을 줄이거나 예산·턴 상한을 올린 뒤 재실행하십시오."


Responder = Callable[[AgentRequest], BaseModel | dict[str, Any]]


class FakeAgentRunner:
    """테스트용. ``responders[role]``는 고정 값(dict/BaseModel) 또는 요청을 받는 콜백."""

    name = "fake"

    def __init__(
        self, responders: dict[str, Any] | None = None, *, cost_per_call: float = 0.01
    ) -> None:
        self.responders: dict[str, Any] = dict(responders or {})
        self.calls: list[AgentRequest] = []
        self.cost_per_call = cost_per_call

    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse:
        self.calls.append(request)
        responder = self.responders.get(request.role)
        if responder is None:
            raise AgentRunError(
                f"FakeAgentRunner: 역할 '{request.role}' 응답 없음", subtype="no_responder"
            )
        value = responder(request) if callable(responder) else responder
        if isinstance(value, Exception):
            raise value
        output = value if isinstance(value, BaseModel) else schema.model_validate(value)
        return AgentResponse(
            role=request.role,
            output=output,
            cost_usd=self.cost_per_call,
            num_turns=1,
            duration_ms=1,
        )


def build_runner(settings: Settings) -> AgentRunner:
    return ClaudeAgentRunner(settings)
