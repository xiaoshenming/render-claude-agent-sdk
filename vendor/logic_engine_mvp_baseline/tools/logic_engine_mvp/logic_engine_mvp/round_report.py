from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


CASE_CSV_FIELDS = [
    "sample_id",
    "stage",
    "supported_contract_count",
    "soft_contract_count",
    "repairable_contract_count",
    "needs_human_review_count",
    "review_issue_count",
    "discarded_issue_count",
    "open_repair_issue_count",
    "open_task_count",
    "reviewer_elapsed_sec",
    "reviewer_safe_fallback_reason",
    "agent_elapsed_sec",
    "render_elapsed_sec",
    "reviewer_tokens",
    "agent_tokens",
    "total_tokens",
    "agent_tool_steps",
    "validation_passed",
    "render_checked",
    "render_passed",
    "render_exit_code",
    "sdk_ok",
    "execution_mode",
    "open_agent_completed",
    "repair_task_type",
    "sdk_error_type",
    "missing_artifacts",
]

REQUIRED_CASE_ARTIFACTS = [
    "review_input.json",
    "llm_review.json",
    "verified_issues.json",
    "repair_contract.json",
    "before_candidate.py",
    "candidate.py",
    "validation_before.json",
]


def write_round_reports(round_dir: Path) -> dict[str, Any]:
    round_dir = Path(round_dir)
    rows = [_case_row(case_dir) for case_dir in sorted((round_dir / "cases").iterdir()) if case_dir.is_dir()]
    summary = _summary(round_dir, rows)

    _write_json(round_dir / "summary.json", summary)
    _write_text(round_dir / "summary.md", _summary_markdown(summary))
    _write_case_csv(round_dir / "per_case_results.csv", rows)
    _write_text(round_dir / _experience_filename(round_dir), _experience_markdown(summary))
    _write_text(round_dir / "audit_report.md", _audit_markdown(summary))
    return summary


