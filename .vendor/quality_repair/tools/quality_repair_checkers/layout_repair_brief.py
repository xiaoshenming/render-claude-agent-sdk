#!/usr/bin/env python3
"""Build repair-oriented layout brief/contract payloads from layout_context JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.quality_repair_checkers.layout_repair_brief_model import (  # noqa: E402
    build_agent_safety_contract,
    build_layout_issue_digest,
    build_layout_repair_brief,
    build_layout_repair_contract,
)
from tools.quality_repair_checkers.layout_repair_brief_report import (  # noqa: E402
    parse_args,
    run_batch,
    run_single,
)

__all__ = [
    "build_agent_safety_contract",
    "build_layout_issue_digest",
    "build_layout_repair_brief",
    "build_layout_repair_contract",
    "main",
    "parse_args",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.layout_context:
            payload = run_single(args.layout_context, args.out_dir)
        else:
            payload = run_batch(args.batch_root, args.out_dir, args.batch_tag)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI emits machine-readable failure
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
