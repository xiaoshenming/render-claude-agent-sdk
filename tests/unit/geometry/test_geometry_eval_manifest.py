import json
from pathlib import Path

import pytest

from evals.run_geometry_inspector_eval import load_selection

SELECTION = (
    Path(__file__).parents[3] / "evals" / "geometry_inspector_v1" / "selection.json"
)


def test_frozen_selection_has_balanced_real_cases_and_no_fix_contamination() -> None:
    selection = load_selection(SELECTION)

    assert selection["frozen"] is True
    cases = selection["cases"]
    assert len(cases) == 22
    assert sum(item["bucket"] == "production_bad" for item in cases) == 11
    assert sum(item["bucket"] == "known_good_control" for item in cases) == 11
    assert len({item["sample_id"] for item in cases}) == 22
    raw = SELECTION.read_text(encoding="utf-8").casefold()
    for forbidden in (
        "visible_error_description",
        "expected_fix",
        "expected_value",
        "move_point",
        "repair_policy",
        "rationale",
        "server_row",
    ):
        assert forbidden not in raw


def test_selection_loader_rejects_mutable_or_malformed_manifests(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "selection.json"
    invalid.write_text(
        json.dumps({"schema_version": "x", "frozen": False, "cases": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_selection(invalid)
