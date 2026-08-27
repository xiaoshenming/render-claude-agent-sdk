"""Claude SDK hook state bound to one RuntimeControls instance."""

from __future__ import annotations

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from ._claude_hook_accessors import ClaudeHookAccessors
from ._claude_hook_values import (
    ClaudeSdkProtocolError as ClaudeSdkProtocolError,
)
from ._claude_hook_values import message_record, parse_token_usage, usage_delta
from ._claude_tool_hooks import (
    pre_tool,
    recover_managed_failure,
    retry_structured_output,
)
from ._runtime_models import BackendRequest
from ._subagent_protocol import NativeSubagentProtocol
from .runtime import RuntimeControls
from .usage import TokenUsage


class ClaudeHookState(ClaudeHookAccessors):
    def __init__(self, controls: RuntimeControls, request: BackendRequest) -> None:
        self._controls = controls
        self._request = request
        self._lock = anyio.Lock()
        self._round_ready = anyio.Event()
        self._pending_tools: set[str] = set()
        self._terminal_tools: set[str] = set()
        self._completed_tools: set[str] = set()
        self._seen_message_ids: set[str] = set()
        self._seen_tool_ids: set[str] = set()
        self._failure: Exception | None = None
        self._usage = TokenUsage()
        self._turns = 0
        self._round_open = False
        self._output_corrections = 0
        self._denied_output_ids: set[str] = set()
        self._terminal_submitted = False
        self._allowed_tool_permissions: dict[str, dict[str, object]] = {}
        self._sdk_messages: list[dict[str, object]] = []
        self._subagents = NativeSubagentProtocol(
            tuple(item.name for item in request.subagents)
        )
        self._subagent_usage: dict[str, TokenUsage] = {}
        self._parent_solution_read = False

    async def pre_tool(
        self, data, tool_use_id, context
    ) -> dict[str, object]:
        return await pre_tool(self, data, tool_use_id, context)
    async def post_tool(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        self._controls.finish_tool_timing(data["tool_use_id"])
        if data.get("tool_name") in {"Agent", "Task"}:
            try:
                self._subagents.validate_agent_completion(data["tool_use_id"])
            except Exception as error:
                async with self._lock:
                    self._failure = error
                return {"continue_": False, "stopReason": str(error)}
        return await self._finish_tool(data["tool_use_id"])

    async def failed_tool(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        self._controls.finish_tool_timing(data["tool_use_id"])
        if data.get("tool_name") == "StructuredOutput":
            return await self._retry_structured_output(
                data["tool_use_id"], str(data.get("error", "schema mismatch"))
            )
        if str(data.get("tool_name", "")).startswith("mcp__quality__"):
            return await recover_managed_failure(self, data)
        error = RuntimeError(f"SDK tool failed: {data.get('error', 'unknown error')}")
        async with self._lock:
            self._failure = error
        return {"continue_": False, "stopReason": str(error)}

    async def _retry_structured_output(
        self, tool_id: str, error_text: str
    ) -> dict[str, object]:
        return await retry_structured_output(self, tool_id, error_text)

    async def record_assistant(
        self, message: AssistantMessage
    ) -> None:
        if message.error is not None:
            async with self._lock:
                self._sdk_messages.append(message_record(message))
            raise ClaudeSdkProtocolError(f"assistant error: {message.error}")
        usage = parse_token_usage(message.usage)
        tool_ids = {
            block.id for block in message.content if isinstance(block, ToolUseBlock)
        }
        async with self._lock:
            self._sdk_messages.append(message_record(message))
            if message.parent_tool_use_id is None:
                self._subagents.bind_parent_message(message.message_id)
            repeated_message = (
                message.message_id is not None
                and message.message_id in self._seen_message_ids
            )
            new_tool_ids = tool_ids - self._seen_tool_ids
            denied_tool_ids = new_tool_ids & self._denied_output_ids
            pending_tool_ids = new_tool_ids - self._denied_output_ids
            if message.parent_tool_use_id is not None:
                self._record_subagent_assistant(
                    message.parent_tool_use_id,
                    usage,
                    pending_tool_ids,
                    new_tool_ids,
                )
                return
            if self._round_open:
                self._record_open_parent_round(
                    usage,
                    pending_tool_ids,
                    new_tool_ids,
                    denied_tool_ids,
                )
                return
            if repeated_message and not new_tool_ids:
                return
            self._start_parent_round(
                message.message_id,
                usage,
                pending_tool_ids,
                new_tool_ids,
                denied_tool_ids,
            )

    def _record_subagent_assistant(
        self,
        parent_tool_use_id: str,
        usage: TokenUsage,
        pending_tool_ids: set[str],
        new_tool_ids: set[str],
    ) -> None:
        if not self._round_open:
            raise ClaudeSdkProtocolError(
                "Reviewer message arrived outside an Agent tool round"
            )
        previous = self._subagent_usage.get(parent_tool_use_id, TokenUsage())
        delta = usage_delta(previous, usage)
        self._subagent_usage[parent_tool_use_id] = previous.plus(delta)
        self._controls.record_additional_usage(delta)
        self._usage = self._usage.plus(delta)
        self._track_new_tools(pending_tool_ids, new_tool_ids)

    def _record_open_parent_round(
        self,
        usage: TokenUsage,
        pending_tool_ids: set[str],
        new_tool_ids: set[str],
        denied_tool_ids: set[str],
    ) -> None:
        delta = self._controls.merge_round_usage(usage)
        self._usage = self._usage.plus(delta)
        self._track_new_tools(pending_tool_ids, new_tool_ids)
        self._finish_denied_output_round(denied_tool_ids)

    def _start_parent_round(
        self,
        message_id: str | None,
        usage: TokenUsage,
        pending_tool_ids: set[str],
        new_tool_ids: set[str],
        denied_tool_ids: set[str],
    ) -> None:
        if message_id is not None:
            self._seen_message_ids.add(message_id)
        if self._pending_tools:
            raise ClaudeSdkProtocolError(
                "next round started before tools completed"
            )
        self._controls.record_round_usage(usage)
        self._usage = self._usage.plus(usage)
        self._turns += 1
        self._round_open = True
        self._pending_tools = pending_tool_ids
        self._seen_tool_ids.update(new_tool_ids)
        self._round_ready.set()
        self._finish_denied_output_round(denied_tool_ids)

    def _track_new_tools(
        self,
        pending_tool_ids: set[str],
        new_tool_ids: set[str],
    ) -> None:
        self._pending_tools.update(pending_tool_ids)
        self._seen_tool_ids.update(new_tool_ids)
        if new_tool_ids:
            self._round_ready.set()

    async def record_user(self, message: UserMessage) -> None:
        async with self._lock:
            self._sdk_messages.append(message_record(message))
            blocks = message.content if isinstance(message.content, list) else ()
            for block in blocks:
                if not isinstance(block, ToolResultBlock):
                    continue
                if not self._subagents.owns_tool_use_id(block.tool_use_id):
                    continue
                try:
                    self._subagents.record_result(
                        tool_use_id=block.tool_use_id,
                        content=block.content,
                        is_error=bool(block.is_error),
                        parent_tool_use_id=message.parent_tool_use_id,
                    )
                except Exception as error:
                    self._failure = error

    async def record_result(self, message: ResultMessage) -> None:
        async with self._lock:
            self._sdk_messages.append(message_record(message))

    async def subagent_start(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        async with self._lock:
            try:
                self._subagents.start(
                    data.get("agent_type"),
                    data.get("agent_id"),
                )
            except Exception as error:
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
        return {}

    async def subagent_stop(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        async with self._lock:
            try:
                self._subagents.stop(
                    data.get("agent_type"),
                    data.get("agent_id"),
                )
            except Exception as error:
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
        return {}

    def _finish_denied_output_round(self, denied_tool_ids: set[str]) -> None:
        if not denied_tool_ids:
            return
        self._denied_output_ids.difference_update(denied_tool_ids)
        if self._pending_tools:
            return
        self._before_next_round()
        self._round_open = False
        self._round_ready = anyio.Event()

    async def _finish_tool(self, tool_id: str) -> dict[str, object]:
        if tool_id in self._completed_tools:
            return {}
        await self._round_ready.wait()
        async with self._lock:
            if tool_id in self._completed_tools:
                return {}
            if tool_id not in self._pending_tools:
                error = ClaudeSdkProtocolError(f"unexpected completed tool: {tool_id}")
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
            self._pending_tools.remove(tool_id)
            self._completed_tools.add(tool_id)
            terminal = tool_id in self._terminal_tools
            if terminal:
                self._terminal_tools.remove(tool_id)
                self._terminal_submitted = True
            if self._pending_tools:
                return {}
            if terminal or self._terminal_submitted:
                return {}
            try:
                self._before_next_round()
            except Exception as error:
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
            self._round_open = False
            self._round_ready = anyio.Event()
        return {}

    def _before_next_round(self) -> None:
        self._controls.before_next_round(
            estimated_input_tokens=self._request.estimated_input_tokens,
            reserved_output_tokens=self._request.reserved_output_tokens,
            reserved_cache_read_tokens=self._request.reserved_cache_read_tokens,
            reserved_cache_write_tokens=self._request.reserved_cache_write_tokens,
        )

def token_usage(value: object) -> TokenUsage:
    return parse_token_usage(value)
