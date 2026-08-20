"""Standalone CLI for evidence-only figure fidelity quantification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage_ledger import RecordingJsonlUsageLedger

from .cli import _provider_environment
from .figure_fidelity import run_figure_fidelity_reviewer


def main(argv=None) -> int:
    args = _arguments(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.base_url:
        os.environ["ANTHROPIC_BASE_URL"] = args.base_url
    sink = RecordingJsonlUsageLedger(output / "usage-events.jsonl")
    runtime = AgentRuntime(
        ClaudeSdkBackend(provider_env=_provider_environment(os.environ)),
        sink,
        _limits(),
    )
    result, record = run_figure_fidelity_reviewer(
        runtime,
        candidate_path=args.candidate.resolve(strict=True),
        figure_path=args.figure.resolve(strict=True),
        problem_text=args.problem.resolve(strict=True).read_text(encoding="utf-8"),
        solution_steps=(
            args.solution_steps.resolve(strict=True).read_text(encoding="utf-8")
            if args.solution_steps else ""
        ),
        model=args.model,
        effort=args.effort,
    )
    if result is None or record is None:
        raise SystemExit("confirmed figure is unavailable")
    payload = {
        **result,
        "source": str(args.figure.resolve()),
        "candidate": str(args.candidate.resolve()),
        "tokens": record.usage.total_tokens,
    }
    (output / "figure-fidelity.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare confirmed figure.py with a final Solution using code only."
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    parser.add_argument("--problem", type=Path, required=True)
    parser.add_argument("--solution-steps", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--effort", choices=("low", "medium"), default="low")
    return parser.parse_args(argv)


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=2_000_000,
        max_turns=6,
        max_tool_calls=3,
        max_elapsed_ms=900_000,
        max_input_tokens=250_000,
        max_output_tokens=20_000,
        max_cache_read_tokens=600_000,
        max_cache_write_tokens=200_000,
        max_total_tokens=800_000,
    )


if __name__ == "__main__":
    raise SystemExit(main())
