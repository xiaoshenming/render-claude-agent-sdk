"""Exact candidate discovery and live native-Read range normalization."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from tempfile import mkdtemp

from .source_view import extract_solution


def find_baseline_candidate(workspace: Path, baseline_code: str) -> Path:
    root = Path(workspace).resolve(strict=True)
    matches = []
    for path in root.glob("*.py"):
        try:
            if path.read_text(encoding="utf-8") == baseline_code:
                matches.append(path.resolve(strict=True))
        except (OSError, UnicodeError):
            continue
    if len(matches) > 1 or (not matches and any(root.glob("*.py"))):
        raise ValueError("workspace must contain exactly one baseline candidate.py")
    session = Path(mkdtemp(prefix=".quality-agent-session-", dir=root))
    candidate = session / "candidate.py"
    candidate.write_text(baseline_code, encoding="utf-8")
    return candidate.resolve(strict=True)


def live_solution_read(candidate_path: Path, *, on_read=None):
    def normalize(value: Mapping[str, object]) -> Mapping[str, object]:
        solution = extract_solution(candidate_path.read_text(encoding="utf-8"))
        if on_read is not None:
            on_read()
        return {
            **value,
            "offset": solution.start_line,
            "limit": solution.end_line - solution.start_line + 1,
        }

    return normalize
