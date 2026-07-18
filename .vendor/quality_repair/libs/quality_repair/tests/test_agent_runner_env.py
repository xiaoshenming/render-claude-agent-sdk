import os
from pathlib import Path

import pytest

from libs.quality_repair.agent.runner import ClaudeSDKRunner, _load_persistent_sdk_env


def test_runner_loads_private_persistent_sdk_env(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "sdk.env"
    env_file.write_text(
        "\n".join(
            [
                "export ANTHROPIC_BASE_URL='https://sdk.example.invalid'",
                "ANTHROPIC_API_" "KEY=api-key-value",
                "QUALITY_REPAIR_SDK_MODEL=gemini-3.5-flash-high",
                "UNRELATED_SHOULD_BE_IGNORED=yes",
            ]
        ),
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    _load_persistent_sdk_env(env_file)

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://sdk.example.invalid"
    assert os.environ["ANTHROPIC_API_KEY"] == "api-key-value"
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ
    assert "UNRELATED_SHOULD_BE_IGNORED" not in os.environ


def test_runner_private_env_overrides_inherited_sdk_env(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "sdk.env"
    env_file.write_text("ANTHROPIC_BASE_URL=https://file.example.invalid\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://runtime.example.invalid")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "stale-token")

    _load_persistent_sdk_env(env_file)

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://file.example.invalid"
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ


def test_runner_ignores_private_auth_token_value(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "sdk.env"
    env_file.write_text("ANTHROPIC_AUTH_TOKEN=must-not-be-loaded\nANTHROPIC_API_KEY=api-key-value\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "stale-token")

    _load_persistent_sdk_env(env_file)

    assert os.environ["ANTHROPIC_API_KEY"] == "api-key-value"
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ


def test_runner_rejects_world_readable_persistent_sdk_env(tmp_path: Path):
    env_file = tmp_path / "sdk.env"
    env_file.write_text("ANTHROPIC_API_" "KEY=api-key-value\n", encoding="utf-8")
    env_file.chmod(0o644)

    with pytest.raises(RuntimeError, match="sdk_env_insecure_permissions"):
        _load_persistent_sdk_env(env_file)


def test_runner_name_attribute():
    assert ClaudeSDKRunner.name == "claude_sdk"
