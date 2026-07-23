"""Replay minimal full-source reviews through the V3 Coder and Verifier."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from collections.abc import Mapping
from pathlib import Path

from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.repair_plan import build_repair_plan
from manim_quality.logic.reporting import review_report_to_dict
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)
from manim_quality.revisions.fingerprint import code_hash, sha256_text

from evals._logic_repair_case import _flow
from evals._logic_shadow_io import JsonSequenceUsageSink, write_json


def main() -> int:
    args = arguments()
    cases = sorted(path for path in args.library.iterdir() if path.is_dir())
    if args.sample_id:
        wanted = set(args.sample_id)
        cases = [case for case in cases if case.name in wanted]
    results = [run_case(case, args) for case in cases]
    write_json(args.output / "pipeline_results.json", results)
    write_json(args.output / "pipeline_summary.json", summarize(results))
    print(json.dumps(summarize(results), ensure_ascii=False, indent=2))
    return 0


def run_case(case: Path, args) -> dict[str, object]:
    started = time.monotonic()
    output = args.output / "cases" / case.name
    output.mkdir(parents=True, exist_ok=True)
    source = case / "baseline.py"
    problem_path = case / "problem.txt"
    review = select_review(args.review_root, case.name)
    if review is None:
        return result(case.name, "review_unavailable", started)
    if review["decision"] != "needs_repair":
        return result(case.name, "review_pass", started)
    baseline = source.read_text(encoding="utf-8")
    problem = problem_path.read_text(encoding="utf-8")
    report = convert_review(case.name, review, baseline, problem)
    write_json(output / "review_report.json", review_report_to_dict(report))
    workspace = output / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    candidate = workspace / "candidate.py"
    shutil.copyfile(source, candidate)
    coder_sink = JsonSequenceUsageSink(output, "coder")
    verifier_sink = JsonSequenceUsageSink(output, "verifier")
    flow = _flow(
        type(
            "Config",
            (),
            {"model": args.model, "provider_env": provider_environment()},
        )(),
        coder_sink,
        verifier_sink,
    )
    try:
        plan = build_repair_plan(report, extract_scenes(baseline))
        flow_result = flow.run(
            run_id=f"minimal-pipeline-{case.name}",
            plan=plan,
            workspace=workspace,
            candidate_path=candidate,
            coder_estimated_input_tokens=max(1_000, len(baseline.encode()) // 2),
            coder_reserved_output_tokens=40_000,
            verifier_estimated_input_tokens=max(1_000, len(baseline.encode()) // 2),
            verifier_reserved_output_tokens=40_000,
        )
        shutil.copyfile(candidate, output / "candidate_after.py")
        compile(candidate.read_text(encoding="utf-8"), "candidate_after.py", "exec")
        payload = result(
            case.name,
            flow_result.status.value,
            started,
            attempts=flow_result.attempt_count,
            reason=flow_result.reason,
            changed=code_hash(baseline) != code_hash(candidate.read_text()),
            review_issues=len(report.issues),
            issue_outcomes=issue_outcomes(report, verifier_sink.records),
            coder_tokens=token_total(coder_sink.records),
            verifier_tokens=token_total(verifier_sink.records),
        )
    except Exception as error:
        payload = result(
            case.name,
            "error",
            started,
            error=f"{type(error).__name__}: {error}",
            review_issues=len(report.issues),
            issue_outcomes=issue_outcomes(report, verifier_sink.records),
            coder_tokens=token_total(coder_sink.records),
            verifier_tokens=token_total(verifier_sink.records),
        )
    write_json(output / "pipeline_result.json", payload)
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return payload


def convert_review(
    sample_id: str, review: dict[str, object], code: str, problem: str
) -> LogicReviewReport:
    lines = code.splitlines()
    scenes = extract_scenes(code)
    issues = []
    for index, raw in enumerate(review.get("issues") or [], 1):
        start = clamp_line(raw.get("line_start"), len(lines))
        end = max(start, clamp_line(raw.get("line_end"), len(lines)))
        scene = next(
            (
                item
                for item in scenes
                if item.line_start <= start <= item.line_end
            ),
            scenes[0],
        )
        issue_id = clean_id(str(raw.get("issue_id") or f"issue-{index}"), index)
        issues.append(
            LogicIssue(
                issue_id=issue_id,
                issue_type="minimal_full_source_logic",
                severity=IssueSeverity(str(raw.get("severity") or "high")),
                confidence=0.9,
                repairable=True,
                repair_scope="修复明确的数学或教学逻辑错误",
                target_scene_ids=(scene.scene_id,),
                evidence=(
                    EvidenceCitation(
                        CitationArtifact.CANDIDATE_CODE,
                        "candidate.py",
                        code_hash(code),
                        "\n".join(lines[start - 1 : end]) or lines[start - 1],
                        scene.scene_id,
                        start,
                        end,
                    ),
                    EvidenceCitation(
                        CitationArtifact.PROBLEM_TEXT,
                        "problem.txt",
                        sha256_text(problem),
                        problem[:1_000],
                    ),
                ),
                expected=str(raw["expected"]),
                observed=str(raw["observed"]),
                acceptance_predicates=(
                    {
                        "kind": "directed_logic_verification",
                        "expected": str(raw["expected"]),
                        "scene_id": scene.scene_id,
                    },
                ),
                non_goals=("不修改排版、重叠、美观和无关教学表达",),
            )
        )
    return LogicReviewReport(
        review_id=f"minimal-review-{sample_id}",
        revision_id=f"minimal-revision-{sample_id}",
        code_hash=code_hash(code),
        render_manifest_hash=sha256_text("{}"),
        decision=LogicDecision.NEEDS_REPAIR,
        blocked=True,
        requires_human_review=False,
        summary=str(review.get("summary") or "极简完整源码审查发现逻辑问题"),
        issues=tuple(issues),
        review_gaps=(),
    )


def select_review(root: Path, sample_id: str) -> dict[str, object] | None:
    for path in sorted((root / "calls" / sample_id).glob("repeat-*/agent_call.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        review = payload.get("structured_output")
        if isinstance(review, dict) and review.get("decision") == "needs_repair":
            return review
    return None


def result(sample_id: str, status: str, started: float, **extra) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "status": status,
        "elapsed_ms": int((time.monotonic() - started) * 1_000),
        **extra,
    }


def summarize(results: list[dict[str, object]]) -> dict[str, object]:
    statuses: dict[str, int] = {}
    for item in results:
        key = str(item["status"])
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "cases": len(results),
        "statuses": statuses,
        "changed": sum(bool(item.get("changed")) for item in results),
        "coder_tokens": sum(int(item.get("coder_tokens") or 0) for item in results),
        "verifier_tokens": sum(
            int(item.get("verifier_tokens") or 0) for item in results
        ),
        "elapsed_ms": sum(int(item["elapsed_ms"]) for item in results),
    }


def token_total(records) -> int:
    return sum(
        record.usage.input_tokens
        + record.usage.output_tokens
        + record.usage.cache_read_tokens
        for record in records
    )


def issue_outcomes(report: LogicReviewReport, records) -> list[dict[str, object]]:
    resolved: dict[str, bool] = {}
    reasons: dict[str, str] = {}
    for record in records:
        payload = record.structured_output
        if not isinstance(payload, Mapping):
            continue
        for item in payload.get("results") or []:
            if not isinstance(item, Mapping):
                continue
            issue_id = str(item.get("issue_id") or "")
            if issue_id:
                resolved[issue_id] = bool(item.get("resolved"))
                reasons[issue_id] = str(item.get("reason") or "")
    return [
        {
            "issue_id": issue.issue_id,
            "status": (
                "resolved"
                if resolved.get(issue.issue_id) is True
                else "unresolved"
                if resolved.get(issue.issue_id) is False
                else "unknown"
            ),
            "reason": reasons.get(issue.issue_id, "未获得结构化逐项验收结果"),
        }
        for issue in report.issues
    ]


def provider_environment() -> dict[str, str]:
    key = os.environ["MANIM_QUALITY_ANTHROPIC_API_KEY"]
    return {
        "ANTHROPIC_BASE_URL": os.environ["MANIM_QUALITY_ANTHROPIC_BASE_URL"],
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
    }


def clamp_line(value: object, maximum: int) -> int:
    return min(max(int(value or 1), 1), maximum)


def clean_id(value: str, index: int) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_-" else "_" for char in value)
    return (cleaned.strip("_") or f"issue-{index}")[:80]


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--sample-id", action="append")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
