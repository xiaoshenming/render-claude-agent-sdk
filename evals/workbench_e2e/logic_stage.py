from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from evals._logic_repair_case import RepairRunConfig, run_repair_case
from evals._logic_shadow_case import ShadowRunConfig, run_shadow_case
from manim_quality.logic.eval_manifest import EvalArtifact, FrozenEvalCase
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.shadow import EvalTruth
from manim_quality.revisions.fingerprint import sha256_bytes


@dataclass(frozen=True, slots=True)
class LogicStageConfig:
    model: str
    provider_env: dict[str, str]
    input_version: ReviewInputVersion = ReviewInputVersion.DIGEST_V2_1


@dataclass(frozen=True, slots=True)
class LogicStageResult:
    status: str
    decision: str | None
    candidate_path: Path
    review_elapsed_ms: int
    repair_elapsed_ms: int
    review_tokens: int
    repair_tokens: int
    error: str | None = None


def run_logic_stage(
    *,
    job_id: str,
    candidate: Path,
    problem: str,
    expected_solution: str,
    baseline_video: Path,
    output_dir: Path,
    config: LogicStageConfig,
) -> LogicStageResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = output_dir / "dataset"
    dataset.mkdir(exist_ok=True)
    _copy(candidate, dataset / "candidate.py")
    _copy(baseline_video, dataset / "before.mp4")
    (dataset / "problem_text.txt").write_text(problem, encoding="utf-8")
    (dataset / "expected_solution.txt").write_text(expected_solution, encoding="utf-8")
    case = _case(job_id, dataset)
    review_root = output_dir / "review"
    started = time.perf_counter()
    reviewed = run_shadow_case(
        case,
        dataset_root=dataset,
        config=ShadowRunConfig(
            model=config.model,
            provider_env=config.provider_env,
            output_root=review_root,
            input_version=config.input_version,
        ),
    )
    review_elapsed = round((time.perf_counter() - started) * 1_000)
    decision = reviewed.decision.value if reviewed.decision else None
    review_tokens = _shadow_tokens(reviewed)
    if reviewed.error:
        return _finish(
            output_dir,
            LogicStageResult(
                "review_error",
                decision,
                candidate,
                review_elapsed,
                0,
                review_tokens,
                0,
                reviewed.error,
            ),
        )
    if decision == "pass":
        return _finish(
            output_dir,
            LogicStageResult(
                "review_pass",
                decision,
                candidate,
                review_elapsed,
                0,
                review_tokens,
                0,
            ),
        )
    if decision == "record_only" and _record_only_allowed(review_root, job_id):
        return _finish(
            output_dir,
            LogicStageResult(
                "review_record_only",
                decision,
                candidate,
                review_elapsed,
                0,
                review_tokens,
                0,
                "low_risk_record_only_warning",
            ),
        )
    if decision != "needs_repair":
        return _finish(
            output_dir,
            LogicStageResult(
                "human_review",
                decision,
                candidate,
                review_elapsed,
                0,
                review_tokens,
                0,
                "reviewer did not issue an automatic pass or repair decision",
            ),
        )
    repair_root = output_dir / "repair"
    started = time.perf_counter()
    repaired = run_repair_case(
        case,
        dataset_root=dataset,
        config=RepairRunConfig(
            config.model,
            config.provider_env,
            review_root,
            repair_root,
        ),
    )
    repair_elapsed = round((time.perf_counter() - started) * 1_000)
    repair_tokens = (
        repaired.coder_usage.total_tokens + repaired.verifier_usage.total_tokens
    )
    patched = repair_root / "cases" / job_id / "candidate_after.py"
    if repaired.status == "candidate_ready" and patched.is_file():
        accepted = output_dir / "candidate_after.py"
        _copy(patched, accepted)
        status = "candidate_ready"
    else:
        accepted = candidate
        status = repaired.status
    return _finish(
        output_dir,
        LogicStageResult(
            status,
            decision,
            accepted,
            review_elapsed,
            repair_elapsed,
            review_tokens,
            repair_tokens,
            repaired.error,
        ),
    )


def _case(job_id: str, root: Path) -> FrozenEvalCase:
    names = ("candidate.py", "problem_text.txt", "expected_solution.txt", "before.mp4")
    artifacts = {
        name: EvalArtifact(name, sha256_bytes((root / name).read_bytes()))
        for name in names
    }
    return FrozenEvalCase(job_id, EvalTruth.KNOWN_GOOD, artifacts)


def _shadow_tokens(result) -> int:
    return (
        result.input_tokens
        + result.output_tokens
        + result.cache_read_tokens
        + result.cache_write_tokens
    )


def _record_only_allowed(review_root: Path, job_id: str) -> bool:
    path = review_root / "cases" / job_id / "review_report.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    issues = report.get("issues") if isinstance(report, dict) else None
    return (
        report.get("decision") == "record_only"
        and report.get("blocked") is False
        and report.get("requires_human_review") is False
        and isinstance(issues, list)
        and bool(issues)
        and all(
            isinstance(issue, dict) and issue.get("severity") == "low"
            for issue in issues
        )
    )


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _finish(output_dir: Path, result: LogicStageResult) -> LogicStageResult:
    payload = asdict(result)
    payload["candidate_path"] = str(result.candidate_path)
    (output_dir / "logic_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result
