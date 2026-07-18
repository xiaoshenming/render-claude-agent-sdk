from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .workbench_e2e.generation import GenerationClient, GenerationConfig
from .workbench_e2e.job_runner import JobConfig, run_job
from .workbench_e2e.layout_stage import LayoutStageConfig
from .workbench_e2e.logic_stage import LogicStageConfig
from .workbench_e2e.prompt_source import PromptSource
from .workbench_e2e.rendering import LocalManimRenderer
from .workbench_e2e.reporting import build_report
from .workbench_e2e.workload import (
    WORKLOAD_PATH,
    full_slots,
    load_workload,
    round_slots,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = _arguments()
    if not args.base_url or not args.model:
        raise SystemExit("ANTHROPIC_BASE_URL and QUALITY_MODEL are required")
    key = os.environ.get("MANIM_E2E_API_KEY", "").strip()
    if not key:
        raise SystemExit("MANIM_E2E_API_KEY is required")
    provider = {
        "ANTHROPIC_BASE_URL": args.base_url,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
    }
    config = JobConfig(
        output_root=args.output.resolve(),
        prompt_source=PromptSource(args.prompt_database),
        generation=GenerationClient(
            GenerationConfig(args.base_url, key, args.model, args.generation_tokens)
        ),
        renderer=LocalManimRenderer(python=str(args.manim_python)),
        logic=LogicStageConfig(args.model, provider),
        layout=LayoutStageConfig(
            python=str(args.manim_python),
            probe_source_path=args.probe_source,
            vendor_root=args.vendor_root,
            model=args.model,
            provider_env=provider,
        ),
    )
    workload = load_workload(args.workload)
    slots = list(
        full_slots(workload, args.round)
        if args.all_items
        else round_slots(workload, args.round)
    )
    if args.slot:
        slots = [slot for slot in slots if slot.slot_id in set(args.slot)]
    config.output_root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_job, slot, config): slot for slot in slots}
        for future in as_completed(futures):
            result = future.result()
            print(f"{result['slot_id']}: {result['status']}", flush=True)
            build_report(config.output_root)
    report = build_report(config.output_root)
    print(
        f"jobs={report['job_count']} "
        f"strict={report['strict_delivery_count']} "
        f"warning={report['warning_release_count']} "
        f"quality_release={report['quality_release_count']} "
        f"tokens={report['total_tokens']}"
    )
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--slot", action="append")
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workload", type=Path, default=WORKLOAD_PATH)
    parser.add_argument("--all-items", action="store_true")
    parser.add_argument(
        "--base-url", default=os.environ.get("ANTHROPIC_BASE_URL", "")
    )
    parser.add_argument("--model", default=os.environ.get("QUALITY_MODEL", ""))
    parser.add_argument("--generation-tokens", type=int, default=32_000)
    parser.add_argument(
        "--prompt-database",
        type=Path,
        default=ROOT / "handoff_data" / "prompts_minimal.sqlite3",
    )
    parser.add_argument(
        "--manim-python",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--probe-source",
        type=Path,
        default=ROOT / "external" / "layout_probe" / "probe_runner.py",
    )
    parser.add_argument(
        "--vendor-root", type=Path, default=ROOT / ".vendor" / "quality_repair"
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
