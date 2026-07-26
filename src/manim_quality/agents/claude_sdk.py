"""Stateless Claude Agent SDK backend with mandatory Runtime hooks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import replace

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    UserMessage,
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
    "Edit",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
)

QueryFunction = Callable[..., AsyncIterator[object]]


class ClaudeSdkRunError(RuntimeError):
    pass


class _DeadlineExtender:
    """Push the session deadline out by external tool wall time.

    The reasoning budget bounds model and protocol time only; real render,
    probe, and detector execution stay bounded by their own tool timeouts.
    Overlapping tool executions extend by their shared wall-clock window
    once, so concurrent calls cannot inflate the deadline.
    """

    def __init__(self) -> None:
        self.scope: anyio.CancelScope | None = None
        self._depth = 0
        self._started = 0.0

    def begin(self) -> None:
        if self._depth == 0:
            self._started = anyio.current_time()
        self._depth += 1

    def finish(self) -> None:
        self._depth -= 1
        if self._depth == 0 and self.scope is not None:
            window = anyio.current_time() - self._started
            if window > 0:
                self.scope.deadline += window


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
        extender = _DeadlineExtender()
        options = _options(request, state, self._provider_env, extender)
        result: ResultMessage | None = None
        try:
            with anyio.CancelScope(
                deadline=anyio.current_time() + request.timeout_ms / 1_000
            ) as scope:
                extender.scope = scope
                async for message in self._query(
                    prompt=request.prompt, options=options
                ):
                    if isinstance(message, AssistantMessage):
                        await state.record_assistant(message)
                    elif isinstance(message, UserMessage):
                        await state.record_user(message)
                    elif isinstance(message, ResultMessage):
                        result = message
                    state.raise_failure()
            if scope.cancelled_caught:
                raise TimeoutError(
                    "Claude Agent SDK session exceeded the reasoning budget"
                )
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
        completed = controls.complete(result.structured_output)
        return replace(
            completed,
            sdk_messages=state.sdk_messages,
            subagent_results=state.subagent_results,
        )


def _options(
    request: BackendRequest,
    state: ClaudeHookState,
    provider_env: Mapping[str, str],
    extender: _DeadlineExtender,
) -> ClaudeAgentOptions:
    tools = list(request.allowed_tools)
    read_tool_names = [item.sdk_name for item in request.read_tools]
    managed_tool_names = [item.sdk_name for item in request.managed_tools]
    hooks = {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[state.pre_tool])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[state.post_tool])],
        "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[state.failed_tool])],
        "SubagentStart": [
            HookMatcher(matcher=None, hooks=[state.subagent_start])
        ],
        "SubagentStop": [HookMatcher(matcher=None, hooks=[state.subagent_stop])],
    }
    denied = _denied_tools(tools)
    return ClaudeAgentOptions(
        tools=tools,
        allowed_tools=tools + read_tool_names + managed_tool_names,
        disallowed_tools=denied,
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
        mcp_servers=_mcp_servers(request, state, extender),
        strict_mcp_config=True,
        plugins=[],
        agents=_subagent_definitions(request),
        continue_conversation=False,
        env=dict(provider_env),
        effort=request.effort,
    )


def _mcp_servers(
    request: BackendRequest,
    state: ClaudeHookState,
    extender: _DeadlineExtender,
) -> Mapping[str, object]:
    grouped: dict[str, list[object]] = {}
    for grant in request.read_tools:
        grouped.setdefault(grant.server_name, []).append(
            _sdk_tool(grant, state, extender, managed=False)
        )
    for grant in request.managed_tools:
        grouped.setdefault(grant.server_name, []).append(
            _sdk_tool(grant, state, extender, managed=True)
        )
    return {
        name: create_sdk_mcp_server(name=name, tools=tools)
        for name, tools in grouped.items()
    }


def _subagent_definitions(
    request: BackendRequest,
) -> Mapping[str, AgentDefinition] | None:
    if not request.subagents:
        return None
    definitions: dict[str, AgentDefinition] = {}
    for spec in request.subagents:
        server_names = sorted(
            {
                name.split("__", 2)[1]
                for name in spec.allowed_tools
                if name.startswith("mcp__") and name.count("__") >= 2
            }
        )
        definitions[spec.name] = AgentDefinition(
            description=spec.description,
            prompt=spec.prompt,
            tools=list(spec.allowed_tools),
            disallowedTools=list(_DENIED_TOOLS),
            model=request.profile.model,
            skills=[],
            mcpServers=server_names,
            maxTurns=spec.max_turns,
            background=False,
            effort=spec.effort,
            permissionMode="dontAsk",
        )
    return definitions


def _denied_tools(enabled: list[str]) -> list[str]:
    aliases = {"Agent", "Task"} if "Agent" in enabled or "Task" in enabled else set()
    return [
        tool
        for tool in _DENIED_TOOLS
        if tool not in enabled and tool not in aliases
    ]


def _sdk_tool(
    grant,
    state: ClaudeHookState,
    extender: _DeadlineExtender,
    *,
    managed: bool,
):
    @tool(
        grant.name,
        grant.description,
        thaw_json_object(grant.input_schema),
    )
    async def invoke(arguments):
        extender.begin()
        try:
            if managed:
                text = await state.execute_managed_tool(grant.sdk_name, arguments)
            else:
                text = await state.execute_read_tool(grant.sdk_name, arguments)
        finally:
            extender.finish()
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
    state.validate_subagent_protocol()
    return result_usage


def _usage_dominates(aggregate: TokenUsage, observed: TokenUsage) -> bool:
    return (
        aggregate.input_accounted_tokens >= observed.input_accounted_tokens
        and aggregate.output_tokens >= observed.output_tokens
    )
