from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from manim_quality.layout import (
    MaterializedQualityRepair,
    OverlapAdapter,
    OverlapDisposition,
    OverlapRepairRequest,
)
from manim_quality.layout.classification import ImpactClassifyingChecker
from manim_quality.layout.impact_policy import issue_summary

from .layout_probe import (
    LocalLayoutProbeChecker,
    build_layout_context,
    configure_vendor_sdk,
)


@dataclass(frozen=True, slots=True)
class LayoutStageConfig:
    python: str
    probe_source_path: Path
    vendor_root: Path
    model: str = "gemini-3.5-flash-high"
    provider_env: dict[str, str] | None = None
    timeout_seconds: int = 180
    token_budget: int = 60_000
    allow_vendor_clean_fallback: bool = False


@dataclass(frozen=True, slots=True)
class LayoutStageResult:
    status: str
    candidate_path: Path
    before_blocking: int
    after_blocking: int
    rounds: int
    tokens: int
    elapsed_ms: int
    requires_render_recheck: bool
    error: str | None = None
    issue_summary: dict[str, Any] | None = None


def run_layout_stage(
    *,
    job_id: str,
    candidate: Path,
    output_dir: Path,
    config: LayoutStageConfig,
) -> LayoutStageResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    backend = MaterializedQualityRepair(config.vendor_root)
    configure_vendor_sdk(config)
    checker = LocalLayoutProbeChecker(config, backend.api.CheckResult)
    classified_checker = ImpactClassifyingChecker(checker)
    initial = classified_checker.run_check(candidate, output_dir / "detect")
    summary = _summary(initial)
    if not initial.ok:
        return _finish(
            output_dir,
            LayoutStageResult(
                "detection_error",
                candidate,
                -1,
                -1,
                0,
                0,
                _elapsed(started),
                False,
                initial.error,
                summary,
            ),
        )
    if initial.passed:
        return _finish(
            output_dir,
            LayoutStageResult(
                "clean",
                candidate,
                0,
                0,
                0,
                0,
                _elapsed(started),
                False,
                issue_summary=summary,
            ),
        )
    classified_payload = {
        "ok": initial.ok,
        "passed": initial.passed,
        "blocking_count": initial.blocking_count,
        "issues": list(initial.issues),
        "raw": dict(initial.raw),
    }
    context = build_layout_context(
        config.vendor_root, classified_payload, checker.last_probe
    )
    context_path = output_dir / "layout_context.json"
    _write_json(context_path, context)
    request = OverlapRepairRequest(
        job_id=job_id,
        code_path=candidate,
        layout_context_path=context_path,
        evidence_root=output_dir / "repair_evidence",
        remaining_tokens=config.token_budget,
    )
    repaired = OverlapAdapter(backend).repair(request, checker)
    fallback = (
        _vendor_clean_candidate(repaired)
        if config.allow_vendor_clean_fallback
        else None
    )
    if fallback is not None:
        return _finish(
            output_dir,
            LayoutStageResult(
                "vendor_clean_recheck_required",
                fallback,
                repaired.before_blocking,
                repaired.after_blocking,
                repaired.rounds_used,
                repaired.tokens_used,
                _elapsed(started),
                True,
                "platform_semantic_guard_recorded",
                summary,
            ),
        )
    error = (
        ";".join(repaired.reasons)
        if repaired.disposition
        in {OverlapDisposition.ERROR, OverlapDisposition.REJECTED}
        else None
    )
    return _finish(
        output_dir,
        LayoutStageResult(
            repaired.disposition.value,
            repaired.code_path,
            repaired.before_blocking,
            repaired.after_blocking,
            repaired.rounds_used,
            repaired.tokens_used,
            _elapsed(started),
            repaired.requires_external_render_recheck,
            error,
            summary,
        ),
    )


def _vendor_clean_candidate(repaired) -> Path | None:
    if (
        repaired.disposition is not OverlapDisposition.REJECTED
        or repaired.vendor_status != "SUCCESS_CLEAN"
        or repaired.after_blocking != 0
        or repaired.evidence_dir is None
    ):
        return None
    root = repaired.evidence_dir
    summary = _read_json(root / "summary.json")
    acceptance = _read_json(root / "acceptance.json")
    candidate = root / "workdir" / "candidate.py"
    gates = acceptance.get("gates") if isinstance(acceptance, dict) else None
    required = {"compile": "pass", "recheck": "pass", "diff_audit": "pass"}
    if (
        summary.get("passed") is True
        and isinstance(gates, dict)
        and all(gates.get(name) == value for name, value in required.items())
        and candidate.is_file()
    ):
        return candidate
    return None


def _elapsed(started: float) -> int:
    return round((time.perf_counter() - started) * 1_000)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _finish(output_dir: Path, result: LayoutStageResult) -> LayoutStageResult:
    payload = asdict(result)
    payload["candidate_path"] = str(result.candidate_path)
    _write_json(output_dir / "layout_summary.json", payload)
    return result


def _summary(result: Any) -> dict[str, Any]:
    raw = dict(getattr(result, "raw", {}) or {})
    warnings = list(raw.get("platform_warnings") or [])
    return issue_summary(
        blocking=list(getattr(result, "issues", []) or []),
        warnings=warnings,
        raw_count=int(raw.get("platform_raw_blocking_count", result.blocking_count)),
    )
