from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any

from .contract_builder import build_repair_contract
from .llm_client import chat_completion
from .llm_reviewer import ChatFunc, review_sample
from .open_task_builder import build_open_repair_task
from .review_input import build_review_input, write_review_input
from .settings import LlmConfig
from .validator import validate_contract
from .verifier import verify_review_payload


REQUIRED_PENDING_ARTIFACTS = (
    "llm_review",
    "verified_issues",
    "repair_contract",
    "agent_messages",
    "after_candidate",
    "validation_after",
    "token_usage",
)


def init_baseline_run(samples_root: Path, out_root: Path, *, limit: int | None = None) -> dict[str, Any]:
    samples_root = _resolve_samples_root(Path(samples_root))
    out_root = Path(out_root)
    round_dir = out_root / "round_0_baseline"
    cases_dir = round_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    sample_dirs = sorted(path for path in samples_root.iterdir() if path.is_dir())
    if limit is not None:
        sample_dirs = sample_dirs[:limit]

    cases = []
    for sample_dir in sample_dirs:
        case_dir = cases_dir / sample_dir.name
        case_dir.mkdir(parents=True, exist_ok=True)
        case_summary = _init_case(sample_dir, case_dir)
        cases.append(case_summary)

    summary = {
        "round": "round_0_baseline",
        "stage": "initialized",
        "case_count": len(cases),
        "samples_root": str(samples_root),
        "out_root": str(out_root),
        "cases": cases,
    }
    _write_json(round_dir / "summary.json", summary)
    _write_text(round_dir / "round_0_experience.md", _experience_template(summary))
    _write_text(round_dir / "audit_report.md", _audit_template(summary))
    return summary


def _resolve_samples_root(samples_root: Path) -> Path:
    direct_samples = [path for path in samples_root.iterdir() if path.is_dir() and (path / "candidate.py").exists()]
    if direct_samples:
        return samples_root
    nested = samples_root / "samples"
    if nested.exists() and nested.is_dir():
        nested_samples = [path for path in nested.iterdir() if path.is_dir() and (path / "candidate.py").exists()]
        if nested_samples:
            return nested
    return samples_root


def advance_case_from_review(
    case_dir: Path,
    *,
    allow_soft_repair: bool = False,
    allow_open_repair: bool = False,
) -> dict[str, Any]:
    case_dir = Path(case_dir)
    review_path = case_dir / "llm_review.json"
    if not review_path.exists():
        raise FileNotFoundError(f"llm_review.json not found: {review_path}")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    verified = verify_review_payload(review, allow_soft_repair=allow_soft_repair)
    verified_path = case_dir / "verified_issues.json"
    _write_json(verified_path, verified)

    candidate_path = case_dir / "before_candidate.py"
    contract = build_repair_contract(candidate_path, verified, include_soft=allow_soft_repair)
    contract_path = case_dir / "repair_contract.json"
    _write_json(contract_path, contract)

    validation = validate_contract(candidate_path, contract_path)
    _write_json(case_dir / "validation_before_contract.json", validation)

    open_task = build_open_repair_task(case_dir, review)
    open_task_count = int(open_task.get("issue_count") or 0)
    if allow_open_repair and open_task_count > 0:
        _write_json(case_dir / "open_repair_task.json", open_task)

    no_review_issues = not verified["issues"] and str(review.get("decision") or "").lower() == "pass"
    repairable_contract_count = int(contract.get("repairable_contract_count") or contract.get("supported_contract_count") or 0)
    ok_to_repair = repairable_contract_count > 0 and not validation["passed"]
    if no_review_issues:
        next_stage = "review_passed_no_repair"
    elif ok_to_repair:
        next_stage = "pending_agent"
    elif allow_open_repair and open_task_count > 0:
        next_stage = "pending_open_agent"
    else:
        next_stage = "needs_human_review"
    status = _read_status(case_dir)
    for key in ("sdk_ok", "validation_passed", "usage", "permission_summary"):
        status.pop(key, None)
    status.update(
        {
            "stage": next_stage,
            "ok_to_repair": ok_to_repair,
            "supported_contract_count": contract["supported_contract_count"],
            "soft_contract_count": contract.get("soft_contract_count", 0),
            "repairable_contract_count": repairable_contract_count,
            "needs_human_review_count": verified["needs_human_review_count"],
            "allow_soft_repair": allow_soft_repair,
            "allow_open_repair": allow_open_repair,
            "open_task_count": open_task_count if allow_open_repair else 0,
        }
    )
    status["artifacts"].update(
        {
            "llm_review": "ready",
            "verified_issues": "ready",
            "repair_contract": "ready",
            "validation_before": "ready",
            "agent_messages": "pending",
            "after_candidate": "pending",
            "validation_after": "pending",
            "token_usage": "pending",
            "open_repair_task": "ready" if allow_open_repair and open_task_count > 0 else "not_applicable",
        }
    )
    _write_json(case_dir / "case_status.json", status)
    return status


