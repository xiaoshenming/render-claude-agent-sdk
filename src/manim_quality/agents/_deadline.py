"""Deadline suspension for external tool execution windows."""

from __future__ import annotations

import math

import anyio


class _DeadlineExtender:
    """Suspend the session deadline while external tools run.

    The reasoning budget bounds model and protocol time only. While at
    least one tool executes the deadline is parked at infinity so it cannot
    fire mid-render; each tool stays bounded by its own timeout, so the
    chain remains finite. When the last overlapping tool finishes, the
    deadline is restored shifted by the shared wall-clock window once.
    """

    def __init__(self) -> None:
        self.scope: anyio.CancelScope | None = None
        self._depth = 0
        self._started = 0.0
        self._saved_deadline: float | None = None

    def begin(self) -> None:
        if self._depth == 0:
            self._started = anyio.current_time()
            if self.scope is not None:
                self._saved_deadline = self.scope.deadline
                self.scope.deadline = math.inf
        self._depth += 1

    def finish(self) -> None:
        self._depth -= 1
        if self._depth > 0:
            return
        window = max(0.0, anyio.current_time() - self._started)
        if self.scope is not None and self._saved_deadline is not None:
            self.scope.deadline = self._saved_deadline + window
        self._saved_deadline = None
