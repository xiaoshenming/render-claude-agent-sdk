"""Build the immutable request passed across the Agent backend boundary."""

from __future__ import annotations

from ._runtime_models import AgentRunRequest, BackendRequest
from .budget import BudgetLimits, BudgetTracker
from .guards import ToolGuard


def build_backend_request(
    request: AgentRunRequest,
    *,
    guard: ToolGuard,
    budget: BudgetTracker,
    limits: BudgetLimits,
) -> BackendRequest:
    return BackendRequest(
        prompt=request.prompt,
        output_schema=request.output_schema,
        profile=request.profile,
        workspace=str(request.workspace.resolve()),
        readable_paths=guard.readable_paths,
        editable_paths=guard.editable_paths,
        allowed_tools=tuple(sorted(request.profile.allowed_tools)),
        read_tools=tuple(request.read_tools),
        managed_tools=tuple(request.managed_tools),
        subagents=tuple(request.subagents),
        effort=request.effort,
        max_turns=limits.max_turns,
        max_tool_calls=limits.max_tool_calls,
        estimated_input_tokens=request.estimated_input_tokens,
        reserved_output_tokens=request.reserved_output_tokens,
        reserved_cache_read_tokens=request.reserved_cache_read_tokens,
        reserved_cache_write_tokens=request.reserved_cache_write_tokens,
        timeout_ms=budget.remaining_elapsed_ms(),
    )
