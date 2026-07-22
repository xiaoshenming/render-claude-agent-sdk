from manim_quality.layout.runtime_policy import (
    OVERLAP_MAX_ROUNDS,
    OVERLAP_NO_PROGRESS_STOP,
    remaining_rounds,
)


def test_overlap_runtime_limits_have_one_five_round_contract() -> None:
    assert OVERLAP_MAX_ROUNDS == 5
    assert OVERLAP_NO_PROGRESS_STOP == 2
    assert remaining_rounds(0) == 5
    assert remaining_rounds(1) == 4
    assert remaining_rounds(3) == 2
    assert remaining_rounds(5) == 0
