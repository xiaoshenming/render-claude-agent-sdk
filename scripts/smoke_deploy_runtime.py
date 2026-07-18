"""Fail-fast smoke check for a deployable quality-platform checkout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _add_source_roots() -> None:
    for path in (
        ROOT / "src",
        ROOT,
        ROOT / "vendor" / "logic_engine_mvp_baseline",
    ):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def main() -> int:
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        print("FAIL: Python 3.11 or 3.12 is required", file=sys.stderr)
        return 1

    _add_source_roots()

    from tools.logic_engine_mvp.logic_engine_mvp.logic_facts import (
        extract_deterministic_logic_facts,
    )

    from manim_quality.layout.vendor_runtime import MaterializedQualityRepair

    facts = extract_deterministic_logic_facts("from manim import *\n")
    if not isinstance(facts, dict):
        print("FAIL: logic_engine_mvp returned an invalid payload", file=sys.stderr)
        return 1

    quality_root = ROOT / ".vendor" / "quality_repair"
    backend = MaterializedQualityRepair(quality_root)
    print(f"PASS: Python {sys.version_info.major}.{sys.version_info.minor}")
    print("PASS: manim_quality imported")
    print("PASS: logic_engine_mvp imported and executed")
    print(f"PASS: quality_repair verified and loaded from {quality_root}")
    print(f"PASS: quality_repair API module is {backend.api.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
