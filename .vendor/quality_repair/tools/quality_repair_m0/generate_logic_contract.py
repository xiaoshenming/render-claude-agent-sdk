#!/usr/bin/env python3
"""Generate logic_contract_context.json from Manim source deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from libs.quality_repair.semantic_contract import generate_logic_contract


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = generate_logic_contract(args.code, manifest_path=args.manifest)
        result.write_to(args.out)
        print(
            json.dumps(
                {
                    "ok": True,
                    "contracts": len(result.logic_contract.get("contracts") or []),
                    "findings": len(result.findings),
                    "out": str(args.out),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured JSON
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
