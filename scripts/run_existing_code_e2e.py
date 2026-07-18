"""Run the real quality Harness for one existing renderable Manim source file."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT, ROOT / "vendor/logic_engine_mvp_baseline"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--problem", type=Path, required=True)
    parser.add_argument("--expected-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--job-id", default="handoff-existing-code")
    parser.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("QUALITY_MODEL"))
    parser.add_argument(
        "--probe-source",
        type=Path,
        default=ROOT / "external/layout_probe/probe_runner.py",
    )
    parser.add_argument(
        "--vendor-root",
        type=Path,
        default=ROOT / ".vendor/quality_repair",
    )
    parser.add_argument("--layout-token-budget", type=int, default=60_000)
    parser.add_argument("--allow-vendor-clean-fallback", action="store_true")
    return parser.parse_args()


def _api_key() -> str:
    for name in (
        "MANIM_QUALITY_API_KEY",
        "MANIM_E2E_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise SystemExit("model API key is required; see config.env.example")


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _finish(output: Path, started: float, status: str, **values: object) -> int:
    payload = {
        "schema_version": "manim-quality.existing-code-handoff.v1",
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000),
        **values,
    }
    _write(output / "result.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if status in {"deliver", "deliver_with_warning"} else 2


def main() -> int:
    from evals.workbench_e2e.layout_stage import LayoutStageConfig, run_layout_stage
    from evals.workbench_e2e.logic_stage import LogicStageConfig, run_logic_stage
    from evals.workbench_e2e.rendering import LocalManimRenderer

    args = _arguments()
    started = time.perf_counter()
    if not args.base_url or not args.model:
        raise SystemExit("ANTHROPIC_BASE_URL and QUALITY_MODEL are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    code = args.code.resolve(strict=True)
    problem = args.problem.resolve(strict=True).read_text(encoding="utf-8")
    expected = args.expected_solution.resolve(strict=True).read_text(encoding="utf-8")
    candidate = output / "candidate_input.py"
    shutil.copyfile(code, candidate)
    key = _api_key()
    provider = {
        "ANTHROPIC_BASE_URL": args.base_url,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
    }
    renderer = LocalManimRenderer(python=str(args.manim_python.absolute()))
    baseline = renderer.render(candidate, output / "render_baseline")
    if not baseline.succeeded or baseline.video_path is None:
        return _finish(output, started, "baseline_render_failed", error=baseline.error)
    logic = run_logic_stage(
        job_id=args.job_id,
        candidate=candidate,
        problem=problem,
        expected_solution=expected,
        baseline_video=baseline.video_path,
        output_dir=output / "logic",
        config=LogicStageConfig(args.model, provider),
    )
    logic_payload = {**asdict(logic), "candidate_path": str(logic.candidate_path)}
    if logic.status not in {"review_pass", "review_record_only", "candidate_ready"}:
        return _finish(
            output,
            started,
            "logic_hold",
            logic=logic_payload,
            error=logic.error or logic.status,
        )
    current = logic.candidate_path
    current_render = baseline
    if current.resolve() != candidate.resolve():
        current_render = renderer.render(current, output / "render_after_logic")
        if not current_render.succeeded:
            return _finish(
                output,
                started,
                "logic_render_hold",
                logic=logic_payload,
                error=current_render.error,
            )
    layout = run_layout_stage(
        job_id=args.job_id,
        candidate=current,
        output_dir=output / "layout",
        config=LayoutStageConfig(
            python=str(args.manim_python.absolute()),
            probe_source_path=args.probe_source.resolve(strict=True),
            vendor_root=args.vendor_root.resolve(strict=True),
            model=args.model,
            provider_env=provider,
            token_budget=args.layout_token_budget,
            allow_vendor_clean_fallback=args.allow_vendor_clean_fallback,
        ),
    )
    layout_payload = {**asdict(layout), "candidate_path": str(layout.candidate_path)}
    final_candidate = (
        layout.candidate_path if layout.requires_render_recheck else current
    )
    final_render = current_render
    if layout.requires_render_recheck:
        final_render = renderer.render(final_candidate, output / "render_after_layout")
        if not final_render.succeeded:
            return _finish(
                output,
                started,
                "layout_render_hold",
                logic=logic_payload,
                layout=layout_payload,
                error=final_render.error,
            )
    shutil.copyfile(final_candidate, output / "candidate_final.py")
    if final_render.video_path is None:
        return _finish(output, started, "final_video_missing", error="no final video")
    shutil.copyfile(final_render.video_path, output / "video_final.mp4")
    warning = logic.status == "review_record_only" or layout.status in {
        "detection_error",
        "rejected",
        "error",
        "vendor_clean_recheck_required",
    }
    return _finish(
        output,
        started,
        "deliver_with_warning" if warning else "deliver",
        final_code=str(output / "candidate_final.py"),
        final_video=str(output / "video_final.mp4"),
        logic=logic_payload,
        layout=layout_payload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
