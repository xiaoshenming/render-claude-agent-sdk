from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


FORBIDDEN_SAMPLE_PATTERNS = (
    "synthetic",
    "synthetic_logic",
    "complex_logic_v2",
    "toy",
    "simple_ai",
    "ai_generated_toy",
)

HARDCODED_RULE_PATTERNS = (
    re.compile(r"\bif\s+sample_id\s*==", re.IGNORECASE),
    re.compile(r"\bif\s+case_id\s*==", re.IGNORECASE),
    re.compile(r"\bif\s+job_id\s*==", re.IGNORECASE),
    re.compile(r"\bG1[89]-\d{2}-", re.IGNORECASE),
    re.compile(r"\bREALCONTRACT-\d{3}-", re.IGNORECASE),
    re.compile(r"\bNEW-\d{3}-", re.IGNORECASE),
)


def validate_sample_pack_manifest(manifest_csv: Path) -> dict:
    manifest_csv = Path(manifest_csv)
    rows = list(csv.DictReader(manifest_csv.read_text(encoding="utf-8-sig").splitlines()))
    forbidden = [row for row in rows if _row_is_forbidden(row)]
    return {
        "ok": not forbidden,
        "sample_count": len(rows),
        "forbidden_count": len(forbidden),
        "forbidden_samples": forbidden,
        "forbidden_patterns": list(FORBIDDEN_SAMPLE_PATTERNS),
    }


def find_hardcoded_sample_rules(paths: Iterable[Path]) -> list[dict]:
    findings: list[dict] = []
    for path in paths:
        path = Path(path)
        if not path.exists() or not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if any(pattern.search(line) for pattern in HARDCODED_RULE_PATTERNS):
                findings.append({"path": str(path), "line": line_no, "text": line.strip()})
    return findings


def scan_tree_for_hardcoding(root: Path, *, suffixes: tuple[str, ...] = (".py", ".md")) -> dict:
    root = Path(root)
    paths = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]
    findings = find_hardcoded_sample_rules(paths)
    return {
        "ok": not findings,
        "file_count": len(paths),
        "finding_count": len(findings),
        "findings": findings,
    }


def _row_is_forbidden(row: dict[str, str]) -> bool:
    joined = " ".join(str(value or "").lower() for value in row.values())
    return any(pattern in joined for pattern in FORBIDDEN_SAMPLE_PATTERNS)
