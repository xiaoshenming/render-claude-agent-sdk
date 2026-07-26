from pathlib import Path

import pytest

from manim_quality.operator.cli import (
    _arguments,
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
    assert args.max_tool_calls == 32


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
