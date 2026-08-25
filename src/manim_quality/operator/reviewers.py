"""One parent SDK session with foreground native Reviewer subagents."""

from __future__ import annotations

from pathlib import Path

from .native_reviewer_group import (
    _content_language as content_language,
)
from .native_reviewer_group import (
    _standard_prompt,
    run_native_reviewer_group,
)


def _prompt(name, candidate, problem, steps=""):
    return _standard_prompt(name, candidate, problem, steps)


def _content_language(candidate):
    return content_language(candidate)


def run_reviewers(
    runtime,
    *,
    candidate_path: Path,
    problem_text: str,
    solution_steps: str = "",
    model: str,
    effort: str = "low",
):
    return run_native_reviewer_group(
        runtime,
        candidate_path=candidate_path,
        problem_text=problem_text,
        solution_steps=solution_steps,
        model=model,
        effort=effort,
    )