def _case_row(case_dir: Path) -> dict[str, Any]:
    status = _read_json(case_dir / "case_status.json")
    review = _read_json(case_dir / "llm_review.json")
    token_usage = _read_json(case_dir / "token_usage.json")
    validation_after = _read_json(case_dir / "validation_after.json")
    render_check = _read_json(case_dir / "render_check.json")
    agent_messages = _read_json(case_dir / "agent_messages.json")
    repair_contract = _read_json(case_dir / "repair_contract.json")
    open_task = _read_json(case_dir / "open_repair_task.json")

    reviewer_tokens = _int((_dict(review.get("usage"))).get("total_tokens"))
    usage = _dict(token_usage.get("usage"))
    agent_tokens = _int(usage.get("total_tokens"))
    supported_contract_count = _int(status.get("supported_contract_count"))
    soft_contract_count = _int(status.get("soft_contract_count") or repair_contract.get("soft_contract_count"))
    repairable_contract_count = _int(
        status.get("repairable_contract_count")
        or repair_contract.get("repairable_contract_count")
        or (supported_contract_count + soft_contract_count)
    )
    missing = [name for name in REQUIRED_CASE_ARTIFACTS if not (case_dir / name).exists()]
    open_task_count = _int(status.get("open_task_count") or open_task.get("issue_count"))
    is_open_repair = open_task_count > 0 or status.get("repair_task_type") == "open_repair"
    if status.get("stage") in {
        "validation_passed",
        "validation_failed",
        "agent_failed",
        "sdk_api_unavailable",
        "budget_exceeded",
    }:
        required_agent_artifacts = ["agent_messages.json", "after_candidate.py", "token_usage.json"]
        if not is_open_repair:
            required_agent_artifacts.append("validation_after.json")
        for name in required_agent_artifacts:
            if not (case_dir / name).exists():
                missing.append(name)
    if open_task_count > 0 and not (case_dir / "open_repair_task.json").exists():
        missing.append("open_repair_task.json")
    if status.get("stage") in {"open_agent_completed", "open_agent_failed"}:
        for name in ("agent_messages.json", "after_candidate.py", "token_usage.json"):
            if not (case_dir / name).exists():
                missing.append(name)

    execution_mode = _execution_mode(agent_messages, token_usage)
    fallback_reason = _reviewer_safe_fallback_reason(review)
    repair_task_type = str(status.get("repair_task_type") or token_usage.get("repair_task_type") or "")
    if not repair_task_type and open_task_count > 0:
        repair_task_type = "open_repair"
    return {
        "sample_id": str(status.get("sample_id") or case_dir.name),
        "stage": str(status.get("stage") or "unknown"),
        "supported_contract_count": supported_contract_count,
        "soft_contract_count": soft_contract_count,
        "repairable_contract_count": repairable_contract_count,
        "needs_human_review_count": _int(status.get("needs_human_review_count")),
        "review_issue_count": len(review.get("issues") or []),
        "discarded_issue_count": _int(review.get("discarded_issue_count")),
        "open_repair_issue_count": _int(review.get("open_repair_issue_count")),
        "open_task_count": open_task_count,
        "reviewer_elapsed_sec": _float_or_empty(review.get("elapsed_sec")),
        "reviewer_safe_fallback_reason": fallback_reason,
        "agent_elapsed_sec": _float_or_empty(agent_messages.get("elapsed_sec")),
        "render_elapsed_sec": _float_or_empty(render_check.get("elapsed_sec")),
        "reviewer_tokens": reviewer_tokens,
        "agent_tokens": agent_tokens,
        "total_tokens": reviewer_tokens + agent_tokens,
        "agent_tool_steps": _int(usage.get("tool_step_count")),
        "validation_passed": bool(status.get("validation_passed") or validation_after.get("passed")),
        "render_checked": bool(render_check.get("checked")),
        "render_passed": bool(render_check.get("checked") and render_check.get("passed")),
        "render_exit_code": _render_exit_code(render_check),
        "sdk_ok": bool(status.get("sdk_ok")),
        "execution_mode": execution_mode,
        "open_agent_completed": bool(status.get("open_agent_completed")),
        "repair_task_type": repair_task_type,
        "sdk_error_type": str(_dict(agent_messages.get("error")).get("type") or ""),
        "missing_artifacts": ";".join(missing),
    }


