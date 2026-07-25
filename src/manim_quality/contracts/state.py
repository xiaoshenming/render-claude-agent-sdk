"""Side-effect-free quality state transition rules."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class QualityState(StrEnum):
    RECEIVED = "RECEIVED"
    INPUT_VALIDATED = "INPUT_VALIDATED"
    BASELINE_READY = "BASELINE_READY"
    LOGIC_REVIEWING = "LOGIC_REVIEWING"
    POLICY_EVALUATING = "POLICY_EVALUATING"
    LOGIC_REPAIRING = "LOGIC_REPAIRING"
    LOGIC_VERIFYING = "LOGIC_VERIFYING"
    LOGIC_CERTIFIED = "LOGIC_CERTIFIED"
    LOGIC_CERTIFIED_WITH_WARNING = "LOGIC_CERTIFIED_WITH_WARNING"
    LAYOUT_CHECKING = "LAYOUT_CHECKING"
    LAYOUT_REPAIRING = "LAYOUT_REPAIRING"
    LAYOUT_VERIFYING = "LAYOUT_VERIFYING"
    LAYOUT_CERTIFIED = "LAYOUT_CERTIFIED"
    LAYOUT_CERTIFIED_WITH_WARNING = "LAYOUT_CERTIFIED_WITH_WARNING"
    FINAL_CONSISTENCY_GATE = "FINAL_CONSISTENCY_GATE"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNING = "ACCEPTED_WITH_WARNING"
    REGENERATE = "REGENERATE"
    HOLD = "HOLD"
    FAILED = "FAILED"


_STOP = frozenset({QualityState.REGENERATE, QualityState.HOLD, QualityState.FAILED})
TRANSITIONS: Mapping[QualityState, frozenset[QualityState]] = MappingProxyType(
    {
        QualityState.RECEIVED: frozenset(
            {QualityState.INPUT_VALIDATED, QualityState.FAILED}
        ),
        QualityState.INPUT_VALIDATED: frozenset({QualityState.BASELINE_READY, *_STOP}),
        QualityState.BASELINE_READY: frozenset({QualityState.LOGIC_REVIEWING, *_STOP}),
        QualityState.LOGIC_REVIEWING: frozenset(
            {
                QualityState.POLICY_EVALUATING,
                QualityState.LOGIC_REPAIRING,
                QualityState.LOGIC_CERTIFIED,
                QualityState.LOGIC_CERTIFIED_WITH_WARNING,
                *_STOP,
            }
        ),
        QualityState.POLICY_EVALUATING: frozenset(
            {QualityState.LOGIC_CERTIFIED_WITH_WARNING, *_STOP}
        ),
        QualityState.LOGIC_REPAIRING: frozenset({QualityState.LOGIC_VERIFYING, *_STOP}),
        QualityState.LOGIC_VERIFYING: frozenset(
            {
                QualityState.LOGIC_REPAIRING,
                QualityState.LOGIC_CERTIFIED,
                *_STOP,
            }
        ),
        QualityState.LOGIC_CERTIFIED: frozenset({QualityState.LAYOUT_CHECKING, *_STOP}),
        QualityState.LOGIC_CERTIFIED_WITH_WARNING: frozenset(
            {QualityState.LAYOUT_CHECKING, *_STOP}
        ),
        QualityState.LAYOUT_CHECKING: frozenset(
            {
                QualityState.LAYOUT_REPAIRING,
                QualityState.LAYOUT_CERTIFIED,
                QualityState.LAYOUT_CERTIFIED_WITH_WARNING,
                *_STOP,
            }
        ),
        QualityState.LAYOUT_REPAIRING: frozenset(
            {QualityState.LAYOUT_VERIFYING, *_STOP}
        ),
        QualityState.LAYOUT_VERIFYING: frozenset(
            {
                QualityState.LAYOUT_REPAIRING,
                QualityState.LAYOUT_CERTIFIED,
                QualityState.LAYOUT_CERTIFIED_WITH_WARNING,
                *_STOP,
            }
        ),
        QualityState.LAYOUT_CERTIFIED: frozenset(
            {QualityState.FINAL_CONSISTENCY_GATE, *_STOP}
        ),
        QualityState.LAYOUT_CERTIFIED_WITH_WARNING: frozenset(
            {QualityState.FINAL_CONSISTENCY_GATE, *_STOP}
        ),
        QualityState.FINAL_CONSISTENCY_GATE: frozenset(
            {
                QualityState.ACCEPTED,
                QualityState.ACCEPTED_WITH_WARNING,
                *_STOP,
            }
        ),
        QualityState.ACCEPTED: frozenset(),
        QualityState.ACCEPTED_WITH_WARNING: frozenset(),
        QualityState.REGENERATE: frozenset(),
        QualityState.HOLD: frozenset(),
        QualityState.FAILED: frozenset(),
    }
)


class InvalidTransition(ValueError):
    def __init__(self, current: QualityState, target: QualityState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"invalid quality transition: {current.value} -> {target.value}"
        )


def allowed_transitions(state: QualityState) -> frozenset[QualityState]:
    if not isinstance(state, QualityState):
        raise TypeError("state must be a QualityState")
    return TRANSITIONS[state]


def require_transition(current: QualityState, target: QualityState) -> None:
    if not isinstance(target, QualityState):
        raise TypeError("target must be a QualityState")
    if target not in allowed_transitions(current):
        raise InvalidTransition(current, target)
