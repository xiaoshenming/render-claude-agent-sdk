#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from manim_quality.math_final.calibration import calculate_metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    verdicts = {}
    for path in args.results.glob("*/result-v2.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        verdicts[row["key"]] = row["verdict"]
    metrics = calculate_metrics(labels, verdicts).as_dict()
    metrics["targets"] = {
        "precision": 0.95,
        "recall": 0.95,
        "false_positive_rate": 0.03,
    }
    metrics["qualified"] = (
        metrics["precision"] >= 0.95
        and metrics["recall"] >= 0.95
        and metrics["false_positive_rate"] <= 0.03
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
