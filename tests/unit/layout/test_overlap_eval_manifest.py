import json
from pathlib import Path


def test_overlap_regression_manifest_is_frozen_and_unique() -> None:
    path = Path("evals/overlap_holdout/manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))

    cases = manifest["cases"]
    assert manifest["selection_count"] == 10
    assert manifest["dataset_manifest_sha256"].startswith("sha256:")
    assert len(cases) == 10
    assert len({case["code_sha256"] for case in cases}) == 10
    assert all(case["label"] == "known_bad" for case in cases)
