"""Run the bundled generation-to-quality Workbench with relative package paths."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--round", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--slot", action="append")
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--all-items", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("QUALITY_MODEL"))
    return parser.parse_args()


def _key() -> str:
    for name in ("MANIM_E2E_API_KEY", "MANIM_QUALITY_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise SystemExit("model API key is required; see config.env.example")


def main() -> int:
    args = _arguments()
    if not args.base_url or not args.model:
        raise SystemExit("ANTHROPIC_BASE_URL and QUALITY_MODEL are required")
    command = [
        sys.executable,
        "-m",
        "evals.run_workbench_e2e",
        "--round",
        str(args.round),
        "--workers",
        str(args.workers),
        "--output",
        str(args.output.resolve()),
        "--workload",
        str(ROOT / "handoff_data/workload_v1.json"),
        "--prompt-database",
        str(ROOT / "handoff_data/prompts_minimal.sqlite3"),
        "--manim-python",
        str(args.manim_python.resolve(strict=True)),
        "--probe-source",
        str(ROOT / "external/layout_probe/probe_runner.py"),
        "--vendor-root",
        str(ROOT / ".vendor/quality_repair"),
        "--base-url",
        args.base_url,
        "--model",
        args.model,
    ]
    if args.all_items:
        command.append("--all-items")
    else:
        for slot in dict.fromkeys(args.slot or ["slot-001"]):
            command.extend(("--slot", slot))
    env = dict(os.environ)
    env["MANIM_E2E_API_KEY"] = _key()
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
