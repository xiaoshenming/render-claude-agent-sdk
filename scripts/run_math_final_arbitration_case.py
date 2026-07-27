#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_math_final_review_case import (  # noqa: E402
    BasicRelationChecker,
    CompileOnlyValidator,
    QualitySession,
    UnverifiedLayoutInspector,
    build_quality_tools,
    run_reviewer,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args()
    row = json.loads(args.result.read_text(encoding="utf-8"))
    decisions = {item["decision"] for item in row["reviews"]}
    if len(decisions) == 1 or row.get("arbitration"):
        print(f"SKIP {row['key']}", flush=True)
        return 0

    source = args.file.read_text(encoding="utf-8")
    session = QualitySession(
        problem_text=row["authoritative_problem"],
        candidate_code=source,
    )
    tools = build_quality_tools(
        session=session,
        relation_checker=BasicRelationChecker(),
        layout_inspector=UnverifiedLayoutInspector(),
        revision_validator=CompileOnlyValidator(),
    )
    reviewer_tools = tuple(
        replace(tool, max_calls=2)
        if tool.name == "check_relation"
        else replace(tool, max_calls=1)
        for tool in tools
        if tool.name in {"read_solution", "check_relation"}
    )
    claims = json.dumps(
        [
            {
                "name": item["name"],
                "decision": item["decision"],
                "diagnosis": item["diagnosis"],
                "issues": item["issues"],
            }
            for item in row["reviews"]
        ],
        ensure_ascii=False,
    )
    prompt = (
        "\n你是第三方仲裁者。前两位 Reviewer 结论冲突。"
        "重新阅读 R0 源码，逐条核对双方证据；不要因为有人报错就默认判错。"
        "只有源码明确违反题意、数学推理或绘图数学不变量时 needs_repair，"
        "纯措辞、近似误差、合理省略和未被源码支持的猜测必须 pass。"
        f"\n待仲裁意见：{claims}\n"
    )
    review, record = run_reviewer(
        name="arbiter",
        extra_prompt=prompt,
        model=args.model,
        output_dir=args.result.parent,
        tools=reviewer_tools,
        problem=row["authoritative_problem"],
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    )
    row["arbitration"] = {"review": review, "call_record": record}
    row["pre_arbitration_verdict"] = row["verdict"]
    row["verdict"] = (
        "math_error" if review["decision"] == "needs_repair" else "pass"
    )
    temporary = args.result.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.result)
    print(f"ARBITRATED {row['key']} {row['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
