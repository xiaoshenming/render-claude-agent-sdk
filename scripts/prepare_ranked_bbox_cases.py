"""Prepare ranked historical BBox sources for the unified Quality Operator."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path


def main() -> int:
    args = _arguments()
    source_root = args.source.resolve(strict=True)
    output = args.output.resolve()
    rows = list(
        csv.DictReader(
            (source_root / "BBox指标排行榜.csv").open(encoding="utf-8-sig")
        )
    )
    prepared = []
    for row in rows[: args.top]:
        source = (source_root / row["源码文件"]).resolve(strict=True)
        code = source.read_text(encoding="utf-8")
        candidate = _rename_entry_scene(code)
        case_id = row["案例ID"]
        case_root = output / "cases" / case_id
        (case_root / "source").mkdir(parents=True, exist_ok=True)
        (case_root / "assets").mkdir(exist_ok=True)
        target = case_root / "source" / "main.py"
        target.write_text(candidate, encoding="utf-8")
        prepared.append(
            {
                "rank": int(row["排名"]),
                "case_id": case_id,
                "before_blocking": int(row["原始BBox问题数"]),
                "historical_after_blocking": int(row["历史修复后残留"]),
                "source": str(source),
                "source_sha256": hashlib.sha256(code.encode()).hexdigest(),
                "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                "adaptation": "MainScene renamed to Solution",
            }
        )
    (output / "prepared_manifest.json").write_text(
        json.dumps({"count": len(prepared), "items": prepared}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Prepared {len(prepared)} ranked BBox cases at {output}")
    return 0


def _rename_entry_scene(code: str) -> str:
    tree = ast.parse(code)
    candidates = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name != "BaseConfigScene"
        and any(
            isinstance(base, ast.Name) and base.id == "BaseConfigScene"
            for base in node.bases
        )
    ]
    if len(candidates) != 1:
        raise ValueError("source must contain exactly one BaseConfigScene entry")
    scene = candidates[0]
    lines = code.splitlines(keepends=True)
    line = lines[scene.lineno - 1]
    marker = f"class {scene.name}("
    if marker not in line:
        raise ValueError("entry Scene declaration is not a simple class statement")
    lines[scene.lineno - 1] = line.replace(marker, "class Solution(", 1)
    candidate = "".join(lines)
    compile(candidate, "candidate.py", "exec")
    return candidate


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    if args.top <= 0:
        parser.error("--top must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
