"""실행 통제 값 객체: 취소 토큰, 도구 호출 기록, 도구 정책.

- ``CancellationToken``: UI 스레드에서 ``cancel()``을 호출하면 러너가 세션을 중단(interrupt)한다.
- ``ToolPolicy``: 역할이 허용한 도구만 통과시키고, 파일 접근은 허용 폴더 안으로 제한하며, 금지 도구는 항상 거부한다.
  PreToolUse 훅과 ``can_use_tool`` 폴백 양쪽에서 같은 정책을 쓴다.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from proposal_agent.config.paths import ensure_within

FORBIDDEN_TOOLS: frozenset[str] = frozenset(
    {
        "Bash",
        "Write",
        "Edit",
        "NotebookEdit",
        "Agent",
        "Task",
        "Skill",
        "KillShell",
        "TodoWrite",
        "TaskCreate",
    }
)
FILE_READ_TOOLS: frozenset[str] = frozenset({"Read", "Glob", "Grep", "LS"})
_PRIVATE_HOSTS = (
    "localhost",
    "127.",
    "0.0.0.0",
    "::1",
    "169.254.",
    "10.",
    "192.168.",
    "metadata.google",
)

_SECRET_MARKERS = ("api_key", "apikey", "token", "secret", "password", "authorization")


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    input_summary: str
    ok: bool
    duration_ms: int = 0
    denied_reason: str | None = None


def summarize_tool_input(tool_input: dict[str, Any], limit: int = 200) -> str:
    """로그·감사용 입력 요약. 비밀값 키는 마스킹하고 길이를 제한한다."""
    parts: list[str] = []
    for k, v in tool_input.items():
        if any(m in k.lower() for m in _SECRET_MARKERS):
            parts.append(f"{k}=***")
            continue
        text = str(v).replace("\n", " ")
        parts.append(f"{k}={text[:80]}")
    return ", ".join(parts)[:limit]


@dataclass
class ToolPolicy:
    """역할별 도구 허용 정책."""

    allowed_tools: tuple[str, ...] = ()
    allowed_dirs: tuple[Path, ...] = ()
    allow_web: bool = False

    def decide(self, tool_name: str, tool_input: dict[str, Any] | None) -> str | None:
        """거부 사유를 돌려준다. None이면 허용."""
        tool_input = tool_input or {}
        if tool_name in FORBIDDEN_TOOLS:
            return f"도구 '{tool_name}'는 정책상 금지입니다."
        if tool_name in FILE_READ_TOOLS:
            if not self.allowed_dirs:
                return "파일 읽기 도구가 허용되지 않았습니다."
            target = (
                tool_input.get("file_path") or tool_input.get("path") or tool_input.get("pattern")
            )
            if not target:
                return None
            return self._check_path(str(target))
        if tool_name in ("WebSearch", "WebFetch"):
            if not self.allow_web or tool_name not in self.allowed_tools:
                return f"도구 '{tool_name}'는 이 역할에 허용되지 않았습니다."
            if tool_name == "WebFetch":
                return self._check_url(str(tool_input.get("url", "")))
            return None
        if tool_name.startswith("mcp__"):
            if any(fnmatch.fnmatch(tool_name, pat) for pat in self.allowed_tools):
                return None
            return f"MCP 도구 '{tool_name}'는 이 역할에 허용되지 않았습니다."
        if tool_name in self.allowed_tools:
            return None
        return f"도구 '{tool_name}'는 허용 목록에 없습니다."

    def _check_path(self, raw: str) -> str | None:
        path = Path(raw)
        for base in self.allowed_dirs:
            try:
                ensure_within(base, path if path.is_absolute() else base / path)
                return None
            except Exception:  # noqa: BLE001 - 다른 허용 폴더를 계속 확인
                continue
        return f"허용 폴더 밖 경로 접근: {raw}"

    @staticmethod
    def _check_url(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return f"허용되지 않는 URL 스킴: {url}"
        host = (parsed.hostname or "").lower()
        if not host or host.startswith(_PRIVATE_HOSTS):
            return f"내부·로컬 주소 접근 금지: {url}"
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return f"내부 IP 접근 금지: {url}"
        except ValueError:
            pass
        return None


@dataclass
class ToolCallRecorder:
    records: list[ToolCallRecord] = field(default_factory=list)

    def add(self, record: ToolCallRecord) -> None:
        self.records.append(record)
