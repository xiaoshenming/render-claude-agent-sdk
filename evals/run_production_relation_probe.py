"""Replay frozen production geometry contracts against candidate code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from manim_quality.logic.expectations.schemas import parse_expected_relation_contract

from ._expected_relation_probe import evaluate_code
from ._production_relation_probe import contract_payload


def main() -> int:
    args = _arguments()
    selected = _read_json(args.selection)["sample_ids"]
    results = [_run_case(args.dataset_root, str(case_id)) for case_id in selected]
    report = {"results": results, "metrics": _metrics(results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


def _run_case(root: Path, case_id: str) -> dict[str, object]:
    matches = sorted(root.glob(f"{case_id}__*"))
    if len(matches) != 1:
        raise ValueError(f"case directory is not unique: {case_id}")
    case = matches[0]
    manifest = _read_json(case / "case_manifest.json")
    raw_contracts = manifest.get("contracts")
    if not isinstance(raw_contracts, list):
        raise ValueError(f"contracts missing: {case_id}")
    payload = contract_payload(case_id, raw_contracts)
    contract = parse_expected_relation_contract(payload)
    code = (case / "candidate.py").read_text(encoding="utf-8-sig")
    evaluation = evaluate_code(code, str(manifest["scene_name"]), contract)
    return {
        "sample_id": case_id,
        "scene_id": manifest["scene_name"],
        "repair_policy": manifest["repair_policy"],
        "evaluation": evaluation.to_dict(),
    }


def _metrics(results: list[dict[str, object]]) -> dict[str, object]:
    statuses = {"satisfied": 0, "contradiction": 0, "unknown": 0}
    flagged = 0
    for result in results:
        evaluation = result["evaluation"]
        assert isinstance(evaluation, dict)
        flagged += int(bool(evaluation["flagged"]))
        counts = evaluation["counts"]
        assert isinstance(counts, dict)
        for status in statuses:
            statuses[status] += int(counts[status])
    return {
        "case_count": len(results),
        "flagged_cases": flagged,
        "case_recall": flagged / len(results) if results else 0.0,
        "claim_counts": statuses,
    }


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path(__file__).parent
        / "production_relation_probe_v1"
        / "selection.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
