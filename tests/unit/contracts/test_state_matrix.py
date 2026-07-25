from __future__ import annotations

import pytest

from manim_quality.contracts import (
    TRANSITIONS,
    InvalidTransition,
    QualityState,
    allowed_transitions,
    require_transition,
)

EXPECTED_STATES = frozenset(
    {
        "RECEIVED",
        "INPUT_VALIDATED",
        "BASELINE_READY",
        "LOGIC_REVIEWING",
        "POLICY_EVALUATING",
        "LOGIC_REPAIRING",
        "LOGIC_VERIFYING",
        "LOGIC_CERTIFIED",
        "LOGIC_CERTIFIED_WITH_WARNING",
        "LAYOUT_CHECKING",
        "LAYOUT_REPAIRING",
        "LAYOUT_VERIFYING",
        "LAYOUT_CERTIFIED",
        "LAYOUT_CERTIFIED_WITH_WARNING",
        "FINAL_CONSISTENCY_GATE",
        "ACCEPTED",
        "ACCEPTED_WITH_WARNING",
        "REGENERATE",
        "HOLD",
        "FAILED",
    }
)

EXPECTED_TRANSITIONS = {
    "RECEIVED": frozenset({"INPUT_VALIDATED", "FAILED"}),
    "INPUT_VALIDATED": frozenset({"BASELINE_READY", "REGENERATE", "HOLD", "FAILED"}),
    "BASELINE_READY": frozenset({"LOGIC_REVIEWING", "REGENERATE", "HOLD", "FAILED"}),
    "LOGIC_REVIEWING": frozenset(
        {
            "POLICY_EVALUATING",
            "LOGIC_REPAIRING",
            "LOGIC_CERTIFIED",
            "LOGIC_CERTIFIED_WITH_WARNING",
            "REGENERATE",
            "HOLD",
            "FAILED",
        }
    ),
    "POLICY_EVALUATING": frozenset(
        {"LOGIC_CERTIFIED_WITH_WARNING", "REGENERATE", "HOLD", "FAILED"}
    ),
    "LOGIC_REPAIRING": frozenset({"LOGIC_VERIFYING", "REGENERATE", "HOLD", "FAILED"}),
    "LOGIC_VERIFYING": frozenset(
        {"LOGIC_REPAIRING", "LOGIC_CERTIFIED", "REGENERATE", "HOLD", "FAILED"}
    ),
    "LOGIC_CERTIFIED": frozenset({"LAYOUT_CHECKING", "REGENERATE", "HOLD", "FAILED"}),
    "LOGIC_CERTIFIED_WITH_WARNING": frozenset(
        {"LAYOUT_CHECKING", "REGENERATE", "HOLD", "FAILED"}
    ),
    "LAYOUT_CHECKING": frozenset(
        {
            "LAYOUT_REPAIRING",
            "LAYOUT_CERTIFIED",
            "LAYOUT_CERTIFIED_WITH_WARNING",
            "REGENERATE",
            "HOLD",
            "FAILED",
        }
    ),
    "LAYOUT_REPAIRING": frozenset({"LAYOUT_VERIFYING", "REGENERATE", "HOLD", "FAILED"}),
    "LAYOUT_VERIFYING": frozenset(
        {
            "LAYOUT_REPAIRING",
            "LAYOUT_CERTIFIED",
            "LAYOUT_CERTIFIED_WITH_WARNING",
            "REGENERATE",
            "HOLD",
            "FAILED",
        }
    ),
    "LAYOUT_CERTIFIED": frozenset(
        {"FINAL_CONSISTENCY_GATE", "REGENERATE", "HOLD", "FAILED"}
    ),
    "LAYOUT_CERTIFIED_WITH_WARNING": frozenset(
        {"FINAL_CONSISTENCY_GATE", "REGENERATE", "HOLD", "FAILED"}
    ),
    "FINAL_CONSISTENCY_GATE": frozenset(
        {"ACCEPTED", "ACCEPTED_WITH_WARNING", "REGENERATE", "HOLD", "FAILED"}
    ),
    "ACCEPTED": frozenset(),
    "ACCEPTED_WITH_WARNING": frozenset(),
    "REGENERATE": frozenset(),
    "HOLD": frozenset(),
    "FAILED": frozenset(),
}

EXPECTED_TERMINALS = frozenset(
    {"ACCEPTED", "ACCEPTED_WITH_WARNING", "REGENERATE", "HOLD", "FAILED"}
)

EXPECTED_ALLOWED_EDGES = tuple(
    (source, target)
    for source, targets in EXPECTED_TRANSITIONS.items()
    for target in targets
)
EXPECTED_REJECTED_EDGES = tuple(
    (source, target)
    for source in EXPECTED_STATES
    for target in EXPECTED_STATES
    if target not in EXPECTED_TRANSITIONS[source]
)


def test_quality_state_members_match_independent_specification() -> None:
    assert set(QualityState.__members__) == EXPECTED_STATES
    assert {state.value for state in QualityState} == EXPECTED_STATES


def test_transition_table_matches_independent_complete_matrix() -> None:
    actual = {
        source.value: frozenset(target.value for target in targets)
        for source, targets in TRANSITIONS.items()
    }

    assert actual == EXPECTED_TRANSITIONS


@pytest.mark.parametrize(("source", "target"), EXPECTED_ALLOWED_EDGES)
def test_every_expected_transition_is_allowed(source: str, target: str) -> None:
    assert require_transition(QualityState(source), QualityState(target)) is None


@pytest.mark.parametrize(("source", "target"), EXPECTED_REJECTED_EDGES)
def test_every_unlisted_transition_is_rejected(source: str, target: str) -> None:
    with pytest.raises(InvalidTransition):
        require_transition(QualityState(source), QualityState(target))


@pytest.mark.parametrize("terminal", EXPECTED_TERMINALS)
def test_all_and_only_expected_terminal_states_have_no_outgoing_edges(
    terminal: str,
) -> None:
    assert allowed_transitions(QualityState(terminal)) == frozenset()
    assert {
        state for state, targets in EXPECTED_TRANSITIONS.items() if not targets
    } == EXPECTED_TERMINALS


def test_received_can_fail_before_input_validation() -> None:
    assert require_transition(QualityState.RECEIVED, QualityState.FAILED) is None


@pytest.mark.parametrize("terminal", EXPECTED_TERMINALS)
def test_final_gate_reaches_every_terminal_decision(terminal: str) -> None:
    assert (
        require_transition(
            QualityState.FINAL_CONSISTENCY_GATE,
            QualityState(terminal),
        )
        is None
    )


@pytest.mark.parametrize(
    "repair_state",
    ["LOGIC_REPAIRING", "LOGIC_VERIFYING", "LAYOUT_REPAIRING", "LAYOUT_VERIFYING"],
)
@pytest.mark.parametrize("stop_state", ["REGENERATE", "HOLD", "FAILED"])
def test_repair_paths_can_stop_explicitly(
    repair_state: str,
    stop_state: str,
) -> None:
    assert (
        require_transition(QualityState(repair_state), QualityState(stop_state)) is None
    )