def _summary(round_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    stage_counts = dict(sorted(Counter(row["stage"] for row in rows).items()))
    hardcoding_scan = _read_json(round_dir / "hardcoding_scan.json")
    supported_rows = [row for row in rows if row["supported_contract_count"] > 0]
    repair_success_rows = [row for row in supported_rows if row["validation_passed"]]
    soft_rows = [row for row in rows if row["soft_contract_count"] > 0]
    soft_repair_success_rows = [row for row in soft_rows if row["validation_passed"]]
    open_task_rows = [row for row in rows if row["open_task_count"] > 0]
    open_agent_rows = [row for row in rows if row["execution_mode"] == "open_sdk_agent"]
    open_render_checked_rows = [row for row in open_task_rows if row["render_checked"]]
    open_render_passed_rows = [row for row in open_render_checked_rows if row["render_passed"]]
    repairable_success_rows = [row for row in rows if row["repairable_contract_count"] > 0 and row["validation_passed"]]
    render_checked_rows = [row for row in rows if row["render_checked"]]
    render_passed_rows = [row for row in rows if row["render_passed"]]
    render_break_rows = [row for row in render_checked_rows if not row["render_passed"]]
    render_unchecked_success_rows = [row for row in repairable_success_rows if not row["render_checked"]]
    audited_success_rows = [
        row for row in repair_success_rows if row["sdk_ok"] and row["render_checked"] and row["render_passed"]
    ]
    audited_soft_success_rows = [
        row for row in soft_repair_success_rows if row["sdk_ok"] and row["render_checked"] and row["render_passed"]
    ]
    validated_after_sdk_error_rows = [
        row for row in repair_success_rows if not row["sdk_ok"] and row["render_checked"] and row["render_passed"]
    ]
    direct_line_patch_rows = [row for row in rows if row["execution_mode"] == "direct_line_patch"]
    sdk_agent_rows = [row for row in rows if row["execution_mode"] == "sdk_agent"]
    direct_line_patch_success_rows = [
        row for row in repair_success_rows if row["execution_mode"] == "direct_line_patch"
    ]
    sdk_agent_success_rows = [row for row in repair_success_rows if row["execution_mode"] == "sdk_agent"]
    audited_direct_line_patch_success_rows = [
        row for row in audited_success_rows if row["execution_mode"] == "direct_line_patch"
    ]
    audited_sdk_agent_success_rows = [row for row in audited_success_rows if row["execution_mode"] == "sdk_agent"]
    reviewer_safe_fallback_rows = [row for row in rows if row["reviewer_safe_fallback_reason"]]
    json_parse_rows = [row for row in rows if (round_dir / "cases" / row["sample_id"] / "llm_review.json").exists()]
    total_tokens = [row["total_tokens"] for row in rows]
    agent_steps = [row["agent_tool_steps"] for row in rows]
    reviewer_elapsed = _numeric_values(rows, "reviewer_elapsed_sec")
    agent_elapsed = _numeric_values(rows, "agent_elapsed_sec")
    render_elapsed = _numeric_values(rows, "render_elapsed_sec")
    return {
        "round": round_dir.name,
        "case_count": len(rows),
        "stage_counts": stage_counts,
        "reviewer_json_parse_rate": _rate(len(json_parse_rows), len(rows)),
        "supported_case_count": len(supported_rows),
        "repair_success_count": len(repair_success_rows),
        "supported_repair_success_rate": _rate(len(repair_success_rows), len(supported_rows)),
        "overall_success_rate": _rate(len(repair_success_rows), len(rows)),
        "soft_case_count": len(soft_rows),
        "soft_repair_success_count": len(soft_repair_success_rows),
        "soft_repair_success_rate": _rate(len(soft_repair_success_rows), len(soft_rows)),
        "soft_overall_success_rate": _rate(len(soft_repair_success_rows), len(rows)),
        "discarded_issue_case_count": sum(1 for row in rows if row["discarded_issue_count"] > 0),
        "open_task_case_count": len(open_task_rows),
        "open_agent_attempt_count": len(open_agent_rows),
        "open_render_checked_count": len(open_render_checked_rows),
        "open_render_passed_count": len(open_render_passed_rows),
        "open_render_passed_rate": _rate(len(open_render_passed_rows), len(open_render_checked_rows)),
        "audited_repair_success_count": len(audited_success_rows),
        "audited_supported_success_rate": _rate(len(audited_success_rows), len(supported_rows)),
        "audited_overall_success_rate": _rate(len(audited_success_rows), len(rows)),
        "audited_soft_repair_success_count": len(audited_soft_success_rows),
        "audited_soft_repair_success_rate": _rate(len(audited_soft_success_rows), len(soft_rows)),
        "audited_soft_overall_success_rate": _rate(len(audited_soft_success_rows), len(rows)),
        "validated_after_sdk_error_count": len(validated_after_sdk_error_rows),
        "direct_line_patch_count": len(direct_line_patch_rows),
        "sdk_agent_attempt_count": len(sdk_agent_rows),
        "direct_line_patch_success_count": len(direct_line_patch_success_rows),
        "sdk_agent_success_count": len(sdk_agent_success_rows),
        "audited_direct_line_patch_success_count": len(audited_direct_line_patch_success_rows),
        "audited_sdk_agent_success_count": len(audited_sdk_agent_success_rows),
        "reviewer_safe_fallback_count": len(reviewer_safe_fallback_rows),
        "reviewer_output_invalid_count": sum(
            1 for row in reviewer_safe_fallback_rows if row["reviewer_safe_fallback_reason"] == "reviewer_output_invalid"
        ),
        "reviewer_transport_error_count": sum(
            1 for row in reviewer_safe_fallback_rows if row["reviewer_safe_fallback_reason"] == "reviewer_transport_error"
        ),
        "render_checked_count": len(render_checked_rows),
        "render_passed_count": len(render_passed_rows),
        "render_break_count": len(render_break_rows),
        "render_unchecked_success_count": len(render_unchecked_success_rows),
        "sdk_api_unavailable_count": stage_counts.get("sdk_api_unavailable", 0),
        "budget_exceeded_count": stage_counts.get("budget_exceeded", 0),
        "avg_total_tokens": round(mean(total_tokens), 2) if total_tokens else 0,
        "p95_total_tokens": _p95(total_tokens),
        "avg_agent_tool_steps": round(mean(agent_steps), 2) if agent_steps else 0,
        "avg_reviewer_elapsed_sec": round(mean(reviewer_elapsed), 3) if reviewer_elapsed else 0,
        "max_reviewer_elapsed_sec": round(max(reviewer_elapsed), 3) if reviewer_elapsed else 0,
        "avg_agent_elapsed_sec": round(mean(agent_elapsed), 3) if agent_elapsed else 0,
        "max_agent_elapsed_sec": round(max(agent_elapsed), 3) if agent_elapsed else 0,
        "avg_render_elapsed_sec": round(mean(render_elapsed), 3) if render_elapsed else 0,
        "max_render_elapsed_sec": round(max(render_elapsed), 3) if render_elapsed else 0,
        "missing_artifact_case_count": sum(1 for row in rows if row["missing_artifacts"]),
        "hardcoding_finding_count": _int(hardcoding_scan.get("finding_count")),
        "hardcoding_scan_ok": bool(hardcoding_scan.get("ok")) if hardcoding_scan else None,
        "cases": rows,
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary['round']} Summary",
            "",
            f"- case_count: {summary['case_count']}",
            f"- stage_counts: {json.dumps(summary['stage_counts'], ensure_ascii=False)}",
            f"- reviewer_json_parse_rate: {summary['reviewer_json_parse_rate']}",
            f"- supported_repair_success_rate: {summary['supported_repair_success_rate']}",
            f"- overall_success_rate: {summary['overall_success_rate']}",
            f"- soft_case_count: {summary['soft_case_count']}",
            f"- soft_repair_success_count: {summary['soft_repair_success_count']}",
            f"- soft_overall_success_rate: {summary['soft_overall_success_rate']}",
            f"- discarded_issue_case_count: {summary['discarded_issue_case_count']}",
            f"- open_task_case_count: {summary['open_task_case_count']}",
            f"- open_agent_attempt_count: {summary['open_agent_attempt_count']}",
            f"- open_render_passed_count: {summary['open_render_passed_count']}",
            f"- open_render_passed_rate: {summary['open_render_passed_rate']}",
            f"- audited_repair_success_count: {summary['audited_repair_success_count']}",
            f"- audited_overall_success_rate: {summary['audited_overall_success_rate']}",
            f"- audited_soft_repair_success_count: {summary['audited_soft_repair_success_count']}",
            f"- audited_soft_overall_success_rate: {summary['audited_soft_overall_success_rate']}",
            f"- validated_after_sdk_error_count: {summary['validated_after_sdk_error_count']}",
            f"- direct_line_patch_count: {summary['direct_line_patch_count']}",
            f"- sdk_agent_attempt_count: {summary['sdk_agent_attempt_count']}",
            f"- direct_line_patch_success_count: {summary['direct_line_patch_success_count']}",
            f"- sdk_agent_success_count: {summary['sdk_agent_success_count']}",
            f"- audited_direct_line_patch_success_count: {summary['audited_direct_line_patch_success_count']}",
            f"- audited_sdk_agent_success_count: {summary['audited_sdk_agent_success_count']}",
            f"- reviewer_safe_fallback_count: {summary['reviewer_safe_fallback_count']}",
            f"- reviewer_output_invalid_count: {summary['reviewer_output_invalid_count']}",
            f"- reviewer_transport_error_count: {summary['reviewer_transport_error_count']}",
            f"- render_checked_count: {summary['render_checked_count']}",
            f"- render_passed_count: {summary['render_passed_count']}",
            f"- render_break_count: {summary['render_break_count']}",
            f"- render_unchecked_success_count: {summary['render_unchecked_success_count']}",
            f"- avg_total_tokens: {summary['avg_total_tokens']}",
            f"- p95_total_tokens: {summary['p95_total_tokens']}",
            f"- avg_agent_tool_steps: {summary['avg_agent_tool_steps']}",
            f"- avg_reviewer_elapsed_sec: {summary['avg_reviewer_elapsed_sec']}",
            f"- avg_agent_elapsed_sec: {summary['avg_agent_elapsed_sec']}",
            f"- avg_render_elapsed_sec: {summary['avg_render_elapsed_sec']}",
            f"- sdk_api_unavailable_count: {summary['sdk_api_unavailable_count']}",
            f"- budget_exceeded_count: {summary['budget_exceeded_count']}",
            f"- hardcoding_finding_count: {summary['hardcoding_finding_count']}",
            "",
        ]
    )


