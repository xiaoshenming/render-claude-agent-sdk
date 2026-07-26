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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="")
    # Accepted for contract compatibility; recorded but not interpreted.
    parser.add_argument("--expected-solution", type=Path)
    parser.add_argument("--logic-mode", default="one_shot")
    parser.add_argument("--layout-token-budget", type=int, default=180_000)
    parser.add_argument("--allow-vendor-clean-fallback", action="store_true")
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
    argv = [
        "--candidate",
        str(args.code.resolve()),
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
    assets = workspace / "assets"
    if assets.is_dir():
        argv.extend(("--assets-dir", str(assets)))
    try:
        return operator_main(argv)
    except SystemExit as error:
        return int(error.code or 0)
    except Exception as error:
        print(f"quality harness crashed: {error}", file=sys.stderr)
        return 4


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
    video = _final_video(harness_root, decision)
    if not candidate.is_file() or video is None:
        print("PROPOSED artifacts missing; failing open", file=sys.stderr)
        return 3
    final_code = output / "candidate_final.py"
    shutil.copyfile(candidate, final_code)
    shutil.copyfile(video, output / "video_final.mp4")
    _write_result(
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
    _write_result(
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


def _write_result(
    output: Path,
    *,
    status: str,
    decision: dict[str, object],
    logic: dict[str, object],
    layout: dict[str, object],
) -> None:
    payload = {
        "schema_version": "batchops.quality-agent.result.v1",
        "status": status,
        "logic": logic,
        "layout": layout,
        "harness_decision": decision.get("decision"),
        "turns": decision.get("turns"),
        "tokens": decision.get("tokens"),
        "external_tool_ms": decision.get("external_tool_ms"),
        "harness_artifacts": "harness/",
    }
    (output / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _final_video(
    harness_root: Path, decision: dict[str, object]
) -> Path | None:
    revision = str(
        decision.get("final_revision_id")
        or decision.get("submitted_revision_id")
        or ""
    )
    roots = (
        harness_root / "acceptance_runtime" / revision,
        harness_root / "agent_runtime" / revision,
    )
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
