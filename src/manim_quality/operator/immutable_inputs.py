"""Immutable problem, solution-step, and repair-feedback input identity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.revisions.fingerprint import sha256_text


@dataclass(frozen=True, slots=True)
class ImmutableReviewInputs:
    problem_text: str
    parsed_standard_answer: str
    solution_steps: str
    reviewer_supplemental_notes: Mapping[str, object]
    repair_feedback: Mapping[str, object]
    problem_hash: str
    parsed_standard_answer_hash: str
    solution_steps_hash: str
    reviewer_supplemental_notes_hash: str
    repair_feedback_hash: str

    @classmethod
    def build(
        cls,
        problem_text: str,
        solution_steps: str,
        parsed_standard_answer: str,
        reviewer_supplemental_notes: Mapping[str, object] | None,
        repair_feedback: Mapping[str, object] | None,
    ) -> ImmutableReviewInputs:
        steps = solution_steps.strip()
        answer = parsed_standard_answer.strip()
        notes = dict(reviewer_supplemental_notes or {})
        feedback = dict(repair_feedback or {})
        feedback_payload = json.dumps(
            feedback,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        notes_payload = json.dumps(
            notes, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return cls(
            problem_text=problem_text,
            parsed_standard_answer=answer,
            solution_steps=steps,
            reviewer_supplemental_notes=notes,
            repair_feedback=feedback,
            problem_hash=sha256_text(problem_text),
            parsed_standard_answer_hash=sha256_text(answer),
            solution_steps_hash=sha256_text(steps),
            reviewer_supplemental_notes_hash=sha256_text(notes_payload),
            repair_feedback_hash=sha256_text(feedback_payload),
        )
