"""Tool authorization hooks for one Claude SDK runtime state."""

from __future__ import annotations

import anyio

from manim_quality.contracts._json_values import thaw_json_object

from ._claude_hook_values import (
    ClaudeSdkProtocolError,
    normalize_sdk_input,
)
from ._runtime_models import OutputRejected
from .managed_tools import ManagedToolInputError


async def pre_tool(state, data, tool_use_id, context) -> dict[str, object]:
    del context
    async with state._lock:
        try:
            normalized = _authorize_tool(state, data, tool_use_id)
        except OutputRejected as error:
            return _handle_output_rejection(state, error, tool_use_id)
        except ManagedToolInputError as error:
            return _deny(str(error), continue_run=True)
        except Exception as error:
            state._failure = error
            return _deny("tool authorization failed")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": thaw_json_object(normalized),
        }
    }


def _authorize_tool(state, data, tool_use_id):
    tool_input = normalize_sdk_input(
        data["tool_input"],
        state._request.workspace,
    )
    tool_name = data["tool_name"]
    agent_id = data.get("agent_id")
    agent_type = data.get("agent_type")
    if tool_name == "StructuredOutput":
        if state._terminal_tools or state._terminal_submitted:
            raise ClaudeSdkProtocolError(
                "multiple terminal structured outputs are not allowed"
            )
        if state._subagents.completed_names != state.required_subagent_names:
            missing = state.required_subagent_names - state._subagents.completed_names
            raise OutputRejected(
                f"required reviewers have not completed: {sorted(missing)}"
            )
        normalized = state._controls.authorize_output_submission(tool_input)
        state._terminal_tools.add(tool_use_id)
        return normalized
    _enforce_findings_prerequisites(state, tool_name, agent_id)
    if agent_id is not None:
        state._subagents.authorize_tool(
            agent_type=agent_type,
            agent_id=agent_id,
            tool_name=tool_name,
        )
    normalized = state._controls.authorize_tool(
        tool_name,
        tool_input,
        agent_id=agent_id,
        agent_type=agent_type,
    )
    if (
        agent_id is None
        and tool_name in {"Agent", "Task"}
        and isinstance(normalized.get("subagent_type"), str)
    ):
        state._subagents.authorize(
            str(normalized["subagent_type"]),
            tool_use_id,
        )
    if tool_name.endswith("__read_solution") and agent_id is None:
        state._parent_solution_read = True
    return normalized


def _enforce_findings_prerequisites(state, tool_name, agent_id) -> None:
    if agent_id is not None or not tool_name.endswith("__record_findings"):
        return
    if not state._parent_solution_read:
        raise ClaudeSdkProtocolError(
            "parent must call read_solution before findings"
        )
    if state._subagents.completed_names != state.required_subagent_names:
        raise ClaudeSdkProtocolError(
            "both Reviewer ToolResults are required before findings"
        )


def _handle_output_rejection(state, error, tool_use_id) -> dict[str, object]:
    if state._output_corrections != 0:
        failure = ClaudeSdkProtocolError(
            "structured output correction limit exceeded"
        )
        state._failure = failure
        return _deny("structured output correction limit exceeded")
    state._controls.record_output_correction(str(error))
    state._output_corrections += 1
    state._denied_output_ids.add(tool_use_id)
    return _deny(str(error), continue_run=True)


async def retry_structured_output(
    state,
    tool_id: str,
    error_text: str,
) -> dict[str, object]:
    await state._round_ready.wait()
    async with state._lock:
        failure = _prepare_structured_retry(state, tool_id, error_text)
        if failure is not None:
            return {"continue_": False, "stopReason": str(failure)}
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


async def recover_managed_failure(state, data) -> dict[str, object]:
    result = await state._finish_tool(data["tool_use_id"])
    if result:
        return result
    detail = str(data.get("error", "invalid tool input"))[:1_000]
    return {
        "continue_": True,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
            "additionalContext": (
                "The managed tool rejected this call. Use its error result to "
                "correct the next call without repeating completed work. "
                f"Error: {detail}"
            ),
        },
    }


def _prepare_structured_retry(state, tool_id: str, error_text: str):
    if tool_id not in state._pending_tools:
        error = ClaudeSdkProtocolError(
            f"unexpected failed structured output: {tool_id}"
        )
        state._failure = error
        return error
    if state._output_corrections >= 2:
        error = ClaudeSdkProtocolError(
            "structured output correction limit exceeded"
        )
        state._failure = error
        return error
    state._pending_tools.remove(tool_id)
    state._terminal_tools.discard(tool_id)
    state._controls.record_output_correction(error_text)
    state._output_corrections += 1
    if not state._pending_tools:
        try:
            state._before_next_round()
        except Exception as error:
            state._failure = error
            return error
        state._round_open = False
        state._round_ready = anyio.Event()
    return None


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
