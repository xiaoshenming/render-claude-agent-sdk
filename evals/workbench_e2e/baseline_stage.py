from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .rendering import RenderResult


@dataclass(frozen=True, slots=True)
class BaselineAttempt:
    primary: object
    recovery: object | None
    candidate: Path
    render: RenderResult
    recovery_error: str | None = None
    recovery_failure: object | None = None


def run_baseline_attempt(
    *, job_dir: Path, prompt: str, generated, generation, renderer
) -> BaselineAttempt:
    candidate = job_dir / "candidate_generated.py"
    candidate.write_text(generated.code, encoding="utf-8")
    baseline = renderer.render(candidate, job_dir / "render_baseline")
    if baseline.succeeded:
        return BaselineAttempt(generated, None, candidate, baseline)
    try:
        recovered = generation.generate(
            prompt=render_recovery_prompt(prompt, baseline.error),
            output_dir=job_dir / "generation_render_recovery",
        )
    except Exception as error:
        return BaselineAttempt(
            generated,
            None,
            candidate,
            baseline,
            f"{type(error).__name__}:{error}",
            error,
        )
    candidate = job_dir / "candidate_render_recovery.py"
    candidate.write_text(recovered.code, encoding="utf-8")
    rerendered = renderer.render(candidate, job_dir / "render_baseline_recovery")
    return BaselineAttempt(generated, recovered, candidate, rerendered)


def generation_metrics(result) -> dict:
    return {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.input_tokens + result.output_tokens,
        "elapsed_ms": result.elapsed_ms,
        "model": result.model,
        "attempts": result.attempts,
    }


def combined_generation_metrics(primary, recovery) -> dict:
    first = generation_metrics(primary)
    if recovery is None:
        return first
    second = generation_metrics(recovery)
    return {
        **second,
        "input_tokens": first["input_tokens"] + second["input_tokens"],
        "output_tokens": first["output_tokens"] + second["output_tokens"],
        "total_tokens": first["total_tokens"] + second["total_tokens"],
        "elapsed_ms": first["elapsed_ms"] + second["elapsed_ms"],
        "attempts": first["attempts"] + second["attempts"],
        "render_recovery_used": True,
    }


def render_recovery_prompt(original_prompt: str, render_error: str | None) -> str:
    error = (render_error or "unknown render failure")[-2_000:]
    return (
        f"{original_prompt}\n\n"
        "【上一次生成代码未能渲染】请从头重新生成完整代码，不要解释，也不要局部补丁。"
        "保持题目、答案和教学顺序不变，避免复现以下通用渲染错误：\n"
        f"{error}"
    )
