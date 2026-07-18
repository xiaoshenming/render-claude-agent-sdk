"""Stateless Claude Agent SDK backend with mandatory Runtime hooks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from manim_quality.contracts._json_values import thaw_json_object

from ._claude_hooks import ClaudeHookState, ClaudeSdkProtocolError, token_usage
from ._runtime_models import BackendRequest, BackendResult
from .runtime import AgentBackend, RuntimeControls
from .usage import TokenUsage

_DENIED_TOOLS = (
    "Agent",
    "Bash",
    "NotebookEdit",
    "Skill",
    "Task",
    "WebFetch",
    "WebSearch",
    "Write",
)

QueryFunction = Callable[..., AsyncIterator[object]]


class ClaudeSdkRunError(RuntimeError):
    pass


class ClaudeSdkBackend(AgentBackend):
    def __init__(
        self,
        *,
        query_func: QueryFunction = query,
        provider_env: Mapping[str, str] | None = None,
    ) -> None:
        if not callable(query_func):
            raise TypeError("query_func must be callable")
        self._query = query_func
        self._provider_env = dict(provider_env or {})

    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        return anyio.run(self._run_async, request, controls)

    async def _run_async(
        self, request: BackendRequest, controls: RuntimeControls
    ) -> BackendResult:
        state = ClaudeHookState(controls, request)
        options = _options(request, state, self._provider_env)
        result: ResultMessage | None = None
        try:
            with anyio.fail_after(request.timeout_ms / 1_000):
                async for message in self._query(
                    prompt=request.prompt, options=options
                ):
                    if isinstance(message, AssistantMessage):
                        await state.record_assistant(message)
                    elif isinstance(message, ResultMessage):
                        result = message
                    state.raise_failure()
        finally:
            controls.record_observed_model_rounds(state.turns)
        state.raise_failure()
        if result is None:
            raise ClaudeSdkProtocolError("Claude Agent SDK returned no ResultMessage")
        controls.record_reported_turns(result.num_turns)
        aggregate_usage = _validate_result(result, state)
        controls.reconcile_usage(aggregate_usage)
        if not isinstance(result.structured_output, Mapping):
            raise ClaudeSdkProtocolError("SDK result has no structured output object")
        return controls.complete(result.structured_output)


def _options(
    request: BackendRequest,
    state: ClaudeHookState,
    provider_env: Mapping[str, str],
) -> ClaudeAgentOptions:
    tools = list(request.allowed_tools)
    read_tool_names = [item.sdk_name for item in request.read_tools]
    hooks = {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[state.pre_tool])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[state.post_tool])],
        "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[state.failed_tool])],
    }
    return ClaudeAgentOptions(
        tools=tools,
        allowed_tools=tools + read_tool_names,
        disallowed_tools=[tool for tool in _DENIED_TOOLS if tool not in tools],
        permission_mode="dontAsk",
        cwd=request.workspace,
        model=request.profile.model,
        max_turns=request.max_turns,
        output_format={
            "type": "json_schema",
            "schema": thaw_json_object(request.output_schema),
        },
        hooks=hooks,
        setting_sources=[],
        skills=[],
        mcp_servers=_mcp_servers(request, state),
        strict_mcp_config=True,
        plugins=[],
        agents=None,
        continue_conversation=False,
        env=dict(provider_env),
    )


def _mcp_servers(
    request: BackendRequest, state: ClaudeHookState
) -> Mapping[str, object]:
    grouped: dict[str, list[object]] = {}
    for grant in request.read_tools:
        grouped.setdefault(grant.server_name, []).append(_sdk_tool(grant, state))
    return {
        name: create_sdk_mcp_server(name=name, tools=tools)
        for name, tools in grouped.items()
    }


def _sdk_tool(grant, state: ClaudeHookState):
    @tool(
        grant.name,
        grant.description,
        thaw_json_object(grant.input_schema),
    )
    async def invoke(arguments):
        text = await state.execute_read_tool(grant.sdk_name, arguments)
        return {"content": [{"type": "text", "text": text}]}

    return invoke


def _validate_result(result: ResultMessage, state: ClaudeHookState) -> TokenUsage:
    if result.is_error:
        details = "; ".join(result.errors or []) or result.subtype
        raise ClaudeSdkRunError(f"Claude Agent SDK failed: {details}")
    minimum = state.sdk_turn_floor
    if result.num_turns < minimum:
        counts = (
            f"result={result.num_turns}, model_rounds={state.turns}, "
            f"minimum_sdk_turns={minimum}"
        )
        raise ClaudeSdkProtocolError(f"SDK turn count mismatch: {counts}")
    result_usage = token_usage(result.usage)
    if not _usage_dominates(result_usage, state.usage):
        raise ClaudeSdkProtocolError(
            "SDK aggregate usage does not match turn usage: "
            f"result={result_usage}, observed={state.usage}"
        )
    return result_usage


def _usage_dominates(aggregate: TokenUsage, observed: TokenUsage) -> bool:
    return (
        aggregate.input_accounted_tokens >= observed.input_accounted_tokens
        and aggregate.output_tokens >= observed.output_tokens
    )
