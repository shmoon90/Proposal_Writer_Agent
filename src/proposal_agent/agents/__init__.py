"""에이전트 실행 및 역할 정의 (Claude Agent SDK)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from proposal_agent.agents.control import CancellationToken, ToolCallRecord, ToolPolicy
from proposal_agent.agents.runner import (
    AgentRequest,
    AgentResponse,
    AgentRunner,
    ClaudeAgentRunner,
    ConnectionReport,
    FakeAgentRunner,
    build_runner,
    classify_failure,
)
from proposal_agent.agents.schemas import RequirementExtraction

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일 없음: {path}")
    return path.read_text(encoding="utf-8")


__all__ = [
    "PROMPTS_DIR",
    "AgentRequest",
    "AgentResponse",
    "AgentRunner",
    "CancellationToken",
    "ClaudeAgentRunner",
    "ConnectionReport",
    "FakeAgentRunner",
    "RequirementExtraction",
    "ToolCallRecord",
    "ToolPolicy",
    "build_runner",
    "classify_failure",
    "load_prompt",
]
