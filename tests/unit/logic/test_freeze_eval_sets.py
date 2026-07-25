import json
from pathlib import Path

from scripts.freeze_logic_eval_sets import _freeze_bad, _freeze_good


def test_freeze_good_uses_data_selection_over_unmodified_source_samples(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "manim_test_tool_logic_review_20260708_geo30_shortnames"
    sample = source_root / "samples" / "SOURCE04"
    sample.mkdir(parents=True)
    (source_root / "manifest.json").write_text("{}", encoding="utf-8")
    for name in (
        "candidate.py",
        "problem_text.txt",
        "case_manifest.json",
        "sample_meta.json",
        "before.mp4",
        "expected_solution.txt",
    ):
        (sample / name).write_bytes(name.encode())
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "pack_id": "known-good-v2",
                "samples": [{"sample_id": "GOOD004", "source_sample_id": "SOURCE04"}],
            }
        ),
        encoding="utf-8",
    )

    frozen = _freeze_good(tmp_path, selection)

    assert frozen["pack_id"] == "known-good-v2"
    assert frozen["samples"][0]["sample_id"] == "GOOD004"
    candidate = frozen["samples"][0]["artifacts"]["candidate.py"]
    assert candidate["path"].startswith(
        "manim_test_tool_logic_review_20260708_geo30_shortnames/"
    )


def test_freeze_bad_replaces_tuning_sample_from_independent_pack(
    tmp_path: Path,
) -> None:
    packs = tmp_path / "mutation_eval_packs_20260708"
    primary = packs / "primary"
    replacement = packs / "replacement"
    _bad_sample(primary, "TUNED", aggregate_truth=True)
    _bad_sample(primary, "HOLDOUT", aggregate_truth=True)
    _bad_sample(replacement, "SOURCE_REPLACEMENT", aggregate_truth=False)
    (primary / "evaluation_ground_truth_private.json").write_text(
        json.dumps(
            {
                "TUNED": {
                    "issue_type": "wrong_a",
                    "difficulty": "hard",
                    "line_no": 3,
                },
                "HOLDOUT": {
                    "issue_type": "wrong_b",
                    "difficulty": "hard",
                    "line_no": 5,
                },
            }
        ),
        encoding="utf-8",
    )
    selection = tmp_path / "bad-selection.json"
    selection.write_text(
        json.dumps(
            {
                "pack_id": "bad-holdout-v2",
                "primary_pack": "primary",
                "excluded_tuning_samples": [{"source_sample_id": "TUNED"}],
                "replacement": {
                    "pack": "replacement",
                    "sample_id": "BAD_REPLACEMENT",
                    "source_sample_id": "SOURCE_REPLACEMENT",
                },
            }
        ),
        encoding="utf-8",
    )

    frozen_primary, frozen_replacement = _freeze_bad(tmp_path, selection)

    assert frozen_primary["pack_id"] == "bad-holdout-v2"
    assert [item["sample_id"] for item in frozen_primary["samples"]] == ["HOLDOUT"]
    assert frozen_replacement["sample_count"] == 1
    assert frozen_replacement["samples"][0]["sample_id"] == "BAD_REPLACEMENT"
    assert frozen_replacement["samples"][0]["target_lines"] == [7]


def _bad_sample(pack: Path, sample_id: str, *, aggregate_truth: bool) -> None:
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text("{}", encoding="utf-8")
    sample = pack / "samples" / sample_id
    sample.mkdir(parents=True)
    for name in (
        "candidate.py",
        "original_candidate.py",
        "problem_text.txt",
        "case_manifest.json",
        "sample_meta.json",
        "source_correct.mp4",
    ):
        (sample / name).write_bytes(f"{sample_id}:{name}".encode())
    if not aggregate_truth:
        (sample / "mutation_ground_truth.json").write_text(
            json.dumps(
                {
                    "issue_type": "wrong_replacement",
                    "difficulty": "expert",
                    "line_no": 7,
                }
            ),
            encoding="utf-8",
        )
