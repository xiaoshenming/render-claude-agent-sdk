"""quality_repair.evidence — deterministic evidence directory writer."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .schemas import SCHEMA_VERSION, write_json
from .statuses import REPAIR_WORSE, SUCCESS_CLEAN, SUCCESS_DEGRADED


def evidence_dir_for(*, code_path: Path, job_id: str, evidence_root: Path | None) -> Path:
    root = evidence_root if evidence_root is not None else code_path.parent / "evidence"
    return root / _safe_component(job_id)


def write_bundle_manifest(evidence_dir: Path, payload: dict[str, Any]) -> None:
    body = {"schema_version": SCHEMA_VERSION, **payload}
    write_json(evidence_dir / "bundle_manifest.json", body)


def write_rounds(
    evidence_dir: Path,
    *,
    rounds: list[dict[str, Any]],
    input_code: str,
    final_code: str,
) -> None:
    for row in rounds:
        round_no = int(row.get("round", 0) or 0)
        round_dir = evidence_dir / f"round_{round_no:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        prompt_text = row.get("prompt_text")
        if isinstance(prompt_text, str):
            (round_dir / "prompt.md").write_text(prompt_text, encoding="utf-8")
        final_text = row.get("final_text")
        if isinstance(final_text, str):
            (round_dir / "final_response.txt").write_text(final_text, encoding="utf-8")
        if isinstance(row.get("agent_decision"), dict):
            write_json(round_dir / "agent_decision.json", {"schema_version": SCHEMA_VERSION, **dict(row["agent_decision"])})
        if isinstance(row.get("evidence_query"), dict):
            write_json(round_dir / "evidence_query.json", {"schema_version": SCHEMA_VERSION, **dict(row["evidence_query"])})
        usage_row = _usage_row_with_attempt_paths(round_dir, row, input_code=input_code)
        write_json(round_dir / "usage.json", {"schema_version": SCHEMA_VERSION, **usage_row})
        write_json(
            round_dir / "check_after" / "check_result.json",
            {"schema_version": SCHEMA_VERSION, **_check_after_payload(row)},
        )
        (round_dir / "sdk_messages.jsonl").touch()
        (round_dir / "diff.patch").write_text(_diff(input_code, final_code), encoding="utf-8")


def write_acceptance(evidence_dir: Path, report: dict[str, Any]) -> None:
    write_json(evidence_dir / "acceptance.json", report)


def write_summary(
    evidence_dir: Path,
    *,
    internal_status: str,
    external_status: str,
    before: dict[str, Any],
    after: dict[str, Any],
    changed: bool,
    reasons: list[str],
) -> None:
    before_count = _as_int(before.get("blocking_count"))
    after_count = _as_int(after.get("blocking_count"))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": external_status,
        "internal_status": internal_status,
        "passed": internal_status in (SUCCESS_CLEAN, SUCCESS_DEGRADED),
        "changed": changed,
        "improved": _improved(before_count, after_count),
        "worsened": internal_status == REPAIR_WORSE or _worsened(before_count, after_count),
        "before": dict(before),
        "after": dict(after),
        "reasons": list(reasons),
    }
    write_json(evidence_dir / "summary.json", payload)


def _safe_component(value: str) -> str:
    text = value or "unknown"
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in text)


def _diff(before: str, after: str, *, fromfile: str = "before/candidate.py", tofile: str = "after/candidate.py") -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def _usage_row_with_attempt_paths(round_dir: Path, row: dict[str, Any], *, input_code: str) -> dict[str, Any]:
    excluded_keys = {
        "base_code",
        "attempted_code",
        "check_after",
        "prompt_text",
        "usage",
        "agent_decision",
        "evidence_query",
        "final_text",
        "compose_report",
        "core_base_code",
        "core_attempted_code",
    }
    usage = {
        key: value
        for key, value in row.items()
        if key not in excluded_keys
    }
    if isinstance(row.get("agent_decision"), dict):
        usage["agent_decision_path"] = f"{round_dir.name}/agent_decision.json"
    if isinstance(row.get("evidence_query"), dict):
        usage["evidence_query_path"] = f"{round_dir.name}/evidence_query.json"
    if isinstance(row.get("final_text"), str):
        usage["final_response_path"] = f"{round_dir.name}/final_response.txt"
    if isinstance(row.get("compose_report"), dict):
        compose_path = round_dir / "compose_report.json"
        write_json(compose_path, {"schema_version": SCHEMA_VERSION, **dict(row["compose_report"])})
        usage["compose_report_path"] = _relative_evidence_path(compose_path, round_dir)
    usage.update(_flat_usage(row.get("usage")))
    base_code = row.get("base_code")
    attempted_code = row.get("attempted_code")
    if not isinstance(base_code, str):
        base_code = input_code
    if isinstance(attempted_code, str):
        _write_round_source_and_diff(
            round_dir,
            usage,
            before_name="candidate.full.before.py",
            after_name="candidate.full.after.py",
            diff_name="full_diff.patch",
            before_code=base_code,
            after_code=attempted_code,
            usage_key="full_diff_path",
            fromfile="before/candidate.py",
            tofile="after/candidate.py",
        )
        attempted_diff = _diff(base_code, attempted_code)
        if attempted_diff:
            attempted_path = round_dir / "attempted_diff.patch"
            attempted_path.write_text(attempted_diff, encoding="utf-8")
            usage["attempted_diff_path"] = _relative_evidence_path(attempted_path, round_dir)
            if not bool(row.get("accepted")):
                rejected_path = round_dir / "rejected_diff.patch"
                rejected_path.write_text(attempted_diff, encoding="utf-8")
                usage["rejected_diff_path"] = _relative_evidence_path(rejected_path, round_dir)
    core_base = row.get("core_base_code")
    core_attempted = row.get("core_attempted_code")
    if isinstance(core_base, str) and isinstance(core_attempted, str):
        _write_round_source_and_diff(
            round_dir,
            usage,
            before_name="core_candidate.before.py",
            after_name="core_candidate.after.py",
            diff_name="core_diff.patch",
            before_code=core_base,
            after_code=core_attempted,
            usage_key="core_diff_path",
            fromfile="before/core_candidate.py",
            tofile="after/core_candidate.py",
        )
    return usage


def _write_round_source_and_diff(
    round_dir: Path,
    usage: dict[str, Any],
    *,
    before_name: str,
    after_name: str,
    diff_name: str,
    before_code: str,
    after_code: str,
    usage_key: str,
    fromfile: str,
    tofile: str,
) -> None:
    before_path = round_dir / before_name
    after_path = round_dir / after_name
    diff_path = round_dir / diff_name
    before_path.write_text(before_code, encoding="utf-8")
    after_path.write_text(after_code, encoding="utf-8")
    diff = _diff(before_code, after_code, fromfile=fromfile, tofile=tofile)
    diff_path.write_text(diff, encoding="utf-8")
    usage[usage_key] = _relative_evidence_path(diff_path, round_dir)


def _flat_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value.get(key, 0)
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    }


def _check_after_payload(row: dict[str, Any]) -> dict[str, Any]:
    check_after = row.get("check_after")
    if isinstance(check_after, dict):
        return dict(check_after)
    return {
        "blocking_count": row.get("after_blocking", row.get("blocking")),
        "passed": row.get("after_blocking", row.get("blocking")) == 0,
        "issues": [],
        "signature": row.get("signature"),
        "error": row.get("error"),
    }


def _relative_evidence_path(path: Path, round_dir: Path) -> str:
    return f"{round_dir.name}/{path.name}"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _improved(before: int | None, after: int | None) -> bool:
    return before is not None and after is not None and after < before


def _worsened(before: int | None, after: int | None) -> bool:
    return before is not None and after is not None and after > before
