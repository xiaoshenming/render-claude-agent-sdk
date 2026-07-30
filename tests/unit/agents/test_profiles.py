from dataclasses import FrozenInstanceError

import pytest

from manim_quality.agents.profile import (
    AgentProfile,
    AgentRole,
    coder_profile,
    operator_profile,
    reviewer_profile,
    verifier_profile,
)


def test_role_profiles_expose_only_required_builtin_tools() -> None:
    reviewer = reviewer_profile(model="test-model", prompt_version="review-v1")
    coder = coder_profile(model="test-model", prompt_version="coder-v1")
    verifier = verifier_profile(model="test-model", prompt_version="verify-v1")

    assert reviewer.allowed_tools == frozenset({"Read"})
    assert coder.allowed_tools == frozenset({"Read", "Edit"})
    assert verifier.allowed_tools == frozenset({"Read"})
    assert not {"Bash", "Write", "Agent", "Task", "Web", "Upload"}.intersection(
        reviewer.allowed_tools | coder.allowed_tools | verifier.allowed_tools
    )
    with pytest.raises(FrozenInstanceError):
        reviewer.model = "changed"  # type: ignore[misc]


def test_profile_versions_and_model_must_be_explicit() -> None:
    with pytest.raises(ValueError):
        reviewer_profile(model="", prompt_version="review-v1")
    with pytest.raises(ValueError):
        coder_profile(model="test-model", prompt_version="")
    with pytest.raises(ValueError, match="do not match"):
        AgentProfile(
            role=AgentRole.REVIEWER,
            model="test-model",
            prompt_version="v1",
            schema_version="schema-v1",
            tool_version="tools-v1",
            allowed_tools=frozenset({"Read", "Edit"}),
        )


def test_operator_profile_exposes_native_read_and_edit() -> None:
    operator = operator_profile(
        model="model-a",
        prompt_version="quality-operator-v1",
    )

    assert operator.role is AgentRole.OPERATOR
    assert operator.allowed_tools == frozenset({"Read", "Edit"})