def run_case_reviewer(
    case_dir: Path,
    config: LlmConfig,
    *,
    chat: ChatFunc = chat_completion,
) -> dict[str, Any]:
    case_dir = Path(case_dir)
    _ensure_working_candidate(case_dir)
    write_review_input(case_dir, case_dir / "review_input.json")
    review_path = case_dir / "llm_review.json"
    try:
        review_sample(case_dir, review_path, config, chat=chat)
    except Exception as exc:  # noqa: BLE001 - case boundary must not abort the whole round
        _write_reviewer_exception_artifacts(case_dir, exc)
        status = _read_status(case_dir)
        status.update(
            {
                "stage": "pending_verifier",
                "ok_to_repair": False,
            }
        )
        status.pop("reviewer_error", None)
        status["artifacts"].update(
            {
                "llm_review": "ready",
                "llm_review_error": "ready",
            }
        )
        _write_json(case_dir / "case_status.json", status)
        return status

    status = _read_status(case_dir)
    stale_error = case_dir / "llm_review_error.json"
    used_safe_fallback = _review_used_safe_fallback(review_path)
    if stale_error.exists() and not used_safe_fallback:
        stale_error.unlink()
    status.update({"stage": "pending_verifier"})
    status.pop("reviewer_error", None)
    status["artifacts"].update({"llm_review": "ready"})
    if used_safe_fallback and stale_error.exists():
        status["artifacts"]["llm_review_error"] = "ready"
    else:
        status["artifacts"].pop("llm_review_error", None)
    _write_json(case_dir / "case_status.json", status)
    return status


def _write_reviewer_exception_artifacts(case_dir: Path, exc: Exception) -> None:
    status = _read_status(case_dir)
    sample_id = str(status.get("sample_id") or case_dir.name)
    error_type = type(exc).__name__
    error_message = str(exc)
    review = {
        "schema_version": "logic_engine_mvp.llm_review.v1",
        "sample_id": sample_id,
        "issues": [
            {
                "issue_type": "reviewer_transport_error",
                "severity": "blocking",
                "confidence": 0.0,
                "evidence": "Reviewer call failed before a parseable review could be produced.",
                "wrong_claim": "The current sample logic review could not be completed reliably.",
                "expected": "A human or a later retry must inspect the sample before automatic repair.",
                "needs_review_reason": f"Reviewer transport failed: {error_type}.",
                "needs_python_verifier": False,
                "repairability": "needs_human_review",
            }
        ],
        "decision": "needs_human_review",
        "elapsed_sec": 0.0,
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "attempt_count": 0,
        },
        "retry_count": 0,
        "discarded_issue_count": 0,
        "reviewer_raw_keys": ["safe_fallback_reason"],
        "safe_fallback_reason": "reviewer_transport_error",
    }
    error = {
        "schema_version": "logic_engine_mvp.llm_review_error.v1",
        "error_type": error_type,
        "error_message": error_message,
        "usage": review["usage"],
        "raw_content_preview": "",
    }
    _write_json(case_dir / "llm_review.json", review)
    _write_json(case_dir / "llm_review_error.json", error)


