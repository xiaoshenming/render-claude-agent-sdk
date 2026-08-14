import json

from manim_quality.assurance.models import ToolReport
from manim_quality.assurance.risk_frames import _sample_times, text_evidence


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


def test_risk_frame_tool_returns_text_without_image_blocks(tmp_path) -> None:
    image = tmp_path / "contact.jpg"
    image.write_bytes(b"not-sent-to-model")
    report = ToolReport(
        "inspect_risk_frames",
        "complete",
        (),
        ({"id": "CASE:risk-frames", "sample_count": 12},),
        (str(image),),
    )

    result = text_evidence(report)

    assert isinstance(result, str)
    assert json.loads(result)["evidence"][0]["sample_count"] == 12
    assert "not-sent-to-model" not in result
    assert '"type": "image"' not in result