def _experience_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary['round']} Experience",
            "",
            f"- case_count: {summary['case_count']}",
            f"- pass_rate: {summary['overall_success_rate']}",
            f"- supported_repair_success_rate: {summary['supported_repair_success_rate']}",
            f"- soft_pass_rate: {summary['soft_overall_success_rate']}",
            f"- open_repair_distribution: tasks={summary['open_task_case_count']}, attempts={summary['open_agent_attempt_count']}, render_passed={summary['open_render_passed_count']}",
            f"- audited_pass_rate: {summary['audited_overall_success_rate']}",
            f"- audited_soft_pass_rate: {summary['audited_soft_overall_success_rate']}",
            f"- validated_after_sdk_error_count: {summary['validated_after_sdk_error_count']}",
            f"- repair_mode_distribution: direct_line_patch={summary['direct_line_patch_count']}, sdk_agent={summary['sdk_agent_attempt_count']}",
            f"- repair_mode_successes: direct_line_patch={summary['direct_line_patch_success_count']}, sdk_agent={summary['sdk_agent_success_count']}",
            f"- reviewer_safe_fallbacks: total={summary['reviewer_safe_fallback_count']}, invalid_json={summary['reviewer_output_invalid_count']}, transport={summary['reviewer_transport_error_count']}",
            f"- render_distribution: checked={summary['render_checked_count']}, passed={summary['render_passed_count']}, broken={summary['render_break_count']}, unchecked_success={summary['render_unchecked_success_count']}",
            f"- token_distribution: avg={summary['avg_total_tokens']}, p95={summary['p95_total_tokens']}",
            f"- step_distribution: avg_agent_tool_steps={summary['avg_agent_tool_steps']}",
            f"- elapsed_distribution: reviewer_avg={summary['avg_reviewer_elapsed_sec']}s, agent_avg={summary['avg_agent_elapsed_sec']}s, render_avg={summary['avg_render_elapsed_sec']}s",
            "- generalizable_lessons: pending after full run analysis",
            "- rejected_case_specific_changes: none recorded by report generator",
            "- next_round_allowed_changes: input/prompt/schema/verifier changes must stay generic",
            "",
        ]
    )


