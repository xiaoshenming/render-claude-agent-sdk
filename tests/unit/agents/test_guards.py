from pathlib import Path

import pytest

from manim_quality.agents.guards import (
    DuplicatePatch,
    DuplicateRead,
    PathDenied,
    ToolDenied,
    ToolGuard,
)
from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect
from manim_quality.agents.profile import (
    assurance_profile,
    coder_profile,
    reviewer_profile,
)
from manim_quality.agents.read_tools import ReadonlyToolGrant
from manim_quality.agents.subagents import NativeSubagentSpec
from manim_quality.agents.tool_policy import ToolInputPolicy


def _inspect(arguments):
    return str(arguments["relation"])


def geometry_grant() -> ReadonlyToolGrant:
    return ReadonlyToolGrant(
        server_name="geometry",
        name="inspect_relation",
        description="Inspect one geometry relation.",
        input_schema={
            "type": "object",
            "properties": {"relation": {"type": "string"}},
            "required": ["relation"],
            "additionalProperties": False,
        },
        handler=_inspect,
        max_calls=2,
        timeout_ms=100,
        max_result_chars=200,
    )


async def _mutate(arguments):
    return str(arguments["value"])


def mutation_grant() -> ManagedToolGrant:
    return ManagedToolGrant(
        server_name="quality",
        name="mutate",
        description="Mutate one value.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler=_mutate,
        effect=ToolEffect.SESSION_MUTATION,
        max_calls=1,
        timeout_ms=1_000,
        max_result_chars=100,
    )


def make_guard(workspace: Path, candidate: Path, *, coder: bool = False) -> ToolGuard:
    profile = (
        coder_profile(model="test", prompt_version="v1")
        if coder
        else reviewer_profile(model="test", prompt_version="v1")
    )
    return ToolGuard(
        workspace=workspace,
        profile=profile,
        readable_paths=(candidate,),
        editable_paths=(candidate,) if coder else (),
    )


