from types import SimpleNamespace

import anyio

from manim_quality.agents._claude_hooks import ClaudeHookState


class Controls:
    def __init__(self, remaining_turns: int) -> None:
        self.remaining_turns = remaining_turns
        self.next_rounds = 0

    def before_next_round(self, **_reservations) -> None:
        self.next_rounds += 1
        self.remaining_turns -= 1


def state(remaining_turns: int, *, terminal: bool = False) -> ClaudeHookState:
    value = ClaudeHookState.__new__(ClaudeHookState)
    value._controls = Controls(remaining_turns)
    value._request = SimpleNamespace(
        estimated_input_tokens=1, reserved_output_tokens=1,
        reserved_cache_read_tokens=0, reserved_cache_write_tokens=0,
    )
    value._lock = anyio.Lock()
    value._round_ready = anyio.Event()
    value._round_ready.set()
    value._completed_tools = set()
    value._pending_tools = {"tool-1"}
    value._terminal_tools = {"tool-1"} if terminal else set()
    value._terminal_submitted = False
    value._failure = None
    value._round_open = True
    return value


def test_last_available_round_receives_final_submission_reminder() -> None:
    runtime = state(1)

    result = anyio.run(runtime._finish_tool, "tool-1")

    assert runtime._controls.next_rounds == 1
    assert result["continue_"] is True
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "final available model round" in context
    assert "StructuredOutput" in context
    assert "Do not invent evidence" in context


def test_nonfinal_or_terminal_tool_receives_no_reminder() -> None:
    ordinary = state(2)
    terminal = state(1, terminal=True)

    assert anyio.run(ordinary._finish_tool, "tool-1") == {}
    assert anyio.run(terminal._finish_tool, "tool-1") == {}
    assert ordinary._controls.next_rounds == 1
    assert terminal._controls.next_rounds == 0
