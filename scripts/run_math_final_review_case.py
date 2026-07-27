#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from math_final_review_support import (
    authoritative_problem,
    provider_env,
    record_payload,
)

from manim_quality.agents._runtime_models import AgentRunRequest
from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import UsageSink
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.operator.services import (
    BasicRelationChecker,
    CompileOnlyValidator,
    UnverifiedLayoutInspector,
)
from manim_quality.operator.session import QualitySession
from manim_quality.operator.toolset import build_quality_tools

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "diagnosis": {"type": "string", "minLength": 1, "maxLength": 2000},
        "issues": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium"],
                    },
                    "claim": {"type": "string"},
                    "evidence": {"type": "string"},
                    "correct_invariant": {"type": "string"},
                },
                "required": [
                    "severity",
                    "claim",
                    "evidence",
                    "correct_invariant",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decision", "confidence", "diagnosis", "issues"],
    "additionalProperties": False,
}

REVIEW_PROMPT = """你是纯数学终审 Reviewer，只诊断，不改代码。
必须调用 read_solution 恰好一次，revision_id 严格为 "R0"。
check_relation 最多调用一次，只验证你认为最高风险的一条关系；不要逐角枚举。
工具返回后必须立即提交 StructuredOutput，不得继续调用任何工具。
逐条审查题意、推理、公式、答案、对象归属、坐标和图形数学不变量。
不得把颜色、措辞、重叠、动画生命周期或代码风格列为数学错误。
没有充分源码证据时必须通过。最后严格使用 StructuredOutput。
"""


class Sink(UsageSink):
    def __init__(self) -> None:
        self.records = []

    def save(self, record) -> None:
        self.records.append(record)


def run_reviewer(
    *,
    name: str,
    extra_prompt: str,
    model: str,
    output_dir: Path,
    tools,
    problem: str,
    source_sha256: str,
) -> tuple[dict[str, object], dict[str, object]]:
    runtime = _runtime()
    prompt = (
        REVIEW_PROMPT
        + extra_prompt
        + f"\nauthoritative_problem: {problem}\n"
        + f"source_sha256: {source_sha256}\n"
    )
    request = AgentRunRequest(
        run_id=f"math-final-{output_dir.name}-{name}",
        profile=reviewer_profile(
            model=model,
            prompt_version=f"math-final-{name}-v1",
            schema_version="math-final-reviewer-output-v1",
            tool_version="math-final-tools-v1",
        ),
        prompt=prompt,
        output_schema=OUTPUT_SCHEMA,
        workspace=output_dir,
        readable_paths=(),
        editable_paths=(),
        context_bytes=len(prompt.encode()) + len(json.dumps(OUTPUT_SCHEMA).encode()),
        estimated_input_tokens=35_000,
        reserved_output_tokens=4_000,
        reserved_cache_read_tokens=60_000,
        reserved_cache_write_tokens=0,
        managed_tools=tools,
        effort="low",
    )
    try:
        outcome = runtime.run(request)
    except Exception as error:
        record = getattr(error, "record", None)
        attempts = [
            thaw_json_object(item.input)
            for item in (record.tool_calls if record else ())
            if item.name == "StructuredOutput"
        ]
        if attempts:
            return attempts[-1], record_payload(record) or {}
        raise
    return (
        thaw_json_object(outcome.structured_output),
        record_payload(outcome.record) or {},
    )


def _runtime() -> AgentRuntime:
    return AgentRuntime(
        ClaudeSdkBackend(provider_env=provider_env()),
        Sink(),
        BudgetLimits(
            max_context_bytes=900_000,
            max_turns=12,
            max_tool_calls=30,
            max_elapsed_ms=360_000,
            max_input_tokens=180_000,
            max_output_tokens=12_000,
            max_cache_read_tokens=220_000,
            max_cache_write_tokens=60_000,
            max_total_tokens=340_000,
        ),
    )
def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "result.json"
    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        if existing.get("status") == "completed":
            print(f"SKIP {args.file.stem}", flush=True)
            return 0

    started = time.time()
    source = args.file.read_text(encoding="utf-8")
    problem = authoritative_problem(source)
    reviewer_tools = _reviewer_tools(problem, source)
    source_sha256 = hashlib.sha256(source.encode()).hexdigest()
    try:
        reviews, records = _collect_reviews(
            args, reviewer_tools, problem, source_sha256,
        )
        payload = _success_payload(
            args, source_sha256, problem, reviews, records, started,
        )
    except Exception as error:
        payload = _failure_payload(
            args, source_sha256, problem, error, started,
        )
    _write_result(result_path, payload)
    print(
        f"{payload['status'].upper()} {args.file.stem} "
        f"{payload['elapsed_seconds']}s",
        flush=True,
    )
    return 0 if payload["status"] == "completed" else 2


def _reviewer_tools(problem, source):
    session = QualitySession(problem_text=problem, candidate_code=source)
    tools = build_quality_tools(
        session=session,
        relation_checker=BasicRelationChecker(),
        layout_inspector=UnverifiedLayoutInspector(),
        revision_validator=CompileOnlyValidator(),
    )
    return tuple(
        replace(tool, max_calls=2)
        if tool.name == "check_relation"
        else replace(tool, max_calls=1)
        for tool in tools
        if tool.name in {"read_solution", "check_relation"}
    )


def _collect_reviews(args, tools, problem, source_sha):
    reviews, records = [], []
    roles = (
        ("proof", ""),
        ("adversarial", "\n重点寻找反例、对象偷换和坐标矛盾。\n"),
    )
    for name, extra in roles:
        checkpoint = args.output / f"reviewer-{name}.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            review, record = saved["review"], saved["call_record"]
        else:
            review, record = run_reviewer(
                name=name, extra_prompt=extra, model=args.model,
                output_dir=args.output, tools=tools, problem=problem,
                source_sha256=source_sha,
            )
            checkpoint.write_text(
                json.dumps(
                    {"review": review, "call_record": record},
                    ensure_ascii=False, indent=2,
                ) + "\n",
                encoding="utf-8",
            )
        reviews.append({"name": name, **review})
        records.append(record)
    return reviews, records


def _success_payload(args, source_sha, problem, reviews, records, started):
    decisions = [item["decision"] for item in reviews]
    return {
        "key": args.file.stem, "file": str(args.file),
        "source_sha256": source_sha, "authoritative_problem": problem,
        "status": "completed",
        "verdict": "math_error" if "needs_repair" in decisions else "pass",
        "reviews": reviews, "call_records": records,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _failure_payload(args, source_sha, problem, error, started):
    return {
        "key": args.file.stem, "file": str(args.file),
        "source_sha256": source_sha, "authoritative_problem": problem,
        "status": "failed", "error": f"{type(error).__name__}: {error}",
        "failed_call_record": record_payload(getattr(error, "record", None)),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _write_result(result_path, payload):
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(result_path)


if __name__ == "__main__":
    sys.exit(main())