def test_guard_enforces_tool_and_exact_file_allowlists(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    other = tmp_path / "other.py"
    other.write_text("value = 2\n", encoding="utf-8")
    guard = make_guard(tmp_path, candidate)

    allowed = guard.authorize("Read", {"file_path": str(candidate)})
    assert allowed["file_path"] == str(candidate.resolve())
    for tool in ("Edit", "Bash", "Write", "Agent", "Task", "Web", "Upload"):
        with pytest.raises(ToolDenied):
            guard.authorize(tool, {"file_path": str(candidate)})
    with pytest.raises(PathDenied, match="allowlist"):
        guard.authorize("Read", {"file_path": str(other)})


def test_guard_rejects_parent_traversal_and_workspace_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    workspace.mkdir()
    candidate = workspace / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    guard = make_guard(workspace, candidate)

    with pytest.raises(PathDenied, match="parent traversal"):
        guard.authorize("Read", {"file_path": "nested/../candidate.py"})
    with pytest.raises(PathDenied, match="workspace"):
        guard.authorize("Read", {"file_path": str(outside)})


def test_guard_detects_duplicate_reads_and_patches(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    read_guard = make_guard(tmp_path, candidate)
    read_guard.authorize("Read", {"file_path": str(candidate), "offset": 1})
    with pytest.raises(DuplicateRead):
        read_guard.authorize("Read", {"file_path": str(candidate), "offset": 1})
    read_guard.authorize("Read", {"file_path": str(candidate), "offset": 2})

    edit_guard = make_guard(tmp_path, candidate, coder=True)
    patch = {
        "file_path": str(candidate),
        "old_string": "value = 1",
        "new_string": "value = 2",
    }
    edit_guard.authorize("Edit", patch)
    with pytest.raises(DuplicatePatch):
        edit_guard.authorize("Edit", patch)


def test_guard_allows_one_fresh_read_after_edit(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    guard = make_guard(tmp_path, candidate, coder=True)
    read = {"file_path": str(candidate)}

    guard.authorize("Read", read)
    guard.authorize(
        "Edit",
        {
            "file_path": str(candidate),
            "old_string": "value = 1",
            "new_string": "value = 2",
        },
    )
    guard.authorize("Read", read)

    with pytest.raises(DuplicateRead):
        guard.authorize("Read", read)


def test_guard_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    link = workspace / "candidate.py"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error}")

    with pytest.raises(PathDenied, match="workspace"):
        make_guard(workspace, link)


def test_guard_validates_workspace_and_declared_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    workspace.mkdir()
    candidate = workspace / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")

    with pytest.raises(PathDenied, match="directory"):
        make_guard(candidate, candidate)
    with pytest.raises(PathDenied, match="parent traversal"):
        ToolGuard(
            workspace=workspace,
            profile=reviewer_profile(model="test", prompt_version="v1"),
            readable_paths=(Path("nested/../candidate.py"),),
            editable_paths=(),
        )
    with pytest.raises(PathDenied, match="escapes workspace"):
        make_guard(workspace, outside)
    with pytest.raises(PathDenied, match="cannot be resolved"):
        make_guard(workspace, workspace / "missing.py")


def test_guard_validates_edit_shape_and_profile_scope(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    reviewer = reviewer_profile(model="test", prompt_version="v1")

    with pytest.raises(ToolDenied, match="editable paths"):
        ToolGuard(
            workspace=tmp_path,
            profile=reviewer,
            readable_paths=(candidate,),
            editable_paths=(candidate,),
        )

    coder_guard = ToolGuard(
        workspace=tmp_path,
        profile=coder_profile(model="test", prompt_version="v1"),
        readable_paths=(candidate,),
        editable_paths=(),
    )
    with pytest.raises(PathDenied, match="edit path"):
        coder_guard.authorize(
            "Edit",
            {"file_path": str(candidate), "old_string": "1", "new_string": "2"},
        )

    editable_guard = make_guard(tmp_path, candidate, coder=True)
    assert editable_guard.editable_paths == (str(candidate.resolve()),)
    with pytest.raises(ToolDenied, match="requires"):
        editable_guard.authorize("Edit", {"file_path": str(candidate)})
    with pytest.raises(ToolDenied, match="must change"):
        editable_guard.authorize(
            "Edit",
            {"file_path": str(candidate), "old_string": "1", "new_string": "1"},
        )


def test_guard_rejects_missing_paths_and_directories(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    guard = make_guard(tmp_path, candidate)

    with pytest.raises(PathDenied, match="file_path"):
        guard.authorize("Read", {})
    with pytest.raises(PathDenied, match="cannot be resolved"):
        guard.authorize("Read", {"file_path": "missing.py"})
    with pytest.raises(PathDenied, match="not a file"):
        guard.authorize("Read", {"file_path": str(tmp_path)})


def test_guard_authorizes_only_explicit_bounded_read_tools(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = geometry_grant()
    guard = ToolGuard(
        workspace=tmp_path,
        profile=reviewer_profile(model="test", prompt_version="v1"),
        readable_paths=(candidate,),
        editable_paths=(),
        read_tools=(tool,),
    )

    tool_input = {"relation": "perpendicular"}
    assert guard.authorize(tool.sdk_name, tool_input) == tool_input
    guard.claim_read_tool(tool.sdk_name, tool_input)
    assert guard.authorize(tool.sdk_name, tool_input) == tool_input
    guard.claim_read_tool(tool.sdk_name, tool_input)
    with pytest.raises(ToolDenied, match="call limit"):
        guard.authorize(tool.sdk_name, tool_input)
    with pytest.raises(ToolDenied, match="not allowed"):
        guard.authorize("mcp__other__inspect_relation", tool_input)


def test_guard_requires_one_time_authorization_before_provider_execution(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = geometry_grant()
    guard = ToolGuard(
        workspace=tmp_path,
        profile=reviewer_profile(model="test", prompt_version="v1"),
        readable_paths=(candidate,),
        editable_paths=(),
        read_tools=(tool,),
    )

    with pytest.raises(ToolDenied, match="authorization"):
        guard.claim_read_tool(tool.sdk_name, {"relation": "parallel"})


def test_guard_enforces_generic_builtin_tool_policy(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    guard = ToolGuard(
        workspace=tmp_path,
        profile=reviewer_profile(model="test", prompt_version="v1"),
        readable_paths=(candidate,),
        editable_paths=(),
        tool_policies={
            "Read": ToolInputPolicy(
                max_calls=1,
                required_fields=("offset", "limit"),
                integer_maximums={"limit": 220},
            )
        },
    )

    with pytest.raises(ToolDenied, match="required"):
        guard.authorize("Read", {"file_path": str(candidate)})
    guard.authorize(
        "Read", {"file_path": str(candidate), "offset": 1, "limit": 220}
    )
    with pytest.raises(ToolDenied, match="call limit"):
        guard.authorize(
            "Read", {"file_path": str(candidate), "offset": 221, "limit": 10}
        )


def test_guard_enforces_foreground_named_reviewer_boundaries(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = geometry_grant()
    reviewer = NativeSubagentSpec(
        name="math_geometry_reviewer",
        description="Review geometry.",
        prompt="Read once and report.",
        allowed_tools=(tool.sdk_name,),
    )


    guard = ToolGuard(
        workspace=tmp_path,
        profile=assurance_profile(model="test", prompt_version="v1"),
        readable_paths=(),
        editable_paths=(),
        read_tools=(tool,),
        subagents=(reviewer,),
    )
    invocation = {
        "subagent_type": reviewer.name,
        "description": "Review geometry",
        "prompt": "Audit all mathematical relations.",
        "run_in_background": False,
    }

    assert guard.authorize("Task", invocation)["subagent_type"] == reviewer.name
    with pytest.raises(ToolDenied, match="only run once"):
        guard.authorize("Agent", invocation)
    with pytest.raises(ToolDenied, match="unknown subagent"):
        guard.authorize(
            tool.sdk_name,
            {"relation": "parallel"},
            agent_id="child-unknown",
            agent_type="general-purpose",
        )
    with pytest.raises(ToolDenied, match="not allowed"):
        guard.authorize(
            "Bash",
            {"command": "dir"},
            agent_id="child-1",
            agent_type=reviewer.name,
        )
    assert guard.authorize(
        tool.sdk_name,
        {"relation": "parallel"},
        agent_id="child-1",
        agent_type=reviewer.name,
    ) == {"relation": "parallel"}


@pytest.mark.parametrize("background", [True, None])
def test_guard_rejects_background_or_implicit_reviewer(
    tmp_path: Path,
    background,
) -> None:
    tool = geometry_grant()
    reviewer = NativeSubagentSpec(
        name="math_geometry_reviewer",
        description="Review geometry.",
        prompt="Read once and report.",
        allowed_tools=(tool.sdk_name,),
    )
    guard = ToolGuard(
        workspace=tmp_path,
        profile=assurance_profile(model="test", prompt_version="v1"),
        readable_paths=(),
        editable_paths=(),
        read_tools=(tool,),
        subagents=(reviewer,),
    )
    value = {
        "subagent_type": reviewer.name,
        "prompt": "Audit geometry.",
    }
    if background is not None:
        value["run_in_background"] = background

    with pytest.raises(ToolDenied, match="foreground"):
        guard.authorize("Agent", value)


def test_failed_parent_mutation_can_refund_per_tool_quota(tmp_path: Path) -> None:
    tool = mutation_grant()
    guard = ToolGuard(
        workspace=tmp_path,
        profile=assurance_profile(model="test", prompt_version="v1"),
        readable_paths=(),
        editable_paths=(),
        managed_tools=(tool,),
    )
    tool_input = {"value": "first"}

    guard.authorize(tool.sdk_name, tool_input)
    guard.claim_managed_tool(tool.sdk_name, tool_input)
    guard.refund_parent_managed_tool(tool.sdk_name)

    assert guard.authorize(tool.sdk_name, {"value": "corrected"}) == {
        "value": "corrected"
    }
