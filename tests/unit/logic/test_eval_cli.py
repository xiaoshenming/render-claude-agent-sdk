from pathlib import Path

import pytest

from evals.run_logic_reviewer_shadow import _arguments, _provider_environment


def test_default_manifests_include_independent_bad_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["run_logic_reviewer_shadow"])

    args = _arguments()

    assert [Path(path).parent.name for path in args.manifest] == [
        "logic_known_bad",
        "logic_known_bad_replacement",
        "logic_known_good",
    ]


def test_explicit_manifest_replaces_default_packs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = Path("evals/logic_real_mutation_10/manifest.json")
    monkeypatch.setattr(
        "sys.argv",
        ["run_logic_reviewer_shadow", "--manifest", str(explicit)],
    )

    args = _arguments()

    assert args.manifest == [explicit]


def test_provider_environment_requires_authentication() -> None:
    with pytest.raises(SystemExit, match="provider authentication"):
        _provider_environment({"ANTHROPIC_BASE_URL": "https://gateway.example"})


def test_provider_environment_returns_only_supported_non_empty_values() -> None:
    environment = _provider_environment(
        {
            "ANTHROPIC_BASE_URL": "https://gateway.example",
            "ANTHROPIC_AUTH_TOKEN": "secret-value",
            "UNRELATED": "must-not-propagate",
        }
    )

    assert environment == {
        "ANTHROPIC_BASE_URL": "https://gateway.example",
        "ANTHROPIC_AUTH_TOKEN": "secret-value",
    }


def test_provider_environment_accepts_official_api_key_without_gateway() -> None:
    assert _provider_environment({"ANTHROPIC_API_KEY": "secret-value"}) == {
        "ANTHROPIC_API_KEY": "secret-value"
    }
