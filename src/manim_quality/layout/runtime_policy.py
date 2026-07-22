"""Single source of truth for overlap repair runtime limits."""

from __future__ import annotations

OVERLAP_MAX_ROUNDS = 5
OVERLAP_NO_PROGRESS_STOP = 2
OVERLAP_SAME_SIGNATURE_STOP = 2


def remaining_rounds(rounds_used: int) -> int:
    """Return the bounded number of rounds still available for this task."""
    used = rounds_used if type(rounds_used) is int and rounds_used >= 0 else 0
    return max(0, OVERLAP_MAX_ROUNDS - used)
