from pathlib import Path

import pytest

from manim_quality.operator.cli import (
    _arguments,
    _json_input,
    _problem_identity,
    _provider_environment,
)


def test_cli_arguments_require_candidate_output_and_model(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text('"""Problem."""\npass\n', encoding="utf-8")

    args = _arguments(
        [
            "--candidate",
            str(candidate),
            "--workspace",
            str(tmp_path),
            "--output",
            str(tmp_path / "run"),
            "--model",
            "model-a",
        ]
    )

    assert args.candidate == candidate
    assert args.model == "model-a"
    assert args.max_turns == 24
    assert args.max_tool_calls == 40


def test_cli_reads_structured_solution_steps_and_repair_feedback(
    tmp_path: Path,
) -> None:
    feedback = tmp_path / "repair_feedback.json"
    feedback.write_text('{"issue_id":"FA-1"}', encoding="utf-8")
    assert _json_input(feedback) == {"issue_id": "FA-1"}

    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="JSON object"):
        _json_input(malformed)


def test_provider_environment_requires_authentication() -> None:
    with pytest.raises(SystemExit, match="authentication"):
        _provider_environment({"ANTHROPIC_BASE_URL": "https://example.invalid"})


def test_provider_environment_returns_only_supported_values() -> None:
    assert _provider_environment(
        {
            "ANTHROPIC_BASE_URL": "https://gateway.example",
            "ANTHROPIC_AUTH_TOKEN": "secret",
            "UNRELATED": "ignored",
        }
    ) == {
        "ANTHROPIC_BASE_URL": "https://gateway.example",
        "ANTHROPIC_AUTH_TOKEN": "secret",
    }


def test_provider_environment_does_not_mix_api_key_and_stale_token() -> None:
    assert _provider_environment(
        {
            "ANTHROPIC_BASE_URL": "https://gateway.example",
            "ANTHROPIC_API_KEY": "current-key",
            "ANTHROPIC_AUTH_TOKEN": "stale-token",
        }
    ) == {
        "ANTHROPIC_BASE_URL": "https://gateway.example",
        "ANTHROPIC_API_KEY": "current-key",
        "ANTHROPIC_AUTH_TOKEN": "",
    }


def test_problem_identity_falls_back_to_solution_hash() -> None:
    candidate = (
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        self.wait()\n"
    )

    assert _problem_identity(candidate, None).startswith(
        "solution-source:sha256:"
    )


def test_clean_environment_requires_explicit_ambient_opt_in() -> None:
    with pytest.raises(SystemExit, match="ambient"):
        _provider_environment({"UNRELATED": "ignored"})
    assert _provider_environment({"UNRELATED": "ignored"}, allow_ambient=True) == {}
