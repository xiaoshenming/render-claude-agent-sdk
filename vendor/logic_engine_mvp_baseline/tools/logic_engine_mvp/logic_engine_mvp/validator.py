from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .logic_facts import deterministic_review_issues, extract_deterministic_logic_facts


def validate_contract(code_path: Path, contract_path: Path) -> dict[str, Any]:
    code_text = Path(code_path).read_text(encoding="utf-8")
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    failures: list[dict[str, Any]] = []
    contract_items = [item for item in contract.get("contracts") or [] if isinstance(item, dict)]
    syntax_failure = _python_syntax_failure(code_text)
    if syntax_failure is not None:
        failures.append(syntax_failure)

    for item in contract_items:
        validators = item.get("validators")
        if not isinstance(validators, list) or not validators:
            failures.append(
                {
                    "contract_id": item.get("id"),
                    "kind": "missing_validators",
                    "message": "contract has no validators",
                }
            )
            continue
        for rule in validators:
            if not isinstance(rule, dict):
                failures.append(
                    {
                        "contract_id": item.get("id"),
                        "kind": "invalid_validator",
                        "message": "validator must be an object",
                    }
                )
                continue
            failure = _check_rule(item, rule, code_text)
            if failure is not None:
                failures.append(failure)
    failures.extend(_semantic_deterministic_failures(contract_items, code_text))

    return {
        "ok": True,
        "passed": not failures,
        "blocking_count": len(failures),
        "failures": failures,
        "contract_path": str(contract_path),
        "code_path": str(code_path),
    }


def _check_rule(item: dict[str, Any], rule: dict[str, Any], code_text: str) -> dict[str, Any] | None:
    kind = rule.get("kind")
    text = str(rule.get("text") or "")
    if not text:
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": "validator text is empty",
            "text": text,
        }

    if kind == "must_not_contain" and text in code_text:
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"forbidden text still exists: {text}",
            "text": text,
        }
    if kind == "must_contain" and text not in code_text:
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"required text is missing: {text}",
            "text": text,
        }
    if kind == "must_not_contain_code_line" and _has_code_line(code_text, text):
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"forbidden code line still exists: {text}",
            "text": text,
        }
    if kind == "must_contain_code_line" and not _has_code_line(code_text, text):
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"required code line is missing: {text}",
            "text": text,
        }
    if kind == "must_not_contain_code_line_at" and _has_code_line_at(code_text, _int(rule.get("line")), text):
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"forbidden code line still exists at line {rule.get('line')}: {text}",
            "text": text,
        }
    if kind == "must_contain_code_line_at" and not _has_code_line_at(code_text, _int(rule.get("line")), text):
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"required code line is missing at line {rule.get('line')}: {text}",
            "text": text,
        }
    known_kinds = {
        "must_not_contain",
        "must_contain",
        "must_not_contain_code_line",
        "must_contain_code_line",
        "must_not_contain_code_line_at",
        "must_contain_code_line_at",
    }
    if kind not in known_kinds:
        return {
            "contract_id": item.get("id"),
            "kind": kind,
            "message": f"unknown validator kind: {kind}",
            "text": text,
        }
    return None


def _semantic_deterministic_failures(items: list[dict[str, Any]], code_text: str) -> list[dict[str, Any]]:
    deterministic_issue_types = {
        str(item.get("issue_type") or "")
        for item in items
        if item.get("contract_source") == "deterministic_logic_facts"
        and item.get("validation_level", "deterministic") != "soft_llm"
    }
    deterministic_issue_types.discard("")
    if not deterministic_issue_types:
        return []

    facts = extract_deterministic_logic_facts(code_text)
    if facts.get("parse_error"):
        return [
            {
                "contract_id": "semantic_deterministic",
                "kind": "semantic_deterministic_parse_error",
                "message": str(facts.get("parse_error")),
            }
        ]
    issues = deterministic_review_issues({"deterministic_logic_facts": facts})
    failures = []
    for issue in issues:
        issue_type = str(issue.get("issue_type") or "")
        if issue_type not in deterministic_issue_types:
            continue
        failures.append(
            {
                "contract_id": "semantic_deterministic",
                "kind": "semantic_deterministic_issue_still_present",
                "issue_type": issue_type,
                "message": str(issue.get("evidence") or "deterministic issue still present after repair"),
            }
        )
    return failures


def _python_syntax_failure(code_text: str) -> dict[str, Any] | None:
    try:
        ast.parse(code_text)
    except SyntaxError as exc:
        return {
            "contract_id": "python_syntax",
            "kind": "python_syntax_error",
            "message": f"{exc.msg} at line {exc.lineno}",
            "line": exc.lineno,
            "offset": exc.offset,
        }
    return None


def _has_code_line(code_text: str, expected: str) -> bool:
    expected = expected.strip()
    return any(line.strip() == expected for line in code_text.splitlines() if _is_code_line(line))


def _is_code_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _has_code_line_at(code_text: str, line_no: int, expected: str) -> bool:
    if line_no <= 0:
        return False
    lines = code_text.splitlines()
    if line_no > len(lines):
        return False
    line = lines[line_no - 1]
    return _is_code_line(line) and line.strip() == expected.strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
