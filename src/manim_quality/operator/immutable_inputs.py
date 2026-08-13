"""Immutable problem, solution-step, and repair-feedback input identity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.revisions.fingerprint import sha256_text


@dataclass(frozen=True, slots=True)
class ImmutableReviewInputs:
    problem_text: str
    solution_steps: str
    repair_feedback: Mapping[str, object]
    problem_hash: str
    solution_steps_hash: str
    repair_feedback_hash: str

    @classmethod
    def build(
        cls,
        problem_text: str,
        solution_steps: str,
        repair_feedback: Mapping[str, object] | None,
    ) -> ImmutableReviewInputs:
        steps = solution_steps.strip()
        feedback = dict(repair_feedback or {})
        feedback_payload = json.dumps(
            feedback,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            problem_text=problem_text,
            solution_steps=steps,
            repair_feedback=feedback,
            problem_hash=sha256_text(problem_text),
            solution_steps_hash=sha256_text(steps),
            repair_feedback_hash=sha256_text(feedback_payload),
        )
