from dataclasses import FrozenInstanceError

import pytest

from manim_quality.agents.tool_policy import ToolInputPolicy


def test_tool_input_policy_is_immutable_and_validates_bounded_shape() -> None:
    policy = ToolInputPolicy(
        max_calls=1,
        required_fields=("offset", "limit"),
        integer_maximums={"limit": 220},
    )

    policy.validate({"file_path": "candidate.py", "offset": 10, "limit": 150})
    with pytest.raises(ValueError, match="required"):
        policy.validate({"file_path": "candidate.py"})
    with pytest.raises(ValueError, match="limit"):
        policy.validate({"file_path": "candidate.py", "offset": 1, "limit": 221})
    with pytest.raises(FrozenInstanceError):
        policy.max_calls = 2  # type: ignore[misc]


@pytest.mark.parametrize("max_calls", [0, -1, True])
def test_tool_input_policy_rejects_invalid_call_limits(max_calls) -> None:
    with pytest.raises(ValueError):
        ToolInputPolicy(max_calls=max_calls)


def test_tool_input_policy_can_explicitly_clamp_safe_integer_maximums() -> None:
    policy = ToolInputPolicy(
        max_calls=1,
        integer_maximums={"limit": 160},
        clamp_integer_maximums=True,
    )

    normalized = policy.normalize({"file_path": "candidate.py", "limit": 500})

    assert normalized["limit"] == 160
    assert normalized["file_path"] == "candidate.py"