def _audit_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary['round']} Audit Report",
            "",
            f"- case_count: {summary['case_count']}",
            f"- repair_success_count: {summary['repair_success_count']}",
            f"- soft_repair_success_count: {summary['soft_repair_success_count']}",
            f"- open_task_case_count: {summary['open_task_case_count']}",
            f"- open_agent_attempt_count: {summary['open_agent_attempt_count']}",
            f"- open_render_passed_count: {summary['open_render_passed_count']}",
            f"- audited_repair_success_count: {summary['audited_repair_success_count']}",
            f"- audited_soft_repair_success_count: {summary['audited_soft_repair_success_count']}",
            f"- validated_after_sdk_error_count: {summary['validated_after_sdk_error_count']}",
            f"- audited_direct_line_patch_success_count: {summary['audited_direct_line_patch_success_count']}",
            f"- audited_sdk_agent_success_count: {summary['audited_sdk_agent_success_count']}",
            f"- reviewer_safe_fallback_count: {summary['reviewer_safe_fallback_count']}",
            f"- reviewer_output_invalid_count: {summary['reviewer_output_invalid_count']}",
            f"- reviewer_transport_error_count: {summary['reviewer_transport_error_count']}",
            f"- sdk_api_unavailable_count: {summary['sdk_api_unavailable_count']}",
            f"- budget_exceeded_count: {summary['budget_exceeded_count']}",
            f"- missing_artifact_case_count: {summary['missing_artifact_case_count']}",
            "- original_samples_modified: not checked by report generator",
            f"- render_checked_count: {summary['render_checked_count']}",
            f"- render_passed_count: {summary['render_passed_count']}",
            f"- render_break_count: {summary['render_break_count']}",
            f"- render_unchecked_success_count: {summary['render_unchecked_success_count']}",
            f"- hardcoded_sample_rules: {summary['hardcoding_finding_count']}",
            f"- hardcoding_scan_ok: {summary['hardcoding_scan_ok']}",
            f"- audit_decision: {_audit_decision(summary)}",
            "",
        ]
    )


