"""Replayable snapshots for the four-Reviewer authority contract."""

from __future__ import annotations

import json
from pathlib import Path

from manim_quality.revisions.fingerprint import sha256_text

from .session import QualitySession

CONTRACT_VERSION = "review-authority-v1"


def write_review_input_artifacts(root: Path, session: QualitySession) -> None:
    """Persist each authority domain separately and bind it by hash."""
    notes = session.reviewer_supplemental_notes
    notes_payload = json.dumps(
        notes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    values = {
        "problem.snapshot": session.problem_text,
        "parsed-standard-answer.snapshot": session.parsed_standard_answer,
        "teaching-script.snapshot": session.solution_steps,
        "candidate.R0.py": session.baseline.code,
    }
    for name, value in values.items():
        _write_text(root / "input" / name, value)
    _write_json(root / "input" / "reviewer-supplemental-notes.json", notes)
    _write_json(
        root / "input" / "review-authority-manifest.json",
        {
            "contract_version": CONTRACT_VERSION,
            "problem_sha256": sha256_text(session.problem_text),
            "parsed_standard_answer_sha256": sha256_text(
                session.parsed_standard_answer
            ),
            "teaching_script_sha256": sha256_text(session.solution_steps),
            "supplemental_notes_sha256": sha256_text(notes_payload),
            "candidate_sha256": session.baseline.code_hash,
        },
    )


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
