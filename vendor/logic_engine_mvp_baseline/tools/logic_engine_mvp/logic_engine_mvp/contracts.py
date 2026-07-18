from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "logic_engine_mvp.v1"


@dataclass(frozen=True)
class PreparedSample:
    sample_id: str
    sample_dir: Path
    workdir: Path
    contract_path: Path
    source_region_path: Path


def prepare_sample(sample_dir: Path, out_root: Path) -> PreparedSample:
    sample_dir = Path(sample_dir)
    out_root = Path(out_root)
    issue = _read_issue(sample_dir / "issue.json")
    sample_id = str(issue.get("sample_id") or sample_dir.name)
    workdir = out_root / sample_id
    workdir.mkdir(parents=True, exist_ok=True)

    candidate_path = sample_dir / "candidate.py"
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate.py not found: {candidate_path}")

    candidate_text = candidate_path.read_text(encoding="utf-8")
    shutil.copy2(candidate_path, workdir / "candidate.py")
    _copy_optional(sample_dir / "question.txt", workdir / "question.txt")
    _copy_optional(sample_dir / "problem.md", workdir / "problem.md")

    contract = _build_contract(sample_id, issue, candidate_text)
    contract_path = workdir / "logic_contract_context.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    source_region_path = workdir / "source_region.md"
    source_region_path.write_text(_build_source_region(contract, candidate_text), encoding="utf-8")

    return PreparedSample(
        sample_id=sample_id,
        sample_dir=sample_dir,
        workdir=workdir,
        contract_path=contract_path,
        source_region_path=source_region_path,
    )


def _read_issue(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"issue.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"issue.json must be an object: {path}")
    return data


def _build_contract(sample_id: str, issue: dict[str, Any], candidate_text: str) -> dict[str, Any]:
    wrong_text = _first_text(issue, "wrong_text", "wrong", "actual", "shown")
    expected_text = _first_text(issue, "expected_text", "expected", "correct", "target")
    issue_type = str(issue.get("issue_type") or "logic_issue")
    source_lines = _find_source_lines(candidate_text, wrong_text or str(issue.get("source_hint") or ""))

    validators: list[dict[str, Any]] = []
    if wrong_text:
        validators.append({"kind": "must_not_contain", "text": wrong_text})
    if expected_text:
        validators.append({"kind": "must_contain", "text": expected_text})

    return {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "profile": "logic",
        "contracts": [
            {
                "id": f"{sample_id}-logic-001",
                "kind": "text_replacement",
                "issue_type": issue_type,
                "severity": issue.get("severity") or "blocking",
                "wrong_text": wrong_text,
                "expected_text": expected_text,
                "explanation": issue.get("explanation") or issue.get("statement") or "",
                "source_lines": source_lines,
                "validators": validators,
            }
        ],
        "review_input": {
            "source": "manual_issue_json",
            "needs_llm_reviewer": False,
            "needs_python_verifier": bool(issue.get("needs_python_verifier", False)),
        },
    }


def _first_text(issue: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = issue.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return ""


def _find_source_lines(candidate_text: str, needle: str) -> list[int]:
    if not needle:
        return []
    return [
        line_no
        for line_no, line in enumerate(candidate_text.splitlines(), start=1)
        if needle in line
    ]


def _build_source_region(contract: dict[str, Any], candidate_text: str) -> str:
    lines = candidate_text.splitlines()
    parts = [
        f"# Source Region: {contract['sample_id']}",
        "",
        "Only edit candidate.py lines related to these contracts.",
        "",
    ]
    for item in contract["contracts"]:
        parts.extend(
            [
                f"## {item['id']}",
                f"- issue_type: {item['issue_type']}",
                f"- wrong_text: {item['wrong_text']}",
                f"- expected_text: {item['expected_text']}",
                f"- explanation: {item['explanation']}",
                "",
                "```python",
            ]
        )
        for line_no in item.get("source_lines") or []:
            if 1 <= line_no <= len(lines):
                parts.append(f"{line_no}: {lines[line_no - 1]}")
        if not item.get("source_lines"):
            parts.append("# No direct source line found. The repairer must inspect a small local region only.")
        parts.extend(["```", ""])
    return "\n".join(parts)


def _copy_optional(src: Path, dest: Path) -> None:
    if src.exists():
        shutil.copy2(src, dest)
