"""Revision materialization without mutating the source task workspace."""

from __future__ import annotations

import json
from pathlib import Path

from manim_quality.operator.models import CandidateAttempt


class RevisionWorkspace:
    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def materialize(self, revision: CandidateAttempt) -> tuple[Path, Path]:
        revision_dir = self._root / revision.revision_id
        revision_dir.mkdir(parents=True, exist_ok=True)
        candidate = revision_dir / "candidate.py"
        _write_text_if_changed(candidate, revision.code)
        identity = {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "parent_revision_id": revision.parent_revision_id,
        }
        _write_text_if_changed(
            revision_dir / "revision.json",
            json.dumps(identity, ensure_ascii=False, indent=2),
        )
        return revision_dir, candidate


def _write_text_if_changed(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")
