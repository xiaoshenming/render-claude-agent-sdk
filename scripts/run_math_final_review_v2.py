#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim_quality.agents._runtime_models import AgentRunRequest
from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import UsageSink
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.math_final.contracts import (
    ARBITRATION_OUTPUT_SCHEMA,
    REVIEW_OUTPUT_SCHEMA,
)
from manim_quality.math_final.input_checks import inspect_input_identity
from manim_quality.math_final.policy import decide_final_verdict
from manim_quality.operator.services import (
    BasicRelationChecker,
    CompileOnlyValidator,
    UnverifiedLayoutInspector,
)
from manim_quality.operator.session import QualitySession
from manim_quality.operator.toolset import build_quality_tools

from math_final_review_support import (
    authoritative_problem,
    provider_env,
    record_payload,
)

COMMON = """你是精确率优先的数学终审 Reviewer，只诊断，不改代码。
必须调用 read_solution 恰好一次，revision_id="R0"；check_relation 最多两次。
只把答案错误、关键公式错误、关键证明链无效归为 core_math。
输入自身矛盾或答案不唯一归为 input_invalid；题目与解答不是同一道题归为
source_mismatch；口误、证明略写、局部标注归为 minor；示意图不按比例、浮点
残差和不影响结论的坐标偏差归为 diagram_fidelity。
diagram_mode=schematic 时，除点线拓扑或题解明确依赖精确构造外，禁止把坐标
实测角度、长度、比例偏差归为 core_math。没有充分证据时必须 pass。
"""

PROOF_PROMPT = COMMON + """
你的唯一职责是核对最终答案、关键公式和从题设到答案的主证明链。
不要逐句挑错，不要求教材常识步骤全部展开，不审动画与样式。
"""

COUNTEREXAMPLE_PROMPT = COMMON + """
你的唯一职责是尝试构造反例、检查遗漏边界和对象偷换。
只有反例会推翻最终答案或关键证明时才归为 core_math。
"""

ARBITER_PROMPT = """你是精确率仲裁器。你只能核对给定 claims，禁止新增问题。
重新读取 R0；先排除示意图比例、浮点残差、旁白口误和合理证明省略。
只有两位 Reviewer 都报告 core_math 且同一核心断言确实错误时，才可输出
core_math。输入自身错误输出 input_invalid；题解不是同一道题输出
source_mismatch；其余风险输出 minor、diagram_fidelity 或 pass。
confirmed_claim_indexes 只能引用传入 claims 的索引。
"""


class Sink(UsageSink):
    def __init__(self) -> None:
        self.records = []

    def save(self, record) -> None:
        self.records.append(record)


def run_agent(
    *,
    name: str,
    prompt: str,
    schema: dict,
    model: str,
    output_dir: Path,
    tools,
) -> tuple[dict[str, object], dict[str, object]]:
    runtime = _runtime()
    request = AgentRunRequest(
        run_id=f"math-final-v2-{output_dir.name}-{name}",
        profile=reviewer_profile(
            model=model,
            prompt_version=f"math-final-v2-{name}",
            schema_version="math-final-v2",
            tool_version="math-final-tools-v1",
        ),
        prompt=prompt,
        output_schema=schema,
        workspace=output_dir,
        readable_paths=(),
        editable_paths=(),
        context_bytes=len(prompt.encode()) + len(json.dumps(schema).encode()),
        estimated_input_tokens=35_000,
        reserved_output_tokens=4_000,
        reserved_cache_read_tokens=60_000,
        reserved_cache_write_tokens=0,
        managed_tools=tools,
        effort="low",
    )
    try:
        result = runtime.run(request)
    except Exception as error:
        record = getattr(error, "record", None)
        attempts = [
            thaw_json_object(call.input)
            for call in (record.tool_calls if record else ())
            if call.name == "StructuredOutput"
        ]
        if attempts:
            return attempts[-1], record_payload(record) or {}
        raise
    return (
        thaw_json_object(result.structured_output),
        record_payload(result.record) or {},
    )


