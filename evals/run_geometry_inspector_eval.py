"""Run the deterministic Geometry Inspector over a frozen private selection."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path

from manim_quality.geometry.relations import inspect_relation
from manim_quality.geometry.static_index import build_static_geometry_snapshot
from manim_quality.revisions.fingerprint import sha256_bytes

SCHEMA_VERSION = "manim-quality.geometry-inspector-selection.v1"
CASE_FIELDS = frozenset(
    {
        "sample_id",
        "bucket",
        "candidate_path",
        "candidate_sha256",
        "scene_id",
        "relation",
        "operands",
        "expected_status",
        "expected_truth",
    }
)


def load_selection(path: Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("geometry selection must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported geometry selection schema")
    if payload.get("frozen") is not True:
        raise ValueError("geometry selection must be frozen")
    roots = payload.get("roots")
    cases = payload.get("cases")
    if not isinstance(roots, dict) or set(roots) != {
        "production_bad",
        "known_good_control",
    }:
        raise ValueError("geometry selection roots are invalid")
    if not isinstance(cases, list) or not cases:
        raise ValueError("geometry selection requires cases")
    for case in cases:
        _validate_case(case, roots)
    return payload


def evaluate_selection(
    selection: Mapping[str, object], roots: Mapping[str, Path]
) -> dict[str, object]:
    cases = selection["cases"]
    if not isinstance(cases, list):
        raise TypeError("selection cases must be an array")
    results = [_evaluate_case(item, roots) for item in cases]
    known = [item for item in results if item["actual_status"] == "known"]
    wrong_known = [item for item in known if item["matches_private_truth"] is False]
    return {
        "schema_version": "manim-quality.geometry-inspector-report.v1",
        "pack_id": selection["pack_id"],
        "case_count": len(results),
        "known_count": len(known),
        "unknown_count": len(results) - len(known),
        "support_rate": len(known) / len(results),
        "wrong_known_count": len(wrong_known),
        "known_accuracy": (
            1.0 if not known else (len(known) - len(wrong_known)) / len(known)
        ),
        "results": results,
    }


def _evaluate_case(case: object, roots: Mapping[str, Path]) -> dict[str, object]:
    if not isinstance(case, dict):
        raise TypeError("geometry case must be an object")
    root = Path(roots[case["bucket"]]).resolve(strict=True)
    candidate = (root / case["candidate_path"]).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("geometry candidate escapes declared root")
    source = candidate.read_bytes()
    if sha256_bytes(source) != case["candidate_sha256"]:
        raise ValueError(f"candidate hash mismatch: {case['sample_id']}")
    code = source.decode("utf-8")
    started = time.perf_counter()
    snapshot = build_static_geometry_snapshot(code, scene_id=case["scene_id"])
    fact = inspect_relation(snapshot, case["relation"], case["operands"])
    elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
    matches = (
        fact.status.value == case["expected_status"]
        and fact.truth is case["expected_truth"]
    )
    return {
        "sample_id": case["sample_id"],
        "bucket": case["bucket"],
        "relation": case["relation"],
        "actual_status": fact.status.value,
        "actual_truth": fact.truth,
        "reason_code": fact.reason_code,
        "matches_private_truth": matches,
        "code_hash": snapshot.code_hash,
        "snapshot_hash": snapshot.snapshot_hash,
        "elapsed_ms": elapsed_ms,
    }


def _validate_case(case: object, roots: Mapping[str, object]) -> None:
    if not isinstance(case, dict) or set(case) != CASE_FIELDS:
        raise ValueError("geometry case fields do not match contract")
    for field in (
        "sample_id",
        "bucket",
        "candidate_path",
        "candidate_sha256",
        "scene_id",
        "relation",
        "expected_status",
    ):
        if not isinstance(case[field], str) or not case[field].strip():
            raise ValueError(f"geometry case {field} must be non-empty text")
    if case["bucket"] not in roots:
        raise ValueError("geometry case bucket is unsupported")
    _validate_case_path(case["candidate_path"])
    _validate_operands(case["operands"])
    _validate_expected(case["expected_status"], case["expected_truth"])


def _validate_case_path(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("geometry candidate path must be text")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("geometry candidate path must be safe and relative")


def _validate_operands(operands: object) -> None:
    if not isinstance(operands, list) or not 1 <= len(operands) <= 4:
        raise ValueError("geometry case operands are invalid")
    if any(not isinstance(item, str) or not item.strip() for item in operands):
        raise ValueError("geometry case operand IDs are invalid")


def _validate_expected(status: object, truth: object) -> None:
    if status not in {"known", "unknown"}:
        raise ValueError("geometry expected status is invalid")
    if status == "known":
        if type(truth) is not bool:
            raise ValueError("known geometry case requires boolean truth")
    elif truth is not None:
        raise ValueError("unknown geometry case requires null truth")


def main() -> int:
    parser = argparse.ArgumentParser()
    default = Path(__file__).with_name("geometry_inspector_v1") / "selection.json"
    parser.add_argument("--selection", type=Path, default=default)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--control-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    selection = load_selection(args.selection)
    roots = {
        "production_bad": _root(args.production_root, "MANIM_GEOMETRY_PRODUCTION_ROOT"),
        "known_good_control": _root(args.control_root, "MANIM_GEOMETRY_CONTROL_ROOT"),
    }
    report = evaluate_selection(selection, roots)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0 if report["wrong_known_count"] == 0 else 1


def _root(value: Path | None, env_name: str) -> Path:
    raw = value or os.environ.get(env_name)
    if not raw:
        raise SystemExit(f"--root or {env_name} is required")
    return Path(raw).resolve(strict=True)


if __name__ == "__main__":
    raise SystemExit(main())
