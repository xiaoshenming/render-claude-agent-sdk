from __future__ import annotations

from itertools import pairwise

import pytest

from manim_quality.contracts import (
    TRANSITIONS,
    InvalidTransition,
    QualityState,
    allowed_transitions,
    require_transition,
)

TERMINAL_STATES = {
    QualityState.ACCEPTED,
    QualityState.ACCEPTED_WITH_WARNING,
    QualityState.REGENERATE,
    QualityState.HOLD,
    QualityState.FAILED,
}


def _assert_path(*states: QualityState) -> None:
    for current, target in pairwise(states):
        assert target in allowed_transitions(current)
        assert require_transition(current, target) is None


def test_clean_happy_path() -> None:
    _assert_path(
        QualityState.RECEIVED,
        QualityState.INPUT_VALIDATED,
        QualityState.BASELINE_READY,
        QualityState.LOGIC_REVIEWING,
        QualityState.LOGIC_CERTIFIED,
        QualityState.LAYOUT_CHECKING,
        QualityState.LAYOUT_CERTIFIED,
        QualityState.FINAL_CONSISTENCY_GATE,
        QualityState.ACCEPTED,
    )


def test_warning_path_covers_policy_and_layout_warning() -> None:
    _assert_path(
        QualityState.LOGIC_REVIEWING,
        QualityState.POLICY_EVALUATING,
        QualityState.LOGIC_CERTIFIED_WITH_WARNING,
        QualityState.LAYOUT_CHECKING,
        QualityState.LAYOUT_REPAIRING,
        QualityState.LAYOUT_VERIFYING,
        QualityState.LAYOUT_CERTIFIED_WITH_WARNING,
        QualityState.FINAL_CONSISTENCY_GATE,
        QualityState.ACCEPTED_WITH_WARNING,
    )


def test_preapproved_low_risk_warning_can_skip_record_only_policy_state() -> None:
    _assert_path(
        QualityState.LOGIC_REVIEWING,
        QualityState.LOGIC_CERTIFIED_WITH_WARNING,
        QualityState.LAYOUT_CHECKING,
    )


def test_logic_and_layout_repair_retry_paths_are_explicit() -> None:
    _assert_path(
        QualityState.LOGIC_REVIEWING,
        QualityState.LOGIC_REPAIRING,
        QualityState.LOGIC_VERIFYING,
        QualityState.LOGIC_REPAIRING,
        QualityState.LOGIC_VERIFYING,
        QualityState.LOGIC_CERTIFIED,
        QualityState.LAYOUT_CHECKING,
        QualityState.LAYOUT_REPAIRING,
        QualityState.LAYOUT_VERIFYING,
        QualityState.LAYOUT_REPAIRING,
        QualityState.LAYOUT_VERIFYING,
        QualityState.LAYOUT_CERTIFIED,
    )


def test_every_state_is_explicitly_covered_by_transition_table() -> None:
    assert set(TRANSITIONS) == set(QualityState)
    covered = set(TRANSITIONS)
    for targets in TRANSITIONS.values():
        covered.update(targets)
    assert covered == set(QualityState)


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_terminal_states_have_no_outgoing_transitions(state: QualityState) -> None:
    assert allowed_transitions(state) == frozenset()
    for target in QualityState:
        with pytest.raises(InvalidTransition):
            require_transition(state, target)


def test_same_state_and_unlisted_jump_are_rejected() -> None:
    with pytest.raises(InvalidTransition, match="RECEIVED.*RECEIVED"):
        require_transition(QualityState.RECEIVED, QualityState.RECEIVED)

    with pytest.raises(InvalidTransition, match="RECEIVED.*ACCEPTED"):
        require_transition(QualityState.RECEIVED, QualityState.ACCEPTED)


def test_transition_api_rejects_non_enum_states() -> None:
    with pytest.raises(TypeError, match="state"):
        allowed_transitions("RECEIVED")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="target"):
        require_transition(QualityState.RECEIVED, "INPUT_VALIDATED")  # type: ignore[arg-type]