def _runtime() -> AgentRuntime:
    return AgentRuntime(
        ClaudeSdkBackend(provider_env=provider_env()),
        Sink(),
        BudgetLimits(
            max_context_bytes=900_000,
            max_turns=10,
            max_tool_calls=24,
            max_elapsed_ms=360_000,
            max_input_tokens=160_000,
            max_output_tokens=12_000,
            max_cache_read_tokens=220_000,
            max_cache_write_tokens=60_000,
            max_total_tokens=320_000,
        ),
    )
def reviewer_tools(problem: str, source: str):
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


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--diagram-mode",
        choices=("schematic", "exact"),
        default="schematic",
    )
    parser.add_argument("--model", default="gpt-5.6-sol")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "result-v2.json"
    started = time.time()
    source = args.file.read_text(encoding="utf-8")
    problem = authoritative_problem(source)
    source_sha = hashlib.sha256(source.encode()).hexdigest()
    input_evidence = inspect_input_identity(
        problem_text=problem,
        source=source,
        expected_sha256=args.expected_sha256,
    )
    tools = reviewer_tools(problem, source)
    context = (
        f"\ndiagram_mode={args.diagram_mode}\n"
        f"authoritative_problem={problem}\nsource_sha256={source_sha}\n"
    )
    reviews, records = _run_reviews(args, context, tools)
    decision = decide_final_verdict(reviews, input_evidence=input_evidence)
    arbitration = None
    if decision.needs_arbitration:
        arbitration = _run_arbitration(args, context, tools, reviews)
        decision = decide_final_verdict(
            reviews,
            input_evidence=input_evidence,
            arbitration=arbitration["review"],
        )
    payload = _payload(
        args, started, source_sha, problem, input_evidence,
        reviews, records, arbitration, decision,
    )
    _write_result(result_path, payload)
    print(f"COMPLETED {args.file.stem} {payload['verdict']}", flush=True)
    return 0


def _run_reviews(args, context, tools):
    reviews, records = [], []
    for name, prompt in (
        ("proof", PROOF_PROMPT),
        ("counterexample", COUNTEREXAMPLE_PROMPT),
    ):
        review, record = run_agent(
            name=name,
            prompt=prompt + context,
            schema=REVIEW_OUTPUT_SCHEMA,
            model=args.model,
            output_dir=args.output,
            tools=tools,
        )
        reviews.append({"name": name, **review})
        records.append(record)
    return reviews, records


def _run_arbitration(args, context, tools, reviews):
    claims = [
        {"reviewer": review["name"], **issue}
        for review in reviews
        for issue in review["issues"]
    ]
    classifications = [
        {"name": item["name"], "classification": item["classification"]}
        for item in reviews
    ]
    prompt = (
        ARBITER_PROMPT + context
        + "\nreviewer_classifications="
        + json.dumps(classifications, ensure_ascii=False)
        + "\nclaims=" + json.dumps(claims, ensure_ascii=False)
    )
    review, record = run_agent(
        name="arbiter", prompt=prompt, schema=ARBITRATION_OUTPUT_SCHEMA,
        model=args.model, output_dir=args.output, tools=tools,
    )
    return {"review": review, "call_record": record}


def _payload(
    args, started, source_sha, problem, input_evidence,
    reviews, records, arbitration, decision,
):
    return {
        "schema_version": "math-final-v2",
        "key": args.file.stem,
        "status": "completed",
        "verdict": decision.verdict.value,
        "failure_code": decision.failure_code,
        "explanation": decision.explanation,
        "evidence_only": True,
        "blocking": False,
        "diagram_mode": args.diagram_mode,
        "source_sha256": source_sha,
        "authoritative_problem": problem,
        "input_evidence": [asdict(item) for item in input_evidence],
        "reviews": reviews,
        "call_records": records,
        "arbitration": arbitration,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _write_result(result_path, payload):
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(result_path)


if __name__ == "__main__":
    raise SystemExit(main())
