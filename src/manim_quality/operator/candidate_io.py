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
        source = candidate_path.read_text(encoding="utf-8")
        solution = extract_solution(source)
        total = max(1, len(source.splitlines()))
        offset = _read_count(value, "offset", solution.start_line)
        limit = _read_count(value, "limit", solution.end_line - solution.start_line + 1)
        offset = min(offset, total)
        limit = min(limit, total - offset + 1)
        if (on_read is not None and offset <= solution.end_line
                and offset + limit > solution.start_line):
            on_read()
        return {
            **value,
            "file_path": str(candidate_path),
            "offset": offset,
            "limit": limit,
        }

    return normalize


def _read_count(value: Mapping[str, object], key: str, default: int) -> int:
    count = value.get(key, default)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"Read {key} must be a positive integer")
    return count