def _experience_filename(round_dir: Path) -> str:
    if round_dir.name == "round_0_baseline":
        return "round_0_experience.md"
    return f"{round_dir.name}_experience.md"


def _write_case_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CASE_CSV_FIELDS})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _render_exit_code(render_check: dict[str, Any]) -> str:
    if "exit_code" not in render_check:
        return ""
    return str(render_check.get("exit_code"))


def _reviewer_safe_fallback_reason(review: dict[str, Any]) -> str:
    reason = review.get("safe_fallback_reason")
    if isinstance(reason, str) and reason:
        return reason
    for issue in review.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("issue_type") or "")
        if issue_type in {"reviewer_output_invalid", "reviewer_transport_error"}:
            return issue_type
    return ""


def _execution_mode(agent_messages: dict[str, Any], token_usage: dict[str, Any]) -> str:
    mode = agent_messages.get("execution_mode")
    if isinstance(mode, str) and mode:
        return mode
    permission_summary = _dict(agent_messages.get("permission_summary")) or _dict(token_usage.get("permission_summary"))
    allowed_tools = permission_summary.get("allowed_tools")
    if permission_summary.get("permission_mode") == "direct":
        return "direct_line_patch"
    if isinstance(allowed_tools, list) and "direct_line_patch" in allowed_tools:
        return "direct_line_patch"
    if permission_summary or agent_messages:
        return "sdk_agent"
    return ""


def _audit_decision(summary: dict[str, Any]) -> str:
    if summary["render_break_count"] > 0:
        return "failed: render break detected"
    if summary["render_unchecked_success_count"] > 0:
        return "incomplete: validation successes need render_check evidence"
    if summary["missing_artifact_case_count"] > 0:
        return "incomplete: required artifacts are missing"
    if summary["hardcoding_finding_count"] > 0:
        return "failed: sample-specific hardcoding findings detected"
    return "complete for available contract and render evidence"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_or_empty(value: Any) -> float | str:
    if value in (None, ""):
        return ""
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return ""


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value == "":
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return ordered[index]