def _review_used_safe_fallback(review_path: Path) -> bool:
    try:
        review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    raw_keys = review.get("reviewer_raw_keys") if isinstance(review, dict) else []
    if isinstance(raw_keys, list) and "safe_fallback_reason" in raw_keys:
        return True
    issues = review.get("issues") if isinstance(review, dict) else []
    return any(isinstance(issue, dict) and issue.get("issue_type") == "reviewer_output_invalid" for issue in issues or [])


def _ensure_working_candidate(case_dir: Path) -> None:
    candidate_path = case_dir / "candidate.py"
    if candidate_path.exists():
        return
    before_path = case_dir / "before_candidate.py"
    if not before_path.exists():
        raise FileNotFoundError(f"candidate.py not found and no baseline copy exists: {candidate_path}")
    shutil.copy2(before_path, candidate_path)


def _init_case(sample_dir: Path, case_dir: Path) -> dict[str, Any]:
    candidate = sample_dir / "candidate.py"
    if not candidate.exists():
        raise FileNotFoundError(f"candidate.py not found: {candidate}")

    before_candidate = case_dir / "before_candidate.py"
    shutil.copy2(candidate, before_candidate)
    shutil.copy2(candidate, case_dir / "candidate.py")
    for name in ("case_manifest.json", "sample_meta.json", "before.mp4", "problem_text.txt", "source_info.txt"):
        _copy_optional(sample_dir / name, case_dir / name)

    review_input = build_review_input(sample_dir)
    _write_json(case_dir / "review_input.json", review_input)
    validation_before = _validate_before(candidate)
    _write_json(case_dir / "validation_before.json", validation_before)

    status = {
        "sample_id": sample_dir.name,
        "stage": "pending_reviewer",
        "ok_to_repair": False,
        "artifacts": {
            "review_input": "ready",
            "before_candidate": "ready",
            "validation_before": "ready",
            **{name: "pending" for name in REQUIRED_PENDING_ARTIFACTS},
        },
    }
    _write_json(case_dir / "case_status.json", status)
    return {
        "sample_id": sample_dir.name,
        "case_dir": str(case_dir),
        "parse_ok": validation_before["parse_ok"],
        "stage": status["stage"],
    }


def _read_status(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "case_status.json"
    if not path.exists():
        return {"artifacts": {}}
    status = json.loads(path.read_text(encoding="utf-8"))
    status.setdefault("artifacts", {})
    return status


def _validate_before(candidate: Path) -> dict[str, Any]:
    text = candidate.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(text)
        return {
            "ok": True,
            "parse_ok": True,
            "render_checked": False,
            "overlap_checked": False,
            "note": "Baseline init only. Render and overlap are intentionally not executed here.",
        }
    except SyntaxError as exc:
        return {
            "ok": False,
            "parse_ok": False,
            "error": f"{exc.msg} at line {exc.lineno}",
            "render_checked": False,
            "overlap_checked": False,
        }


def _experience_template(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Round 0 Experience",
            "",
            f"- stage: {summary['stage']}",
            f"- case_count: {summary['case_count']}",
            "- pass_rate: pending",
            "- token_distribution: pending",
            "- step_distribution: pending",
            "- generalizable_lessons: pending",
            "- rejected_case_specific_changes: none at initialization",
            "",
        ]
    )


def _audit_template(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Round 0 Audit Report",
            "",
            f"- stage: {summary['stage']}",
            f"- case_count: {summary['case_count']}",
            "- original_samples_modified: no",
            "- hardcoded_sample_rules: pending scan",
            "- repair_success_count: pending",
            "- render_break_count: pending",
            "",
        ]
    )


def _copy_optional(src: Path, dest: Path) -> None:
    if src.exists():
        shutil.copy2(src, dest)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
