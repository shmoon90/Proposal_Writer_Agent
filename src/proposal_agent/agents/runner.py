"""Claude Agent SDK 실행 어댑터.

- ``AgentRunner``: 역할별 프롬프트 + Pydantic 스키마 → 검증된 구조화 출력. 유일하게 SDK에 의존하는 모듈.
- ``ClaudeAgentRunner``: ``ClaudeSDKClient`` 사용(interrupt 지원). 역할이 선언한 내장 도구·MCP 서버만 연결하고,
  PreToolUse 훅 + ``can_use_tool`` 폴백으로 도구 정책을 강제한다. 시간 제한·취소 토큰·재시도(일시 오류만)·
  비용·도구 호출 기록을 제공한다. 비밀값은 환경변수로만 전달하고 로그에 남기지 않는다.
- ``FakeAgentRunner``: 테스트용.

확인된 SDK 0.2.167 API 기준: ClaudeAgentOptions(tools, allowed_tools, mcp_servers, hooks, can_use_tool, permission_mode,
output_format, max_turns, max_budget_usd, add_dirs, setting_sources, env), ClaudeSDKClient(query/receive_response/
interrupt/get_mcp_status), ResultMessage(subtype, is_error, result, structured_output, total_cost_usd, num_turns, usage).
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

from proposal_agent.agents.control import (
    CancellationToken,
    ToolCallRecord,
    ToolCallRecorder,
    ToolPolicy,
)
from proposal_agent.agents.hooks import build_hook_config, make_can_use_tool
from proposal_agent.config.errors import AgentRunError, ConfigError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.settings import Settings

log = get_logger("agents.runner")

T = TypeVar("T", bound=BaseModel)

TRANSIENT_CATEGORIES = frozenset({"rate_limit", "overloaded", "connection", "process"})


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
    add_dirs: tuple[Path, ...] = ()
    builtin_tools: tuple[str, ...] = ()
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()
    timeout_s: int = 600
    retries: int = 1
    cancel: CancellationToken | None = None


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
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    attempts: int = 1


@dataclass
class ConnectionReport:
    """MCP·도구 연결 점검 결과 (실제 세션 init 메시지 기준)."""

    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    error: str | None = None

    def status(self, name: str) -> str | None:
        return (self.servers.get(name) or {}).get("status")

    @property
    def all_connected(self) -> bool:
        return bool(self.servers) and all(
            s.get("status") == "connected" for s in self.servers.values()
        )


class AgentRunner(Protocol):
    name: str

    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse: ...

    def test_connection(
        self,
        mcp_servers: dict[str, Any] | None = None,
        builtin_tools: tuple[str, ...] = (),
        *,
        timeout_s: int = 90,
    ) -> ConnectionReport: ...


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


_API_FAILURE_HINTS: tuple[tuple[str, str, str], ...] = (
    ("credit balance", "credit", "Anthropic Console에서 API 크레딧을 충전한 뒤 다시 실행하십시오."),
    ("invalid api key", "auth", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("authentication", "auth", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("not logged in", "auth", ".env의 ANTHROPIC_API_KEY 값을 확인하십시오."),
    ("rate limit", "rate_limit", "잠시 후 다시 실행하거나 호출 간격을 늘리십시오."),
    ("overloaded", "overloaded", "잠시 후 다시 실행하십시오."),
    ("connection", "connection", "네트워크 연결을 확인한 뒤 다시 실행하십시오."),
)


def classify_failure(subtype: str, result_text: str, is_error: bool) -> tuple[str, str, str]:
    """(원인, 조치, 분류). 분류는 재시도 판단에 쓴다 (TRANSIENT_CATEGORIES만 재시도)."""
    lowered = result_text.lower()
    for marker, category, resolution in _API_FAILURE_HINTS:
        if marker in lowered:
            return result_text[:300], resolution, category
    if subtype == "error_max_budget_usd":
        return (
            "단계 예산 초과",
            "역할의 max_budget_usd 또는 PWA_MAX_BUDGET_USD_PER_STEP 값을 올리거나 입력을 줄이십시오.",
            "budget",
        )
    if subtype == "error_max_turns":
        return "턴 상한 초과", "역할의 max_turns 값을 올리거나 입력을 줄이십시오.", "turns"
    if subtype == "error_max_structured_output_retries":
        return (
            "스키마에 맞는 출력을 만들지 못함",
            "입력을 줄이거나(청크 분할) 프롬프트·스키마를 단순화하십시오.",
            "schema",
        )
    if is_error or not result_text:
        return (
            result_text[:300] or "결과 없음",
            "로그를 확인하고 입력을 줄인 뒤 재실행하십시오.",
            "unknown",
        )
    return (
        result_text[:300],
        "구조화 출력이 비어 있습니다. 입력을 줄이거나 예산·턴 상한을 올린 뒤 재실행하십시오.",
        "no_output",
    )


class ClaudeAgentRunner:
    name = "claude-agent-sdk"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- 공개 API ----------------------------------------------------------------------
    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse:
        api_key = self._settings.require_api_key()  # SDK 호출 전에 키 누락을 명확히 알린다
        attempts = max(1, request.retries + 1)
        last_error: AgentRunError | None = None
        for attempt in range(1, attempts + 1):
            if request.cancel and request.cancel.is_cancelled:
                raise AgentRunError(
                    f"에이전트 '{request.role}' 실행이 취소되었습니다.",
                    subtype="cancelled",
                    resolution="필요하면 단계를 다시 실행하십시오.",
                    detail={"category": "cancelled"},
                )
            try:
                response = _run_coroutine_sync(self._run_async(request, schema, api_key))
                response.attempts = attempt
                return response
            except AgentRunError as exc:
                last_error = exc
                exc.detail["attempt"] = attempt
                category = str(exc.detail.get("category", ""))
                if category not in TRANSIENT_CATEGORIES or attempt >= attempts:
                    raise
                wait = min(2.0 * attempt, 10.0)
                log.warning(
                    "agent %s 일시 오류(%s), %.0fs 후 재시도 %d/%d",
                    request.role,
                    category,
                    wait,
                    attempt,
                    attempts - 1,
                )
                time.sleep(wait)
        assert last_error is not None
        raise last_error

    def test_connection(
        self,
        mcp_servers: dict[str, Any] | None = None,
        builtin_tools: tuple[str, ...] = (),
        *,
        timeout_s: int = 90,
    ) -> ConnectionReport:
        """세션을 열어 init 메시지의 MCP 서버 상태·도구 목록을 확인한 뒤 즉시 중단한다 (모델 호출 비용 없음)."""
        api_key = self._settings.require_api_key()
        return _run_coroutine_sync(
            self._test_connection_async(mcp_servers or {}, builtin_tools, api_key, timeout_s)
        )

    # --- 내부 ------------------------------------------------------------------------
    def _build_options(
        self,
        request: AgentRequest,
        schema: type[BaseModel] | None,
        api_key: str,
        policy: ToolPolicy,
        recorder: ToolCallRecorder,
        max_turns: int | None = None,
    ) -> Any:
        import warnings

        from claude_agent_sdk import CanUseToolShadowedWarning, ClaudeAgentOptions

        # allowed_tools 와일드카드가 can_use_tool 폴백을 가리는 것은 의도된 설계다: 모든 호출은 PreToolUse 훅이 정책으로 검사한다.
        warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)
        kwargs: dict[str, Any] = dict(
            system_prompt=request.system_prompt,
            tools=list(request.builtin_tools),
            allowed_tools=list(request.allowed_tools),
            disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit", "Agent", "Skill"],
            mcp_servers=dict(request.mcp_servers),
            permission_mode="dontAsk",
            hooks=build_hook_config(policy, recorder),
            can_use_tool=make_can_use_tool(policy),
            max_turns=max_turns or request.max_turns,
            max_budget_usd=request.max_budget_usd,
            model=request.model or self._settings.model_primary,
            effort=request.effort,
            cwd=str(request.cwd) if request.cwd else None,
            add_dirs=[str(d) for d in request.add_dirs],
            setting_sources=[],
            env={
                "ANTHROPIC_API_KEY": api_key,
                "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "0",
                "MCP_TIMEOUT": "30000",
                "MCP_TOOL_TIMEOUT": "120000",
            },
        )
        if schema is not None:
            kwargs["output_format"] = {"type": "json_schema", "schema": schema.model_json_schema()}
        return ClaudeAgentOptions(**kwargs)

    @staticmethod
    def policy_for(request: AgentRequest) -> ToolPolicy:
        dirs = tuple(d for d in (request.cwd, *request.add_dirs) if d is not None)
        return ToolPolicy(
            allowed_tools=request.allowed_tools,
            allowed_dirs=dirs,
            allow_web=any(t in ("WebSearch", "WebFetch") for t in request.builtin_tools),
        )

    async def _run_async(
        self, request: AgentRequest, schema: type[T], api_key: str
    ) -> AgentResponse:
        try:
            from claude_agent_sdk import ClaudeSDKClient, ResultMessage, SystemMessage
        except ImportError as exc:  # pragma: no cover
            raise ConfigError(
                "claude-agent-sdk가 설치되지 않았습니다.",
                cause=str(exc),
                resolution="pip install claude-agent-sdk",
            ) from exc

        policy = self.policy_for(request)
        recorder = ToolCallRecorder()
        options = self._build_options(request, schema, api_key, policy, recorder)
        started = time.monotonic()
        result: Any = None
        init_servers: list[dict[str, Any]] = []
        interrupted_for: str | None = None

        async def consume(client: Any) -> None:
            nonlocal result, init_servers
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    init_servers = list(message.data.get("mcp_servers", []))
                    bad = [s for s in init_servers if s.get("status") in ("failed", "needs-auth")]
                    if bad:
                        log.warning(
                            "MCP 서버 연결 실패: %s",
                            [(s.get("name"), s.get("status")) for s in bad],
                        )
                elif isinstance(message, ResultMessage):
                    result = message

        async def watchdog(client: Any) -> None:
            nonlocal interrupted_for
            while True:
                await asyncio.sleep(0.5)
                if request.cancel and request.cancel.is_cancelled:
                    interrupted_for = "cancelled"
                elif time.monotonic() - started > request.timeout_s:
                    interrupted_for = "timeout"
                if interrupted_for:
                    try:
                        await client.interrupt()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("interrupt 실패: %s", exc)
                    return

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(request.prompt)
                consumer = asyncio.create_task(consume(client))
                watcher = asyncio.create_task(watchdog(client))
                try:
                    await consumer
                finally:
                    watcher.cancel()
        except AgentRunError:
            raise
        except Exception as exc:
            if result is None and interrupted_for is None:
                raise self._map_sdk_exception(request, exc) from exc

        duration = int((time.monotonic() - started) * 1000)
        if interrupted_for == "timeout":
            raise AgentRunError(
                f"에이전트 '{request.role}' 시간 제한 초과 ({request.timeout_s}s).",
                subtype="timeout",
                resolution="입력을 줄이거나 역할의 timeout_s를 올리십시오.",
                detail={"category": "timeout", "tool_calls": len(recorder.records)},
            )
        if interrupted_for == "cancelled":
            raise AgentRunError(
                f"에이전트 '{request.role}' 실행이 취소되었습니다.",
                subtype="cancelled",
                resolution="필요하면 단계를 다시 실행하십시오.",
                detail={"category": "cancelled"},
            )
        if result is None:
            raise AgentRunError(
                f"에이전트 '{request.role}'가 결과를 반환하지 않았습니다.",
                subtype="no_result",
                detail={"category": "unknown"},
            )

        cost = float(getattr(result, "total_cost_usd", 0.0) or 0.0)
        turns = int(getattr(result, "num_turns", 0) or 0)
        subtype = str(getattr(result, "subtype", ""))
        structured = getattr(result, "structured_output", None)
        result_text = str(getattr(result, "result", "") or "")
        is_error = bool(getattr(result, "is_error", False))
        failed_servers = [
            str(s.get("name")) for s in init_servers if s.get("status") in ("failed", "needs-auth")
        ]
        if subtype != "success" or is_error or not structured:
            cause, resolution, category = classify_failure(subtype, result_text, is_error)
            if failed_servers:
                cause = f"{cause} (MCP 서버 연결 실패: {', '.join(failed_servers)})"
            raise AgentRunError(
                f"에이전트 '{request.role}' 실행 실패 ({subtype or 'unknown'})",
                subtype=subtype or "no_structured_output",
                cause=cause,
                resolution=resolution,
                detail={
                    "cost_usd": cost,
                    "num_turns": turns,
                    "is_error": is_error,
                    "category": category,
                    "failed_mcp_servers": failed_servers,
                    "tool_calls": len(recorder.records),
                },
            )
        try:
            output = schema.model_validate(structured)
        except PydanticValidationError as exc:
            raise AgentRunError(
                f"에이전트 '{request.role}' 출력이 스키마와 맞지 않습니다.",
                subtype="schema_mismatch",
                cause=str(exc)[:500],
                detail={"cost_usd": cost, "num_turns": turns, "category": "schema"},
            ) from exc
        log.info(
            "agent %s ok cost=%.4f turns=%d tools=%d %dms",
            request.role,
            cost,
            turns,
            len(recorder.records),
            duration,
        )
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
            tool_calls=list(recorder.records),
        )

    async def _test_connection_async(
        self,
        mcp_servers: dict[str, Any],
        builtin_tools: tuple[str, ...],
        api_key: str,
        timeout_s: int,
    ) -> ConnectionReport:
        from claude_agent_sdk import ClaudeSDKClient, ResultMessage, SystemMessage

        report = ConnectionReport()
        request = AgentRequest(
            role="connection_test",
            system_prompt="connection test",
            prompt="Reply with OK.",
            max_turns=1,
            max_budget_usd=0.05,
            builtin_tools=builtin_tools,
            mcp_servers=mcp_servers,
            allowed_tools=tuple(f"mcp__{name}__*" for name in mcp_servers),
        )
        options = self._build_options(
            request, None, api_key, self.policy_for(request), ToolCallRecorder(), max_turns=1
        )

        async def run() -> None:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(request.prompt)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        for s in message.data.get("mcp_servers", []):
                            report.servers[str(s.get("name"))] = dict(s)
                        report.tools = list(message.data.get("tools", []))
                        report.model = message.data.get("model")
                        try:
                            await client.interrupt()  # 모델 호출 전에 중단 (비용 0)
                        except Exception as exc:  # noqa: BLE001
                            log.debug("interrupt 실패: %s", exc)
                    elif isinstance(message, ResultMessage) and message.is_error and message.result:
                        report.error = str(message.result)[:200]
                try:
                    status = await client.get_mcp_status()
                    for s in status.get("mcpServers", []):
                        name = str(s.get("name"))
                        report.servers.setdefault(name, {})
                        report.servers[name].update(
                            {k: v for k, v in s.items() if k in ("status", "error", "tools")}
                        )
                except Exception as exc:  # noqa: BLE001
                    log.debug("get_mcp_status 실패: %s", exc)

        try:
            await asyncio.wait_for(run(), timeout=timeout_s)
        except TimeoutError:
            report.error = f"연결 점검 시간 초과 ({timeout_s}s)"
        except Exception as exc:  # noqa: BLE001 - 결과 오류(크레딧 등)가 와도 init 정보는 유효
            if not report.servers:
                report.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            elif report.error is None:
                report.error = str(exc)[:200]
        return report

    @staticmethod
    def _map_sdk_exception(request: AgentRequest, exc: Exception) -> AgentRunError:
        name = type(exc).__name__
        text = str(exc)
        if name == "CLINotFoundError":
            return AgentRunError(
                "Claude Code 실행 파일을 찾을 수 없습니다.",
                subtype="cli_not_found",
                cause=text[:300],
                resolution="claude-agent-sdk를 재설치하거나 PWA_CLI_PATH로 경로를 지정하십시오.",
                detail={"category": "cli"},
            )
        cause, resolution, category = classify_failure("", text, True)
        if name in ("CLIConnectionError", "ProcessError"):
            return AgentRunError(
                f"에이전트 '{request.role}' 프로세스 오류",
                subtype="process",
                cause=cause or text[:300],
                resolution=resolution
                if category != "unknown"
                else "로그(stderr)를 확인하고 다시 실행하십시오.",
                detail={"category": category if category != "unknown" else "process"},
            )
        return AgentRunError(
            f"에이전트 '{request.role}' 실행 실패",
            subtype="exception",
            cause=cause or f"{name}: {text[:300]}",
            resolution=resolution,
            detail={"category": category},
        )


Responder = Callable[[AgentRequest], BaseModel | dict[str, Any]]


class FakeAgentRunner:
    """테스트용. ``responders[role]``는 고정 값(dict/BaseModel), 예외, 또는 요청을 받는 콜백."""

    name = "fake"

    def __init__(
        self, responders: dict[str, Any] | None = None, *, cost_per_call: float = 0.01
    ) -> None:
        self.responders: dict[str, Any] = dict(responders or {})
        self.calls: list[AgentRequest] = []
        self.cost_per_call = cost_per_call

    def run_structured(self, request: AgentRequest, schema: type[T]) -> AgentResponse:
        self.calls.append(request)
        if request.cancel and request.cancel.is_cancelled:
            raise AgentRunError(
                f"에이전트 '{request.role}' 실행이 취소되었습니다.",
                subtype="cancelled",
                detail={"category": "cancelled"},
            )
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

    def test_connection(
        self,
        mcp_servers: dict[str, Any] | None = None,
        builtin_tools: tuple[str, ...] = (),
        *,
        timeout_s: int = 90,
    ) -> ConnectionReport:
        return ConnectionReport(
            servers={n: {"status": "connected"} for n in (mcp_servers or {})},
            tools=list(builtin_tools),
        )


def build_runner(settings: Settings) -> AgentRunner:
    return ClaudeAgentRunner(settings)
