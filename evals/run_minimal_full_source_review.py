"""Run an isolated minimal full-source Logic Reviewer experiment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT, ROOT / "vendor/logic_engine_mvp_baseline"):
    if str(item) not in os.sys.path:
        os.sys.path.insert(0, str(item))

from evals._logic_shadow_io import JsonUsageSink
from manim_quality.agents import (
    AgentRunFailed,
    AgentRuntime,
    BudgetLimits,
    ClaudeSdkBackend,
    reviewer_profile,
)
from manim_quality.agents._runtime_models import AgentRunRequest
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.contracts._json_values import thaw_json_object


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "summary", "issues"],
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "summary": {"type": "string", "minLength": 1},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_id",
                    "severity",
                    "line_start",
                    "line_end",
                    "observed",
                    "expected",
                    "reason",
                ],
                "properties": {
                    "issue_id": {"type": "string", "minLength": 1},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "line_start": {"type": "integer", "minimum": 1},
                    "line_end": {"type": "integer", "minimum": 1},
                    "observed": {"type": "string", "minLength": 1},
                    "expected": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

PROMPT = """你是 Manim 数学视频的逻辑审查员。

请直接阅读下面的题目和完整 Python 源码，检查是否存在明确的数学或教学逻辑错误。

只检查：
1. 公式、计算、结论是否正确；
2. 点、线、圆、角度、坐标、函数图像是否与题目和讲解一致；
3. 动画初态、过程、终态是否表达同一个正确关系；
4. 是否遗漏题目明确要求，或把待证结论当成已知条件。

不要检查排版、重叠、美观、节奏和代码风格。
不要因为存在不同但等价的证明或画法而报错。
只有存在明确证据时才报告问题；没有明确逻辑错误就返回 pass。
发现问题时给出源码行号、当前错误内容、正确内容和判断理由。
完整源码已在提示词中，不需要调用 Read 工具。

【题目原文】
{problem}

【完整 candidate.py】
```python
{code}
```
"""


def main() -> int:
    args = arguments()
    cases = sorted(path for path in args.library.iterdir() if complete(path))
    jobs = [
        (case, repeat)
        for case in cases
        for repeat in range(1, args.repeats + 1)
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_one, case, repeat, args): (case, repeat)
            for case, repeat in jobs
        }
        for index, future in enumerate(as_completed(futures), 1):
            case, repeat = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "job_id": case.name,
                    "repeat": repeat,
                    "decision": None,
                    "issues": [],
                    "error": f"{type(error).__name__}: {error}",
                }
            results.append(result)
            print(
                json.dumps(
                    {"done": index, "total": len(jobs), **result},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    results.sort(key=lambda item: (str(item["job_id"]), int(item["repeat"])))
    write_json(args.output / "results.json", results)
    write_json(args.output / "summary.json", summarize(results))
    print(json.dumps(summarize(results), ensure_ascii=False, indent=2))
    return 0


def run_one(case: Path, repeat: int, args) -> dict[str, object]:
    output = args.output / "calls" / case.name / f"repeat-{repeat}"
    sink = JsonUsageSink(output / "agent_call.json")
    code = (case / "baseline.py").read_text(encoding="utf-8")
    problem = (case / "problem.txt").read_text(encoding="utf-8")
    prompt = PROMPT.format(problem=problem, code=code)
    with tempfile.TemporaryDirectory(prefix="minimal-logic-review-") as temporary:
        workspace = Path(temporary)
        candidate = workspace / "candidate.py"
        shutil.copyfile(case / "baseline.py", candidate)
        runtime = AgentRuntime(
            ClaudeSdkBackend(provider_env=provider()),
            sink,
            limits(),
        )
        request = AgentRunRequest(
            run_id=f"minimal-{case.name}-{repeat}",
            profile=reviewer_profile(
                model=os.environ["MANIM_QUALITY_MODEL"],
                prompt_version="logic-reviewer-minimal-full-source-v1",
                tool_version=f"claude-agent-sdk-{sdk_version}-minimal-v1",
            ),
            prompt=prompt,
            output_schema=OUTPUT_SCHEMA,
            workspace=workspace,
            readable_paths=(candidate,),
            editable_paths=(),
            context_bytes=len(prompt.encode("utf-8")),
            estimated_input_tokens=max(1_000, len(prompt.encode("utf-8")) // 2),
            reserved_output_tokens=20_000,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
            tool_policies={"Read": ToolInputPolicy(max_calls=1)},
        )
        try:
            result = runtime.run(request)
            payload = thaw_json_object(result.structured_output)
            error = None
        except AgentRunFailed as failure:
            payload = {}
            error = failure.record.error
    record = sink.record
    usage = record.usage if record else None
    return {
        "job_id": case.name,
        "repeat": repeat,
        "decision": payload.get("decision"),
        "summary": payload.get("summary"),
        "issues": payload.get("issues") or [],
        "issue_count": len(payload.get("issues") or []),
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "cache_read_tokens": usage.cache_read_tokens if usage else 0,
        "elapsed_ms": record.elapsed_ms if record else 0,
        "tool_calls": [call.name for call in record.tool_calls] if record else [],
        "error": error,
    }


def summarize(results: list[dict[str, object]]) -> dict[str, object]:
    decisions: dict[str, int] = {}
    for result in results:
        key = str(result.get("decision") or "error")
        decisions[key] = decisions.get(key, 0) + 1
    by_case: dict[str, list[str]] = {}
    for result in results:
        by_case.setdefault(str(result["job_id"]), []).append(
            str(result.get("decision") or "error")
        )
    return {
        "attempted": len(results),
        "decisions": decisions,
        "consistent_cases": sum(len(set(values)) == 1 for values in by_case.values()),
        "case_count": len(by_case),
        "total_tokens": sum(
            int(result.get("input_tokens") or 0)
            + int(result.get("output_tokens") or 0)
            + int(result.get("cache_read_tokens") or 0)
            for result in results
        ),
        "total_elapsed_ms": sum(int(result.get("elapsed_ms") or 0) for result in results),
    }


def provider() -> dict[str, str]:
    key = os.environ["MANIM_QUALITY_ANTHROPIC_API_KEY"]
    return {
        "ANTHROPIC_BASE_URL": os.environ["MANIM_QUALITY_ANTHROPIC_BASE_URL"],
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
    }


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=250_000,
        max_turns=6,
        max_tool_calls=4,
        max_elapsed_ms=180_000,
        max_input_tokens=200_000,
        max_output_tokens=40_000,
        max_cache_read_tokens=200_000,
        max_cache_write_tokens=1,
        max_total_tokens=300_000,
    )


def complete(path: Path) -> bool:
    return path.is_dir() and all(
        (path / name).is_file() for name in ("baseline.py", "problem.txt")
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
