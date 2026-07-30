import anyio

from manim_quality.agents._claude_tool_hooks import pre_tool, recover_managed_failure
from manim_quality.agents._guard_primitives import DuplicatePatch, PathDenied


class RecoverableState:
    def __init__(self) -> None:
        self.finished = []

    async def _finish_tool(self, tool_id: str) -> dict[str, object]:
        self.finished.append(tool_id)
        return {}


def test_managed_tool_failure_returns_correction_to_agent() -> None:
    state = RecoverableState()
    result = anyio.run(
        recover_managed_failure,
        state,
        {
            "tool_use_id": "validate-1",
            "error": "only the current candidate can be validated",
        },
    )

    assert state.finished == ["validate-1"]
    assert result["continue_"] is True
    assert "current candidate" in result["hookSpecificOutput"]["additionalContext"]


def test_duplicate_native_edit_is_recoverable(tmp_path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    class Controls:
        def authorize_tool(self, *args, **kwargs):
            del args, kwargs
            raise DuplicatePatch(f"duplicate Edit patch: {candidate}")

    class Request:
        workspace = tmp_path

    class State:
        _request = Request()
        _controls = Controls()
        _failure = None

    async def scenario():
        state = State()
        state._lock = anyio.Lock()
        return await pre_tool(
            state,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(candidate),
                    "old_string": "pass",
                    "new_string": "pass ",
                },
            },
            "edit-2",
            {},
        )

    result = anyio.run(scenario)

    assert result["continue_"] is True
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "duplicate Edit patch" in result["stopReason"]


def test_out_of_scope_native_read_is_denied_but_recoverable(tmp_path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    class Controls:
        def authorize_tool(self, *args, **kwargs):
            del args, kwargs
            raise PathDenied("/tmp/render.log is outside exact allowlist")

    class Request:
        workspace = tmp_path

    class State:
        _request = Request()
        _controls = Controls()
        _failure = None

    async def scenario():
        state = State()
        state._lock = anyio.Lock()
        return await pre_tool(
            state,
            {
                "tool_name": "Read",
                "tool_input": {
                    "file_path": "/tmp/render.log",
                    "offset": 1,
                    "limit": 200,
                },
            },
            "read-log-1",
            {},
        )

    result = anyio.run(scenario)

    assert result["continue_"] is True
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "authorized Solution range" in result["stopReason"]
