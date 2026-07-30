"""Load optional evidence-only findings from a prior Final Assurance run."""

from __future__ import annotations

import json
from pathlib import Path

CONTEXT_FILE = "final_assurance_issues.json"


def load_final_assurance_context(workspace: Path) -> tuple[dict[str, object], ...]:
    path = workspace / CONTEXT_FILE
    if not path.is_file():
        return ()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("issues"), list):
        raise ValueError(f"{CONTEXT_FILE} must contain an issues array")
    issues: list[dict[str, object]] = []
    for index, item in enumerate(value["issues"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"{CONTEXT_FILE} issue {index} must be an object")
        required = ("issue_id", "category", "severity", "summary", "evidence_ids")
        missing = [name for name in required if not item.get(name)]
        if missing:
            raise ValueError(
                f"{CONTEXT_FILE} issue {index} missing: {', '.join(missing)}"
            )
        issues.append(dict(item))
    return tuple(issues)
