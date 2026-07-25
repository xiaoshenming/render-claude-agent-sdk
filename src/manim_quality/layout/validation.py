"""Structural validation of untrusted vendor overlap results."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .result_mapping import VendorResult


class RepairRequest(Protocol):
    code_path: Path
    evidence_root: Path
    remaining_tokens: int


def result_violation(result: VendorResult, request: RepairRequest) -> str | None:
    if (
        type(result.tokens_used) is not int
        or not 0 <= result.tokens_used <= request.remaining_tokens
    ):
        return "vendor_usage_exceeds_remaining_budget"
    if type(result.rounds_used) is not int or not 0 <= result.rounds_used <= 2:
        return "vendor_rounds_exceed_platform_budget"
    if not isinstance(result.before, dict) or not isinstance(result.after, dict):
        return "vendor_check_evidence_invalid"
    evidence = _resolved_directory(result.evidence_dir)
    if evidence is None or not _is_within(evidence, request.evidence_root.resolve()):
        return "vendor_evidence_outside_request_root"
    if result.status in {"SUCCESS_CLEAN", "SUCCESS_DEGRADED"}:
        candidate = _resolved_file(result.code_path)
        if candidate is None or not _is_within(candidate, evidence):
            return "vendor_candidate_outside_evidence"
    return None


def _resolved_directory(path: Path | None) -> Path | None:
    try:
        if path is None or path.is_symlink() or not path.is_dir():
            return None
        return path.resolve(strict=True)
    except OSError:
        return None


def _resolved_file(path: Path) -> Path | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.resolve(strict=True)
    except OSError:
        return None


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
