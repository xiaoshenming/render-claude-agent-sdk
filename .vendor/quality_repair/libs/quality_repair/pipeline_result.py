"""Result finalization helpers for api.repair."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent.controller import LoopResult
from .api_types import RepairBundle, RepairResult
from .evidence import write_acceptance, write_bundle_manifest, write_summary
from .pipeline_io import external_status
from .schemas import AcceptanceReport, CheckResult, RepairabilityDecision
from .statuses import REPAIR_WORSE, SUCCESS_CLEAN, SUCCESS_DEGRADED


def early_finish(
    *,
    bundle: RepairBundle,
    evidence_dir: Path,
    workdir: Path,
    status: str,
    repairability: str,
    before: CheckResult,
    reasons: list[str],
    manifest: dict[str, Any],
) -> RepairResult:
    report = AcceptanceReport(
        status=status,
        gates={},
        reasons=list(reasons),
        before=before.to_dict(),
        after=before.to_dict(),
    )
    return finish(
        bundle=bundle,
        evidence_dir=evidence_dir,
        status=status,
        code_path=bundle.code_path,
        repairability=repairability,
        before=before.to_dict(),
        after=before.to_dict(),
        rounds_used=0,
        tokens_used=0,
        reasons=list(reasons),
        acceptance=report,
        manifest=manifest,
    )


def finish_after_loop(
    *,
    bundle: RepairBundle,
    evidence_dir: Path,
    workdir: Path,
    decision: RepairabilityDecision,
    before: CheckResult,
    loop: LoopResult,
    acceptance: AcceptanceReport,
    manifest: dict[str, Any],
) -> RepairResult:
    internal_status = acceptance.status
    external = external_status(internal_status)
    success = internal_status in (SUCCESS_CLEAN, SUCCESS_DEGRADED)
    code_path = workdir / "candidate.py" if success else bundle.code_path
    reasons = list(acceptance.reasons)
    if loop.stop_reason and loop.stop_reason not in reasons:
        reasons.append(loop.stop_reason)
    if loop.stop_reason.startswith("runner_error") and "runner_error" not in reasons:
        reasons.append("runner_error")
    if loop.stop_reason.startswith("check_error") and "check_error" not in reasons:
        reasons.append("check_error")
    if internal_status == REPAIR_WORSE:
        reasons.append("repair_worse_rolled_back")
    return finish(
        bundle=bundle,
        evidence_dir=evidence_dir,
        status=external,
        code_path=code_path,
        repairability=decision.classification,
        before=acceptance.before or before.to_dict(),
        after=acceptance.after or loop.best_check.to_dict(),
        rounds_used=loop.rounds_used,
        tokens_used=loop.tokens_used,
        reasons=reasons,
        acceptance=acceptance,
        manifest=manifest,
        internal_status=internal_status,
    )


def finish(
    *,
    bundle: RepairBundle,
    evidence_dir: Path,
    status: str,
    code_path: Path,
    repairability: str,
    before: dict[str, Any],
    after: dict[str, Any],
    rounds_used: int,
    tokens_used: int,
    reasons: list[str],
    acceptance: AcceptanceReport,
    manifest: dict[str, Any],
    internal_status: str | None = None,
) -> RepairResult:
    internal = internal_status or acceptance.status
    manifest.update({"status": status, "internal_status": internal, "reasons": list(reasons)})
    write_bundle_manifest(evidence_dir, manifest)
    write_acceptance(evidence_dir, acceptance.to_dict())
    write_summary(
        evidence_dir,
        internal_status=internal,
        external_status=status,
        before=before,
        after=after,
        changed=code_path != bundle.code_path,
        reasons=reasons,
    )
    return RepairResult(
        status=status,
        code_path=code_path,
        repairability=repairability,
        before=before,
        after=after,
        rounds_used=rounds_used,
        tokens_used=tokens_used,
        evidence_dir=evidence_dir,
        reasons=reasons,
    )
