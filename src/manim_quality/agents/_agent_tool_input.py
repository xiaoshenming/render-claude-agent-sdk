"""Normalize foreground Reviewer Agent calls across CLI schema revisions."""

from __future__ import annotations

from collections.abc import Mapping

from manim_quality.contracts._json_values import freeze_json_object

from ._guard_primitives import ToolDenied
from .subagents import NativeSubagentSpec


def normalize_reviewer_agent_input(
    input_data: object,
    subagents: Mapping[str, NativeSubagentSpec],
    invoked: set[str],
) -> Mapping[str, object]:
    """Keep read-only Reviewers in the parent workspace.

    Claude CLI 0.2.128 can add ``isolation=worktree`` to parallel Agent calls.
    The Reviewers have no filesystem tools and read through bounded MCP grants,
    so a worktree is both unnecessary and invalid in a render workspace.
    """

    value = dict(freeze_json_object(input_data, "agent_tool_input"))
    isolation = value.get("isolation")
    if isolation not in {None, "remote", "worktree"}:
        raise ToolDenied(f"unsupported Reviewer isolation: {isolation}")
    # Remote isolation is the CLI's read-only subagent mode.  It does not
    # create a local Git worktree.  Never pass worktree isolation through.
    value["isolation"] = "remote"
    # Claude CLI enriches Agent calls with execution metadata in newer builds.
    # AgentDefinition already owns these values; never let model output
    # override the registered Reviewer identity, model, team, or mode.
    value.pop("model", None)
    name = value.get("name")
    if name is not None and name != value.get("subagent_type"):
        raise ToolDenied("Reviewer name must match subagent_type")
    for field in ("mode", "team_name"):
        value.pop(field, None)
    allowed_fields = {
        "description", "isolation", "name", "prompt", "run_in_background",
        "subagent_type",
    }
    unsupported = set(value) - allowed_fields
    if unsupported:
        raise ToolDenied(f"Agent input contains unsupported fields: {sorted(unsupported)}")
    name = value.get("subagent_type")
    if not isinstance(name, str) or name not in subagents:
        raise ToolDenied("Agent subagent_type is not registered")
    if value.get("run_in_background") is not False:
        raise ToolDenied("Reviewer subagents must run in the foreground")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 1_000:
        raise ToolDenied("Agent prompt must contain 1 to 1000 characters")
    description = value.get("description")
    if description is not None and (
        not isinstance(description, str)
        or not description.strip()
        or len(description) > 200
    ):
        raise ToolDenied("Agent description exceeds its bound")
    if name in invoked:
        raise ToolDenied(f"Reviewer may only run once: {name}")
    invoked.add(name)
    if name is None:
        value.pop("name", None)
    return freeze_json_object(value, "normalized_agent_tool_input")
