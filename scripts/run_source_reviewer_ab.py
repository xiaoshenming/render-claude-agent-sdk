#!/usr/bin/env python3
"""Run matched code-only Review1/Review2 experiments over frozen cases."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage_ledger import RecordingJsonlUsageLedger
from manim_quality.operator.native_reviewer_group import _specs, _tools
from manim_quality.operator.parallel_reviewer_sessions import (
    run_parallel_reviewer_sessions,
)

REVIEWERS = {
    "review1": "math_geometry_reviewer",
    "review2": "animation_lifecycle_reviewer",
}


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def provider_env() -> dict[str, str]:
    values = {}
    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            values[name] = value
    if not values.get("ANTHROPIC_API_KEY") and not values.get("ANTHROPIC_AUTH_TOKEN"):
        raise SystemExit("provider credentials are required")
    return values


def runtime(output: Path) -> AgentRuntime:
    limits = BudgetLimits(
        max_context_bytes=3_000_000,
        max_turns=8,
        max_tool_calls=16,
        max_elapsed_ms=900_000,
        max_input_tokens=400_000,
        max_output_tokens=24_000,
        max_cache_read_tokens=500_000,
        max_cache_write_tokens=300_000,
        max_total_tokens=800_000,
    )
    return AgentRuntime(
        ClaudeSdkBackend(provider_env=provider_env()),
        RecordingJsonlUsageLedger(output / "usage-events.jsonl"),
        limits,
    )


def materialize(case: Path, output: Path, source_name: str) -> Path:
    workspace = output / "workspaces" / case.name
    workspace.mkdir(parents=True, exist_ok=True)
    candidate = workspace / "candidate.py"
    shutil.copy2(case / source_name, candidate)
    figure = case / "confirmed_figure.py"
    if figure.is_file():
        target = workspace / "assets/visual/figure.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(figure, target)
    return candidate


def run_case(case: Path, args, agent: AgentRuntime) -> dict:
    started = time.monotonic()
    candidate = materialize(case, args.output, args.source_name)
    problem = (case / "problem.txt").read_text(encoding="utf-8")
    script = (case / "teaching_script.txt").read_text(encoding="utf-8")
    answer = (case / "parsed_standard_answer.txt").read_text(encoding="utf-8")
    tools = _tools(candidate, candidate.parent / "assets/visual/figure.py")
    specs = tuple(
        spec for spec in _specs(
            tools, candidate, candidate.parent / "assets/visual/figure.py",
            problem, answer, script, {}, args.effort,
        )
        if spec.name in args.reviewer_names
    )
    rows, records = run_parallel_reviewer_sessions(
        agent, candidate=candidate, specs=specs, tools=tools,
        model=args.model, effort=args.effort,
    )
    reviewers = []
    for row, record in zip(rows, records, strict=True):
        payload = row.get("payload") or {}
        reviewers.append({
            "reviewer": row.get("agent_type"),
            "decision": payload.get("decision"),
            "diagnosis": payload.get("diagnosis"),
            "issues": payload.get("issues") or [],
            "coverage": payload.get("coverage") or {},
            "duration_ms": record.elapsed_ms,
            "turns": record.turns,
            "tool_calls": len(record.tool_calls),
            "usage": {
                "input_tokens": record.usage.input_tokens,
                "output_tokens": record.usage.output_tokens,
                "cache_read_tokens": record.usage.cache_read_tokens,
                "cache_write_tokens": record.usage.cache_write_tokens,
                "total_tokens": record.usage.total_tokens,
            },
        })
    return {
        "label": case.name,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "reviewers": reviewers,
    }


def main() -> None:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    agent = runtime(args.output)
    rows = []
    cases = sorted(path for path in args.root.iterdir() if path.is_dir())
    if args.labels:
        wanted = set(args.labels.split(","))
        cases = [case for case in cases if case.name in wanted]
    for case in cases:
        print(f"[{len(rows) + 1}] {case.name}", flush=True)
        try:
            rows.append(run_case(case, args, agent))
        except Exception as error:
            rows.append({
                "label": case.name,
                "error": f"{type(error).__name__}: {error}",
            })
        atomic_json(args.output / "results.json", {"cases": rows})
    print(json.dumps({
        "count": len(rows),
        "errors": sum("error" in row for row in rows),
        "needs_repair": sum(
            reviewer.get("decision") == "needs_repair"
            for row in rows for reviewer in row.get("reviewers", [])
        ),
    }, ensure_ascii=False))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-name", default="initial_source.py")
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--reviewers", default="review1,review2")
    parser.add_argument("--labels", default="")
    args = parser.parse_args()
    args.reviewer_names = {
        REVIEWERS[name.strip()] for name in args.reviewers.split(",")
        if name.strip() in REVIEWERS
    }
    if not args.reviewer_names:
        parser.error("--reviewers must include review1 or review2")
    return args


if __name__ == "__main__":
    main()
