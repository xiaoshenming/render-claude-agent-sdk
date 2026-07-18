"""Read-only SDK reviewer for the pre-archive quality-platform bridge."""

from __future__ import annotations

import json
from typing import Any

import anyio

from app.core.config import settings

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["pass", "record_only", "needs_repair", "human_review"],
        },
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene": {"type": "string"},
                    "issue": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["scene", "issue", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decision", "summary", "issues"],
    "additionalProperties": False,
}


def run_sdk_logic_review(
    *, code: str, problem_text: str, expected_solution: str
) -> dict[str, Any] | None:
    """Return a read-only structured review, or None when not configured."""
    base_url = settings.MANIM_QUALITY_ANTHROPIC_BASE_URL.strip()
    api_key = settings.MANIM_QUALITY_ANTHROPIC_API_KEY.strip()
    if not base_url or not api_key:
        return None
    return anyio.run(
        _review,
        code,
        problem_text,
        expected_solution,
        base_url,
        api_key,
    )


async def _review(
    code: str,
    problem_text: str,
    expected_solution: str,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    prompt = _prompt(code, problem_text, expected_solution)
    options = ClaudeAgentOptions(
        model=settings.MANIM_QUALITY_MODEL,
        max_turns=1,
        tools=[],
        allowed_tools=[],
        permission_mode="dontAsk",
        setting_sources=[],
        env={
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_API_KEY": api_key,
            "ANTHROPIC_AUTH_TOKEN": api_key,
        },
        output_format={"type": "json_schema", "schema": _SCHEMA},
    )
    result = None
    with anyio.fail_after(settings.MANIM_QUALITY_REVIEW_TIMEOUT_SEC):
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result = message
    if result is None or result.is_error:
        raise RuntimeError("quality reviewer returned no successful result")
    if not isinstance(result.structured_output, dict):
        raise RuntimeError("quality reviewer returned no structured output")
    return result.structured_output


def _prompt(code: str, problem_text: str, expected_solution: str) -> str:
    payload = json.dumps(
        {
            "problem_text": problem_text,
            "expected_solution": expected_solution,
            "candidate_code": code,
        },
        ensure_ascii=False,
    )
    return (
        "你是只读 Manim 数学逻辑 Reviewer。检查题意、数学逻辑、场景叙述和代码是否一致。"
        "只报告有源码证据的问题，不修改代码、不调用工具。record_only 表示非阻断建议；"
        "needs_repair 表示明确且可修复的问题；证据不足时用 human_review。输入 JSON：\n"
        + payload
    )
