from pathlib import Path

import pytest

from evals._logic_repair_case import CODER_MAX_TURNS
from evals.run_logic_repair_shadow import _arguments


def test_explicit_manifest_replaces_default_packs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = Path("evals/logic_real_mutation_10/manifest.json")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_logic_repair_shadow",
            "--manifest",
            str(explicit),
            "--dataset-root",
            "dataset",
            "--review-root",
            "reviews",
            "--review-report-sha256",
            "0" * 64,
            "--review-bundle-sha256",
            "1" * 64,
            "--output",
            "repairs",
            "--model",
            "test-model",
        ],
    )

    args = _arguments()

    assert args.manifest == [explicit]


def test_coder_turn_budget_supports_multi_location_repairs() -> None:
    assert CODER_MAX_TURNS == 12
