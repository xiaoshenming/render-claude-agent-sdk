"""Claude SDK hook state bound to one RuntimeControls instance."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import anyio
from claude_agent_sdk import AssistantMessage, ToolUseBlock

from manim_quality.contracts._json_values import thaw_json_object

from ._runtime_models import BackendRequest, OutputRejected
from .runtime import RuntimeControls
from .usage import TokenUsage


class ClaudeSdkProtocolError(RuntimeError):
    pass


class ClaudeHookState:
    def __init__(self, controls: RuntimeControls, request: BackendRequest) -> None:
        self._controls = controls
        self._request = request
        self._lock = anyio.Lock()
        self._round_ready = anyio.Event()
        self._pending_tools: set[str] = set()
        self._terminal_tools: set[str] = set()
        self._seen_message_ids: set[str] = set()
        self._seen_tool_ids: set[str] = set()
        self._failure: Exception | None = None
        self._usage = TokenUsage()
        self._turns = 0
        self._round_open = False
        self._output_corrections = 0
        self._denied_output_ids: set[str] = set()
        self._terminal_submitted = False

    @property
    def usage(self) -> TokenUsage:
        return self._usage

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def sdk_turn_floor(self) -> int:
        return self._turns

    async def pre_tool(self, data, tool_use_id, context) -> dict[str, object]:
        del context
        async with self._lock:
            try:
                tool_input = _normalize_sdk_input(
                    data["tool_input"], self._request.workspace
                )
                if data["tool_name"] == "StructuredOutput":
                    if self._terminal_tools or self._terminal_submitted:
                        raise ClaudeSdkProtocolError(
                            "multiple terminal structured outputs are not allowed"
                        )
                    normalized = self._controls.authorize_output_submission(tool_input)
                    self._terminal_tools.add(tool_use_id)
                else:
                    normalized = self._controls.authorize_tool(
                        data["tool_name"], tool_input
                    )
            except OutputRejected as error:
                if self._output_corrections != 0:
                    failure = ClaudeSdkProtocolError(
                        "structured output correction limit exceeded"
                    )
                    self._failure = failure
                    return _deny("structured output correction limit exceeded")
                self._controls.record_output_correction(str(error))
                self._output_corrections += 1
                self._denied_output_ids.add(tool_use_id)
                return _deny(str(error), continue_run=True)
            except Exception as error:
                self._failure = error
                return _deny("tool authorization failed")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": thaw_json_object(normalized),
            }
        }

    async def post_tool(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        return await self._finish_tool(data["tool_use_id"])

    async def failed_tool(self, data, tool_use_id, context) -> dict[str, object]:
        del tool_use_id, context
        if data.get("tool_name") == "StructuredOutput":
            return await self._retry_structured_output(
                data["tool_use_id"], str(data.get("error", "schema mismatch"))
            )
        error = RuntimeError(f"SDK tool failed: {data.get('error', 'unknown error')}")
        async with self._lock:
            self._failure = error
        return {"continue_": False, "stopReason": str(error)}

    async def _retry_structured_output(
        self, tool_id: str, error_text: str
    ) -> dict[str, object]:
        await self._round_ready.wait()
        async with self._lock:
            if tool_id not in self._pending_tools:
                error = ClaudeSdkProtocolError(
                    f"unexpected failed structured output: {tool_id}"
                )
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
            if self._output_corrections != 0:
                error = ClaudeSdkProtocolError(
                    "structured output correction limit exceeded"
                )
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
            self._pending_tools.remove(tool_id)
            self._terminal_tools.discard(tool_id)
            self._controls.record_output_correction(error_text)
            self._output_corrections += 1
            if not self._pending_tools:
                try:
                    self._before_next_round()
                except Exception as error:
                    self._failure = error
                    return {"continue_": False, "stopReason": str(error)}
                self._round_open = False
                self._round_ready = anyio.Event()
        detail = error_text[:1_000]
        return {
            "continue_": True,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": (
                    "Correct only the structured-output contract and submit once more. "
                    f"Do not redo diagnosis or add unsupported fields. Error: {detail}"
                ),
            },
        }

    async def record_assistant(self, message: AssistantMessage) -> None:
        if message.error is not None:
            raise ClaudeSdkProtocolError(f"assistant error: {message.error}")
        usage = _token_usage(message.usage)
        tool_ids = {
            block.id for block in message.content if isinstance(block, ToolUseBlock)
        }
        async with self._lock:
            repeated_message = (
                message.message_id is not None
                and message.message_id in self._seen_message_ids
            )
            new_tool_ids = tool_ids - self._seen_tool_ids
            denied_tool_ids = new_tool_ids & self._denied_output_ids
            pending_tool_ids = new_tool_ids - self._denied_output_ids
            if self._round_open:
                delta = self._controls.merge_round_usage(usage)
                self._usage = self._usage.plus(delta)
                self._pending_tools.update(pending_tool_ids)
                self._seen_tool_ids.update(new_tool_ids)
                if new_tool_ids:
                    self._round_ready.set()
                self._finish_denied_output_round(denied_tool_ids)
                return
            if repeated_message and not new_tool_ids:
                return
            if message.message_id is not None:
                self._seen_message_ids.add(message.message_id)
            if self._pending_tools:
                message = "next round started before tools completed"
                raise ClaudeSdkProtocolError(message)
            self._controls.record_round_usage(usage)
            self._usage = self._usage.plus(usage)
            self._turns += 1
            self._round_open = True
            self._pending_tools = pending_tool_ids
            self._seen_tool_ids.update(new_tool_ids)
            self._round_ready.set()
            self._finish_denied_output_round(denied_tool_ids)

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
        await self._round_ready.wait()
        async with self._lock:
            if tool_id not in self._pending_tools:
                error = ClaudeSdkProtocolError(f"unexpected completed tool: {tool_id}")
                self._failure = error
                return {"continue_": False, "stopReason": str(error)}
            self._pending_tools.remove(tool_id)
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

    def raise_failure(self) -> None:
        if self._failure is not None:
            raise self._failure

    async def execute_read_tool(self, name: str, input_data: object) -> str:
        return await self._controls.execute_read_tool(name, input_data)


def _token_usage(value: object) -> TokenUsage:
    if not isinstance(value, Mapping):
        raise ClaudeSdkProtocolError("assistant usage is required for every turn")
    return TokenUsage(
        input_tokens=_usage_count(value, "input_tokens"),
        output_tokens=_usage_count(value, "output_tokens"),
        cache_read_tokens=_usage_count(value, "cache_read_input_tokens"),
        cache_write_tokens=_usage_count(value, "cache_creation_input_tokens"),
    )


def token_usage(value: object) -> TokenUsage:
    return _token_usage(value)


def _usage_count(value: Mapping[object, object], key: str) -> int:
    count = value.get(key, 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ClaudeSdkProtocolError(f"invalid SDK usage field: {key}")
    return count


def _deny(reason: str, *, continue_run: bool = False) -> dict[str, object]:
    return {
        "continue_": continue_run,
        "stopReason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def _normalize_sdk_input(value: object, workspace: str) -> object:
    if not isinstance(value, Mapping):
        return value
    path = value.get("file_path")
    if not isinstance(path, str):
        return value
    portable = path.replace("\\", "/")
    prefix = "/workspace/"
    if portable.startswith("//"):
        return value
    if portable.casefold().startswith(prefix):
        relative = portable[len(prefix) :]
    elif portable.startswith("/"):
        relative = portable[1:]
    else:
        return value
    normalized = dict(value)
    normalized["file_path"] = str(Path(workspace) / relative)
    return normalized
