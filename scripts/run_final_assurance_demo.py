#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import UsageSink
from manim_quality.assurance.agent import FinalAssuranceAgent
from manim_quality.assurance.dataset import (
    load_annotated_cases,
    load_successful_cases,
)
from manim_quality.assurance.risk_frames import inspect_risk_frames
from manim_quality.assurance.tools import (
    inspect_artifact,
    inspect_code_review,
    inspect_consistency,
    inspect_execution,
    inspect_layout,
    inspect_tts,
)


class Sink(UsageSink):
    def __init__(self) -> None:
        self.records = []

    def save(self, record) -> None:
        self.records.append(record)


def main() -> int:
    args = arguments()
    cases = (
        load_successful_cases(args.gallery, args.logs)
        if args.all_successful
        else load_annotated_cases(args.forensic, args.gallery, args.logs)
    )
    if args.keys:
        wanted = set(args.keys.split(","))
        cases = tuple(case for case in cases if case.key in wanted)
    cases = cases[: args.limit or None]
    args.output.mkdir(parents=True, exist_ok=True)
    agent = build_agent(args) if args.with_agent else None
    rows = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case.key}", flush=True)
        reports = deterministic_reports(case, args.output / "frames")
        row = {
            "key": case.key,
            "human_tags": list(case.human_tags),
            "expected_verdict": case.expected_verdict,
            "deterministic": {report.tool: report.as_dict() for report in reports},
            "detected_by_tools": any(report.detected for report in reports),
        }
        if agent is not None:
            case_output = args.output / "agent" / case.key
            case_output.mkdir(parents=True, exist_ok=True)
            try:
                result = agent.run(case, case_output)
                row["agent"] = result.output
                row["agent_usage"] = {
                    "tokens": result.call_record.usage.total_tokens,
                    "turns": result.call_record.turns,
                    "tool_calls": len(result.call_record.tool_calls),
                }
            except Exception as error:
                row["agent_error"] = f"{type(error).__name__}: {error}"
        rows.append(row)
        write_json(args.output / "partial-results.json", rows)
    summary = summarize(rows)
    write_json(args.output / "results.json", {"summary": summary, "cases": rows})
    write_markdown(args.output / "report.md", summary, rows)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


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


def summarize(rows: list[dict]) -> dict[str, object]:
    total = len(rows)
    detected = sum(bool(row["detected_by_tools"]) for row in rows)
    labeled_bad = sum(
        bool(row.get("human_tags") or row.get("expected_verdict")) for row in rows
    )
    agent_completed = [row for row in rows if isinstance(row.get("agent"), dict)]
    agent_reviewed = sum(
        row["agent"].get("status") in {"review", "incomplete"}
        for row in agent_completed
    )
    by_tool: dict[str, int] = {}
    for row in rows:
        for name, report in row["deterministic"].items():
            by_tool[name] = by_tool.get(name, 0) + (report["status"] == "risk")
    return {
        "total": total,
        "deterministic_detected": detected,
        "deterministic_flag_rate": detected / total if total else 0,
        "labeled_bad": labeled_bad,
        "deterministic_recall": (
            detected / labeled_bad if labeled_bad == total and total else None
        ),
        "agent_completed": len(agent_completed),
        "agent_reviewed": agent_reviewed,
        "agent_recall": (
            agent_reviewed / len(agent_completed) if agent_completed else None
        ),
        "risk_count_by_tool": by_tool,
        "agent_errors": sum("agent_error" in row for row in rows),
    }


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
        max_tool_calls=12,
        max_elapsed_ms=900_000,
        max_input_tokens=160_000,
        max_output_tokens=16_000,
        max_cache_read_tokens=200_000,
        max_cache_write_tokens=100_000,
        max_total_tokens=300_000,
    )
    runtime = AgentRuntime(ClaudeSdkBackend(provider_env=provider), sink, limits)
    return FinalAssuranceAgent(runtime, args.model)


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
    parser.add_argument("--all-successful", action="store_true")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keys", default="")
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
