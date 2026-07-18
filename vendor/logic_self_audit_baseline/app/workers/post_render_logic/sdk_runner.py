"""Claude Agent SDK JSON runner for post-render logic tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any


class ClaudeAgentJsonRunner:
    """Run one stateless Claude Agent SDK request and return JSON.

    Tests can inject ``query_func`` to avoid requiring network, CLI auth, or a
    live Claude session. Production uses ``claude_agent_sdk.query`` lazily.
    """

    def __init__(
        self,
        *,
        query_func: Callable[..., AsyncIterator[Any]] | None = None,
        cwd: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
        tools: list[str] | None = None,
        allowed_tools: list[str] | None = None,
    ) -> None:
        self._query_func = query_func
        self.cwd = cwd
        self.model = model
        self.max_turns = max_turns
        self.tools = [] if tools is None else list(tools)
        self.allowed_tools = [] if allowed_tools is None else list(allowed_tools)

    async def run_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str,
    ) -> dict[str, Any]:
        query_func, options = self._build_query(schema, system_prompt)
        last_text = ""

        async for message in query_func(prompt=prompt, options=options):
            structured = getattr(message, "structured_output", None)
            if isinstance(structured, dict):
                return structured

            result_text = getattr(message, "result", None)
            if isinstance(result_text, str) and result_text.strip():
                last_text = result_text

            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    last_text = text

        if not last_text:
            raise ValueError("Claude Agent SDK returned no JSON content")
        return _parse_json_object(last_text)

    def _build_query(self, schema: dict[str, Any], system_prompt: str):
        if self._query_func is not None:
            from claude_agent_sdk import ClaudeAgentOptions

            options = ClaudeAgentOptions(
                tools=self.tools,
                allowed_tools=self.allowed_tools,
                cwd=self.cwd,
                model=self.model,
                max_turns=self.max_turns,
                permission_mode="dontAsk",
                system_prompt=system_prompt,
                output_format={"type": "json_schema", "schema": schema},
            )
            return self._query_func, options

        from claude_agent_sdk import ClaudeAgentOptions, query

        options = ClaudeAgentOptions(
            tools=self.tools,
            allowed_tools=self.allowed_tools,
            cwd=self.cwd,
            model=self.model,
            max_turns=self.max_turns,
            permission_mode="dontAsk",
            system_prompt=system_prompt,
            output_format={"type": "json_schema", "schema": schema},
        )
        return query, options


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Claude Agent SDK JSON output must be an object")
    return data
