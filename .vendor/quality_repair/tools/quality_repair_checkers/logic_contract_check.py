#!/usr/bin/env python3
"""Static logic contract checker for quality_repair bundles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.quality_repair_checkers.logic_contract import run_check


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check a candidate.py against logic_contract_context.json.")
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    payload = run_check(code_path=args.code, workdir=args.workdir)
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
