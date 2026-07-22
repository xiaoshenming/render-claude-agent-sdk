from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .baseline_stage import (
    combined_generation_metrics,
    generation_metrics,
    run_baseline_attempt,
)
from .generation import GenerationClient, GenerationFailed
from .layout_stage import LayoutStageConfig, run_layout_stage
from .logic_stage import LogicStageConfig, run_logic_stage
from .models import WorkloadSlot
from .prompt_source import PromptSource
from .rendering import LocalManimRenderer, RenderResult


@dataclass(frozen=True, slots=True)
class JobConfig:
    output_root: Path
    prompt_source: PromptSource
    generation: GenerationClient
    renderer: LocalManimRenderer
    logic: LogicStageConfig
    layout: LayoutStageConfig


def run_job(slot: WorkloadSlot, config: JobConfig) -> dict:
    job_dir = config.output_root / f"round-{slot.round_id}" / slot.slot_id
    summary_path = job_dir / "job_summary.json"
    existing = _existing_summary(summary_path)
    if existing is not None:
        return existing
    started = time.perf_counter()
    try:
        return _run_new_job(slot, config, job_dir, started)
    except Exception as error:
        return _terminal(
            job_dir,
            slot,
            started,
            "unhandled_job_error",
            error=f"{type(error).__name__}:{error}",
        )


def _run_new_job(
    slot: WorkloadSlot, config: JobConfig, job_dir: Path, started: float
) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    task = slot.task
    _write_json(job_dir / "task.json", asdict(task) | {"slot_id": slot.slot_id})
    prompt = config.prompt_source.render(
        task.prompt_id,
        problem=task.problem,
        solution=task.expected_solution,
    )
    (job_dir / "prompt.txt").write_text(prompt.text, encoding="utf-8")
    _write_json(
        job_dir / "prompt_meta.json",
        {"prompt_id": prompt.prompt_id, "name": prompt.name, "version": prompt.version},
    )
    try:
        generated = config.generation.generate(
            prompt=prompt.text, output_dir=job_dir / "generation"
        )
    except Exception as error:
        extra = (
            {"generation": generation_metrics(error)}
            if isinstance(error, GenerationFailed)
            else {}
        )
        return _terminal(
            job_dir, slot, started, "generation_failed", error=str(error), **extra
        )
    attempt = run_baseline_attempt(
        job_dir=job_dir,
        prompt=prompt.text,
        generated=generated,
        generation=config.generation,
        renderer=config.renderer,
    )
    recovered = attempt.recovery
    candidate = attempt.candidate
    baseline = attempt.render
    if attempt.recovery_error:
        return _terminal(
            job_dir,
            slot,
            started,
            "render_recovery_generation_failed",
            generation=combined_generation_metrics(generated, attempt.recovery_failure),
            baseline_render=_render_metrics(baseline),
            error=attempt.recovery_error,
        )
    if not baseline.succeeded or baseline.video_path is None:
        return _terminal(
            job_dir,
            slot,
            started,
            "baseline_render_failed",
            generation=combined_generation_metrics(generated, recovered),
            baseline_render=_render_metrics(baseline),
            error=baseline.error,
        )
    logic = run_logic_stage(
        job_id=slot.slot_id,
        candidate=candidate,
        problem=task.problem,
        expected_solution=task.expected_solution,
        baseline_video=baseline.video_path,
        output_dir=job_dir / "logic",
        config=config.logic,
    )
    logic_accepted = logic.status in {
        "review_pass", "review_record_only", "candidate_ready",
    }
    logic_warning = not logic_accepted or logic.status == "review_record_only"
    current = logic.candidate_path if logic_accepted else candidate
    current_render = baseline
    if current.resolve() != candidate.resolve():
        repaired_render = config.renderer.render(current, job_dir / "render_after_logic")
        if repaired_render.succeeded:
            current_render = repaired_render
        else:
            logic_warning = True
            current = candidate
    layout = run_layout_stage(
        job_id=slot.slot_id,
        candidate=current,
        output_dir=job_dir / "layout",
        config=config.layout,
    )
    final_render = current_render
    if layout.requires_render_recheck:
        repaired_render = config.renderer.render(
            layout.candidate_path, job_dir / "render_after_layout"
        )
        if repaired_render.succeeded:
            final_render = repaired_render
    final_candidate = (
        layout.candidate_path
        if layout.requires_render_recheck and final_render is not current_render
        else current
    )
    _copy(final_candidate, job_dir / "candidate_final.py")
    if final_render.video_path:
        _copy(final_render.video_path, job_dir / "video_final.mp4")
    layout_warning = layout.status in {
        "detection_error",
        "rejected",
        "error",
        "vendor_clean_recheck_required",
    }
    warning = layout_warning or logic_warning
    warning_text = ";".join(
        item
        for item in (
            logic.error if logic_warning else None,
            layout.error if layout_warning else None,
        )
        if item
    )
    return _terminal(
        job_dir,
        slot,
        started,
        "deliver_with_warning" if warning else "deliver",
        generation=combined_generation_metrics(generated, recovered),
        baseline_render=_render_metrics(baseline),
        logic=_path_safe(asdict(logic)),
        layout=_path_safe(asdict(layout)),
        final_render=_render_metrics(final_render),
        warning=warning_text or None,
    )


def _terminal(job_dir: Path, slot: WorkloadSlot, started: float, status: str, **extra):
    payload = {
        "schema_version": "manim-quality.workbench-job.v1",
        "slot_id": slot.slot_id,
        "round_id": slot.round_id,
        "task_id": slot.task.task_id,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000),
        **extra,
    }
    _write_json(job_dir / "job_summary.json", payload)
    return payload


def _render_metrics(result: RenderResult) -> dict:
    return {
        "succeeded": result.succeeded,
        "scene_name": result.scene_name,
        "video_path": str(result.video_path) if result.video_path else None,
        "elapsed_ms": result.elapsed_ms,
        "returncode": result.returncode,
        "error": result.error,
    }


def _path_safe(value: dict) -> dict:
    return {
        key: str(item) if isinstance(item, Path) else item
        for key, item in value.items()
    }


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _existing_summary(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
