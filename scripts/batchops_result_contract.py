"""Versioned BatchOps result serialization for the SDK compatibility shim."""

import hashlib
import json
from pathlib import Path


def write_result(
    output: Path,
    *,
    status: str,
    decision: dict[str, object],
    logic: dict[str, object],
    layout: dict[str, object],
) -> None:
    payload = {
        "schema_version": "batchops.quality-agent.result.v2",
        "status": status,
        "logic": logic,
        "layout": layout,
        "harness_decision": decision.get("decision"),
        "agent_outcome": {
            "status": _outcome_status(status, decision),
            "code": decision.get("status") or decision.get("decision"),
            "reasons": decision.get("reasons") or [],
            "recoverable": bool(decision.get("best_render_passed")),
            "last_verified_revision_id": _best_revision(decision),
        },
        "artifact_identity": _artifact_identity(output, decision),
        "turns": decision.get("turns"),
        "tokens": decision.get("tokens"),
        "token_usage": token_usage(decision),
        "external_tool_ms": decision.get("external_tool_ms"),
        "harness_artifacts": "harness/",
    }
    (output / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def token_usage(decision: dict[str, object]) -> dict[str, object]:
    parent = decision.get("tokens")
    parent = parent if isinstance(parent, dict) else {}
    parent_total = int(parent.get("total_tokens") or 0)
    reviewer_total = int(decision.get("reviewer_tokens") or 0)
    entries = []
    if parent_total:
        entries.append({"operation": "parent", **parent})
    if reviewer_total:
        entries.append({"operation": "reviewers", "total_tokens": reviewer_total})
    complete = bool(decision.get("usage_complete", True))
    return {
        "schema_version": "batchops.token-usage.v2",
        "total_tokens": int(
            decision.get("total_tokens_with_reviewers")
            or parent_total + reviewer_total
        ),
        "entries": entries,
        "complete": complete,
        "missing_operations": [] if complete else ["parent"],
    }


def _outcome_status(status: str, decision: dict[str, object]) -> str:
    if status == "failed":
        return "failed"
    if decision.get("decision") == "HOLD":
        return "held"
    return "delivered"


def _best_revision(decision: dict[str, object]) -> object:
    best = decision.get("best_render_passed")
    return best.get("revision_id") if isinstance(best, dict) else None


def _artifact_identity(output: Path, decision: dict[str, object]) -> dict:
    return {
        "revision_id": (
            decision.get("final_revision_id")
            or decision.get("submitted_revision_id")
            or "R0"
        ),
        "candidate_code_sha256": _file_sha256(output / "candidate_final.py"),
        "video_sha256": _file_sha256(output / "video_final.mp4"),
    }


def _file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
