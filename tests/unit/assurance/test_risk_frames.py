from manim_quality.assurance.risk_frames import _sample_times


def test_risk_frame_sampling_prioritizes_black_windows() -> None:
    times = _sample_times(
        100.0,
        {
            "black": [{"start": 20.0, "end": 24.0}],
            "freeze": [{"start": 60.0, "end": 80.0}],
        },
    )

    assert len(times) == 12
    assert 20.0 in times
    assert 22.0 in times
    assert 24.0 in times
    assert 70.0 in times


def test_risk_frame_sampling_is_bounded_and_unique() -> None:
    times = _sample_times(1.0, {"black": [], "freeze": []})

    assert times == sorted(set(times))
    assert len(times) == 12
    assert all(0.0 <= value <= 1.0 for value in times)
