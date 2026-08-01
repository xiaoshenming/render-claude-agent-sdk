#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import UsageSink
from manim_quality.assurance.agent import FinalAssuranceAgent
from manim_quality.assurance.dataset import (
    load_annotated_cases,
    load_curated_cases,
    load_successful_cases,
)
from manim_quality.assurance.metrics import summarize
from manim_quality.assurance.risk_frames import inspect_risk_frames
from manim_quality.assurance.tools import (
    inspect_artifact,
    inspect_code_review,
    inspect_consistency,
    inspect_execution,
    inspect_layout,
)
from manim_quality.assurance.tts import inspect_tts
from manim_quality.assurance.verification import VerificationConfig


class Sink(UsageSink):
    def __init__(self) -> None:
        self.records = []

    def save(self, record) -> None:
        self.records.append(record)


def main() -> int:
    args = arguments()
    if args.with_agent and not args.full_verification:
        raise SystemExit("--with-agent requires --full-verification")
    if args.case_manifest:
        cases = load_curated_cases(args.case_manifest, args.logs)
    elif args.all_successful:
        cases = load_successful_cases(args.gallery, args.logs)
    else:
        cases = load_annotated_cases(args.forensic, args.gallery, args.logs)
    if args.keys:
        wanted = set(args.keys.split(","))
        cases = tuple(case for case in cases if case.key in wanted)
    cases = cases[: args.limit or None]
    args.output.mkdir(parents=True, exist_ok=True)
    shared_agent = build_agent(args) if args.with_agent and args.workers == 1 else None
    rows = []
    indexed = tuple(enumerate(cases, 1))
    if args.workers == 1:
        generated = (
            process_case(case, args, index, len(cases), shared_agent)
            for index, case in indexed
        )
    else:
        executor = ThreadPoolExecutor(max_workers=args.workers)
        generated = executor.map(
            lambda item: process_case(item[1], args, item[0], len(cases)),
            indexed,
        )
    try:
        for row in generated:
            rows.append(row)
            write_json(args.output / "partial-results.json", rows)
    finally:
        if args.workers != 1:
            executor.shutdown(wait=True)
    summary = summarize(rows)
    write_json(args.output / "results.json", {"summary": summary, "cases": rows})
    write_markdown(args.output / "report.md", summary, rows)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def process_case(case, args, index: int, total: int, agent=None) -> dict:
    print(f"[{index}/{total}] {case.key}", flush=True)
    row = {
        "key": case.key,
        "human_tags": list(case.human_tags),
        "expected_verdict": case.expected_verdict,
    }
    if not args.with_agent:
        reports = deterministic_reports(case, args.output / "frames")
        row["deterministic"] = {
            report.tool: report.as_dict() for report in reports
        }
        row["detected_by_tools"] = any(report.detected for report in reports)
        return row
    return run_agent_case(case, args, row, agent or build_agent(args))


def run_agent_case(case, args, row: dict, agent) -> dict:
    case_output = args.output / "agent" / case.key
    case_output.mkdir(parents=True, exist_ok=True)
    try:
        result = agent.run(case, case_output)
        row["agent"] = result.output
        row["deterministic"] = result.reports
        row["detected_by_tools"] = any(
            report["status"] == "risk" for report in result.reports.values()
        )
        row["reviewers"] = list(result.reviewers)
        row["agent"] = {
            **row["agent"],
            "model": result.parent_call_record.model,
            "duration_ms": result.parent_call_record.elapsed_ms,
            "token_usage": usage_dict(result.parent_call_record),
            "usage_complete": result.parent_call_record.usage_complete,
        }
        row["agent_usage"] = {
            "tokens": result.call_record.usage.total_tokens,
            "token_usage": usage_dict(result.call_record),
            "usage_complete": result.call_record.usage_complete,
            "turns": result.call_record.turns,
            "tool_calls": len(result.call_record.tool_calls),
        }
    except Exception as error:
        row["agent_error"] = f"{type(error).__name__}: {error}"
        row["deterministic"] = {}
        row["detected_by_tools"] = False
    return row


def usage_dict(record) -> dict | None:
    usage = record.usage
    if not usage.total_tokens:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "total_tokens": usage.total_tokens,
    }


def deterministic_reports(case, frame_root: Path):
    return (
        inspect_artifact(case),
        inspect_execution(case),
        inspect_code_review(case),
        inspect_layout(case),
        inspect_risk_frames(case, frame_root),
        inspect_tts(case),
        inspect_consistency(case),
    )


def build_agent(args) -> FinalAssuranceAgent:
    provider = {}
    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            provider[name] = value
    if not provider.get("ANTHROPIC_API_KEY") and not provider.get(
        "ANTHROPIC_AUTH_TOKEN"
    ):
        raise SystemExit("Agent mode requires provider credentials")
    sink = Sink()
    limits = BudgetLimits(
        max_context_bytes=2_000_000,
        max_turns=12,
        max_tool_calls=30,
        max_elapsed_ms=900_000,
        max_input_tokens=160_000,
        max_output_tokens=16_000,
        max_cache_read_tokens=200_000,
        max_cache_write_tokens=100_000,
        max_total_tokens=300_000,
    )
    runtime = AgentRuntime(ClaudeSdkBackend(provider_env=provider), sink, limits)
    verification = None
    if args.full_verification:
        verification = VerificationConfig(
            manim_python=args.manim_python,
            runtime_python_paths=tuple(args.runtime_python_path),
        )
    return FinalAssuranceAgent(runtime, args.model, verification)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    default = Path(
        "/home/ming/data/Project/NodeProject/chap5/shuxuepai/"
        "outputs/batchops-agent-audit-20260727"
    )
    parser.add_argument("--forensic", type=Path, default=default / "forensic")
    parser.add_argument(
        "--gallery",
        type=Path,
        default=default.parent / "batchops-agent-gallery-20260727",
    )
    parser.add_argument("--logs", type=Path, default=default / "all-agent-logs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-agent", action="store_true")
    parser.add_argument("--full-verification", action="store_true")
    parser.add_argument(
        "--manim-python",
        type=Path,
        default=Path(__file__).with_name("docker_manim_python"),
    )
    parser.add_argument(
        "--runtime-python-path",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--all-successful", action="store_true")
    parser.add_argument("--case-manifest", type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keys", default="")
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=1)
    return parser.parse_args()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_markdown(path: Path, summary: dict, rows: list[dict]) -> None:
    lines = [
        "# Final Assurance Demo 评估",
        "",
        f"- 样本：{summary['total']}",
        f"- 确定性工具检出：{summary['deterministic_detected']}",
        f"- Agent 完成：{summary['agent_completed']}",
        f"- Agent 错误：{summary['agent_errors']}",
        "",
        "| case | 人工标签 | 工具检出 | Agent |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        status = row.get("agent", {}).get("status", row.get("agent_error", "未运行"))
        lines.append(
            f"| {row['key']} | {', '.join(row['human_tags'])} | "
            f"{'是' if row['detected_by_tools'] else '否'} | {status} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
