#!/usr/bin/env python3
"""batchops compatibility entrypoint for the unified Quality Harness.

Speaks the frozen `batchops.quality-agent.result.v1` contract expected by
apps/batchops/render/app/quality_agent/runner.py:

- reads the legacy CLI arguments (--code/--problem/--baseline-video/...)
- runs the unified operator (python -m manim_quality.operator semantics)
- writes result.json + candidate_final.py + video_final.mp4 into --output
- exits 0 for deliver/deliver_with_warning; any other exit fail-opens

Status mapping keeps batchops fail-open semantics: PROPOSED delivers the
candidate; HOLD delivers the untouched Before pair with warning evidence;
FAILED exits non-zero so the runner keeps Before via fail_open.
Deployment note: the release directory must contain a RELEASE_COMMIT file
matching BATCHOPS_QUALITY_AGENT_COMMIT (runner provenance check).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from batchops_result_contract import write_result

_PROXY_VARIABLES = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    _strip_proxies()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    harness_root = output / "harness"
    exit_code = _run_operator(args, harness_root)
    decision = _read_decision(harness_root)
    verdict = str(decision.get("decision") or "FAILED")
    if verdict == "PROPOSED":
        return _emit_proposed(args, output, harness_root, decision)
    if verdict == "HOLD":
        return _emit_hold(args, output, decision)
    _emit_failed(output, decision, exit_code)
    print(
        f"quality harness terminal state: {verdict} (exit {exit_code}); "
        "failing open",
        file=sys.stderr,
    )
    return 3


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--problem", type=Path, required=True)
    parser.add_argument("--baseline-video", type=Path, required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument(
        "--runtime-python-path",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--solution-steps", type=Path)
    parser.add_argument("--parsed-standard-answer", type=Path)
    parser.add_argument("--reviewer-supplemental-notes", type=Path)
    parser.add_argument("--repair-feedback", type=Path)
    # Deprecated compatibility alias; interpreted as solution_steps when the
    # canonical argument is absent.
    parser.add_argument("--expected-solution", type=Path)
    parser.add_argument("--logic-mode", default="one_shot")
    parser.add_argument("--layout-token-budget", type=int, default=180_000)
    parser.add_argument("--allow-vendor-clean-fallback", action="store_true")
    parser.add_argument("--render-cache-dir", type=Path)
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print(f"ignoring unknown arguments: {unknown}", file=sys.stderr)
    return args


def _strip_proxies() -> None:
    for name in _PROXY_VARIABLES:
        os.environ.pop(name, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def _run_operator(args: argparse.Namespace, harness_root: Path) -> int:
    from manim_quality.operator.cli import main as operator_main

    if args.base_url:
        os.environ["ANTHROPIC_BASE_URL"] = args.base_url
    workspace = args.code.resolve(strict=True).parent
    candidate = _session_candidate(args.code, harness_root)
    argv = [
        "--candidate",
        str(candidate),
        "--problem",
        str(args.problem.resolve(strict=True)),
        "--workspace",
        str(workspace),
        "--output",
        str(harness_root),
        "--model",
        args.model,
        "--manim-python",
        str(args.manim_python.resolve(strict=True)),
        "--run-id",
        args.job_id,
    ]
    _append_review_inputs(argv, args)
    if args.repair_feedback is not None:
        argv.extend((
            "--repair-feedback",
            str(args.repair_feedback.resolve(strict=True)),
        ))
    assets = workspace / "assets"
    if assets.is_dir():
        argv.extend(("--assets-dir", str(assets)))
    for path in args.runtime_python_path:
        argv.extend(("--runtime-python-path", str(path.resolve(strict=True))))
    if args.render_cache_dir is not None:
        cache = args.render_cache_dir.resolve()
        cache.mkdir(parents=True, exist_ok=True)
        argv.extend(("--render-cache-dir", str(cache)))
    try:
        return operator_main(argv)
    except SystemExit as error:
        return int(error.code or 0)
    except Exception as error:
        print(f"quality harness crashed: {error}", file=sys.stderr)
        return 4


def _append_review_inputs(argv: list[str], args: argparse.Namespace) -> None:
    values = (
        ("--solution-steps", args.solution_steps or args.expected_solution),
        ("--parsed-standard-answer", args.parsed_standard_answer),
        ("--reviewer-supplemental-notes", args.reviewer_supplemental_notes),
    )
    for flag, path in values:
        if path is not None:
            argv.extend((flag, str(path.resolve(strict=True))))


def _session_candidate(source: Path, harness_root: Path) -> Path:
    """Create the only Agent-editable copy while preserving caller R0."""
    session = harness_root.parent / "session_workspace"
    session.mkdir(parents=True, exist_ok=True)
    candidate = session / "candidate.py"
    shutil.copyfile(source.resolve(strict=True), candidate)
    return candidate.resolve(strict=True)


def _read_decision(harness_root: Path) -> dict[str, object]:
    path = harness_root / "output" / "decision.json"
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _emit_proposed(
    args: argparse.Namespace,
    output: Path,
    harness_root: Path,
    decision: dict[str, object],
) -> int:
    candidate = harness_root / "output" / "proposed_candidate.py"
    video = _final_video(
        harness_root, decision, render_cache_dir=args.render_cache_dir)
    if not candidate.is_file() or video is None:
        print("PROPOSED artifacts missing; failing open", file=sys.stderr)
        return 3
    final_code = output / "candidate_final.py"
    shutil.copyfile(candidate, final_code)
    shutil.copyfile(video, output / "video_final.mp4")
    write_result(
        output,
        status="deliver",
        decision=decision,
        logic={
            "status": "candidate_ready",
            "candidate_path": str(final_code),
            "final_revision_id": decision.get("final_revision_id"),
        },
        layout={"status": "pass", "blocking_count": 0},
    )
    return 0


def _emit_hold(
    args: argparse.Namespace,
    output: Path,
    decision: dict[str, object],
) -> int:
    shutil.copyfile(args.code.resolve(strict=True), output / "candidate_final.py")
    shutil.copyfile(
        args.baseline_video.resolve(strict=True), output / "video_final.mp4"
    )
    write_result(
        output,
        status="deliver_with_warning",
        decision=decision,
        logic={"status": "hold"},
        layout={
            "status": "hold",
            "risk_codes": ["quality_hold_before_retained"],
            "reasons": decision.get("reasons"),
            "best_render_passed": decision.get("best_render_passed"),
        },
    )
    return 0


def _emit_failed(
    output: Path,
    decision: dict[str, object],
    exit_code: int,
) -> None:
    write_result(
        output,
        status="failed",
        decision=decision,
        logic={"status": "failed"},
        layout={
            "status": "failed",
            "risk_codes": ["quality_agent_failed_before_retained"],
            "reasons": decision.get("reasons") or [decision.get("status")],
            "exit_code": exit_code,
            "best_render_passed": decision.get("best_render_passed"),
        },
    )

def _final_video(
    harness_root: Path,
    decision: dict[str, object],
    *,
    render_cache_dir: Path | None = None,
) -> Path | None:
    revision = str(
        decision.get("final_revision_id")
        or decision.get("submitted_revision_id")
        or ""
    )
    roots = [
        harness_root / "acceptance_runtime" / revision,
        harness_root / "agent_runtime" / revision,
    ]
    if render_cache_dir is not None:
        roots.append(render_cache_dir.resolve())
        validation = decision.get("validation")
        validation = validation if isinstance(validation, dict) else {}
        details = validation.get("details")
        details = details if isinstance(details, dict) else {}
        reported = details.get("video_path")
        candidate = Path(reported).resolve() if isinstance(reported, str) else None
        if (
            candidate is not None
            and candidate.is_file()
            and candidate.suffix.lower() == ".mp4"
            and candidate.is_relative_to(render_cache_dir.resolve())
        ):
            return candidate
    for root in roots:
        if not revision or not root.is_dir():
            continue
        videos = sorted(
            root.rglob("*.mp4"),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if videos:
            return videos[0]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
