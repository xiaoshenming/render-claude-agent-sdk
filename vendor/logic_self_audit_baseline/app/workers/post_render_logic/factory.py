"""Factory helpers for post-render logic repair pipelines."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.workers.post_render_logic.claude_adapters import (
    ClaudeLogicReviewer,
    ClaudeSceneCoder,
)
from app.workers.post_render_logic.orchestrator import LogicRepairOrchestrator
from app.workers.post_render_logic.sdk_runner import ClaudeAgentJsonRunner


def build_claude_logic_orchestrator(
    *,
    render_again: Callable[[str], Any],
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int = 1,
    tools: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> LogicRepairOrchestrator:
    """Create a Claude Agent SDK backed post-render logic orchestrator."""
    runner = ClaudeAgentJsonRunner(
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        tools=tools,
        allowed_tools=allowed_tools,
    )
    return LogicRepairOrchestrator(
        reviewer=ClaudeLogicReviewer(runner),
        coder=ClaudeSceneCoder(runner),
        render_again=render_again,
    )
