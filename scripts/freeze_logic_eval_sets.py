"""Freeze external logic evaluation packs into hash-only repository manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "manim-quality.logic-eval.v1"
ROOT_ENV = "MANIM_LOGIC_EVAL_PACKS_ROOT"
GOOD_SOURCE_ROOT = "manim_test_tool_logic_review_20260708_geo30_shortnames"
MUTATION_PACKS_ROOT = "mutation_eval_packs_20260708"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packs-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--good-selection",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "evals"
            / "logic_known_good"
            / "selection.json"
        ),
    )
    parser.add_argument(
        "--bad-selection",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "evals"
            / "logic_known_bad"
            / "selection.json"
        ),
    )
    args = parser.parse_args()
    packs_root = args.packs_root.resolve(strict=True)
    output_root = args.output_root.resolve()
    good = _freeze_good(packs_root, args.good_selection.resolve(strict=True))
    bad, bad_replacement = _freeze_bad(
        packs_root, args.bad_selection.resolve(strict=True)
    )
    _write(output_root / "logic_known_good" / "manifest.json", good)
    _write(output_root / "logic_known_bad" / "manifest.json", bad)
    _write(
        output_root / "logic_known_bad_replacement" / "manifest.json",
        bad_replacement,
    )
    return 0


def _freeze_good(root: Path, selection_path: Path) -> dict[str, object]:
    pack = root / GOOD_SOURCE_ROOT
    source_manifest = pack / "manifest.json"
    selection = _read_object(selection_path)
    samples = []
    for item in _array(selection.get("samples"), "known-good selection"):
        sample_id = _text(item.get("sample_id"), "sample_id")
        source_sample_id = _text(item.get("source_sample_id"), "source_sample_id")
        sample_dir = pack / "samples" / source_sample_id
        artifacts = _artifacts(
            root,
            sample_dir,
            (
                "candidate.py",
                "problem_text.txt",
                "case_manifest.json",
                "sample_meta.json",
                "before.mp4",
            ),
        )
        artifacts["expected_solution.txt"] = _optional_artifact(
            root, sample_dir / "expected_solution.txt"
        )
        samples.append(
            {
                "sample_id": sample_id,
                "truth": "known_good",
                "artifacts": artifacts,
            }
        )
    return _manifest(
        pack_id=_text(selection.get("pack_id"), "pack_id"),
        truth="known_good",
        source_manifest=_artifact(root, source_manifest),
        samples=samples,
    )


def _freeze_bad(
    root: Path, selection_path: Path
) -> tuple[dict[str, object], dict[str, object]]:
    selection = _read_object(selection_path)
    primary_name = _text(selection.get("primary_pack"), "primary_pack")
    pack = root / MUTATION_PACKS_ROOT / primary_name
    source_manifest = pack / "manifest.json"
    truth_file = pack / "evaluation_ground_truth_private.json"
    truth = _read_object(truth_file)
    excluded = {
        _text(item.get("source_sample_id"), "excluded source_sample_id")
        for item in _array(
            selection.get("excluded_tuning_samples"),
            "excluded_tuning_samples",
        )
    }
    samples = []
    for sample_id, label in sorted(truth.items()):
        if sample_id in excluded:
            continue
        label_data = _object(label, f"ground truth {sample_id}")
        sample_dir = pack / "samples" / sample_id
        samples.append(_bad_sample(root, sample_dir, sample_id, label_data))
    manifest = _manifest(
        pack_id=_text(selection.get("pack_id"), "pack_id"),
        truth="known_bad",
        source_manifest=_artifact(root, source_manifest),
        samples=samples,
    )
    manifest["private_ground_truth"] = _artifact(root, truth_file)
    replacement = _freeze_bad_replacement(root, selection)
    return manifest, replacement


def _freeze_bad_replacement(
    root: Path, selection: dict[str, object]
) -> dict[str, object]:
    item = _object(selection.get("replacement"), "replacement")
    pack_name = _text(item.get("pack"), "replacement.pack")
    source_sample_id = _text(
        item.get("source_sample_id"), "replacement.source_sample_id"
    )
    sample_id = _text(item.get("sample_id"), "replacement.sample_id")
    pack = root / MUTATION_PACKS_ROOT / pack_name
    sample_dir = pack / "samples" / source_sample_id
    truth_file = sample_dir / "mutation_ground_truth.json"
    truth = _read_object(truth_file)
    manifest = _manifest(
        pack_id=f"{pack_name}-replacement-holdout",
        truth="known_bad",
        source_manifest=_artifact(root, pack / "manifest.json"),
        samples=[_bad_sample(root, sample_dir, sample_id, truth)],
    )
    manifest["private_ground_truth"] = _artifact(root, truth_file)
    return manifest


def _bad_sample(
    root: Path,
    sample_dir: Path,
    sample_id: str,
    label: dict[str, object],
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "truth": "known_bad",
        "expected_issue_type": _text(label.get("issue_type"), "issue_type"),
        "difficulty": _text(label.get("difficulty"), "difficulty"),
        "target_lines": [_positive_int(label.get("line_no"), "line_no")],
        "artifacts": _artifacts(
            root,
            sample_dir,
            (
                "candidate.py",
                "original_candidate.py",
                "problem_text.txt",
                "case_manifest.json",
                "sample_meta.json",
                "source_correct.mp4",
            ),
        ),
    }


def _manifest(
    *,
    pack_id: str,
    truth: str,
    source_manifest: dict[str, str],
    samples: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack_id,
        "truth": truth,
        "frozen": True,
        "dataset_root_env": ROOT_ENV,
        "source_manifest": source_manifest,
        "sample_count": len(samples),
        "samples": samples,
    }


def _artifacts(
    root: Path, sample_dir: Path, names: tuple[str, ...]
) -> dict[str, object]:
    return {name: _artifact(root, sample_dir / name) for name in names}


def _artifact(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError(f"artifact escapes pack root: {path}")
    return {
        "path": resolved.relative_to(root).as_posix(),
        "sha256": _sha256(resolved),
    }


def _optional_artifact(root: Path, path: Path) -> dict[str, str] | None:
    return _artifact(root, path) if path.is_file() else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_object(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8-sig")), str(path))


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{name} must be a JSON object")
    return value


def _array(value: object, name: str) -> list[dict[str, object]]:
    if type(value) is not list or not all(type(item) is dict for item in value):
        raise TypeError(f"{name} must be an array of objects")
    return value


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
