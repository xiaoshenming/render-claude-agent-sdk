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
    final_answer: str = "",
    parsed_standard_answer: str = "",
    teaching_script: str = "",
    reviewer_supplemental_notes: dict[str, str] | None = None,
    layout_evidence: dict[str, object] | None = None,
    model: str,
    effort: str = "low",
):
    return run_native_reviewer_group(
        runtime,
        candidate_path=candidate_path,
        problem_text=problem_text,
        solution_steps=solution_steps,
        final_answer=final_answer,
        parsed_standard_answer=parsed_standard_answer,
        teaching_script=teaching_script,
        reviewer_supplemental_notes=reviewer_supplemental_notes,
        layout_evidence=layout_evidence,
        model=model,
        effort=effort,
    )
