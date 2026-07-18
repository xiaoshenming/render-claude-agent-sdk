from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .contract_builders.structured_expanders import expand_structured_issue
from .contract_builders.text_resolution import normalize_expected_text, resolve_contract_texts
from .contract_builders.text_tools import nonempty_stripped_lines, trim_agent_text


MAX_AGENT_EVIDENCE_CHARS = 480


def build_repair_contract(candidate_path: Path, verified_issues: dict[str, Any], *, include_soft: bool = False) -> dict[str, Any]:
    candidate_path = Path(candidate_path)
    code_text = candidate_path.read_text(encoding="utf-8", errors="replace")
    contracts = []
    skipped_contracts = []
    for index, issue in enumerate(verified_issues.get("issues") or [], start=1):
        if not isinstance(issue, dict) or not _is_included_issue(issue, include_soft=include_soft):
            continue
        for contract in _contracts_for_issue(index, issue, code_text):
            skip_reason = _contract_skip_reason(contract)
            if skip_reason is None:
                contracts.append(contract)
                continue
            skipped_contracts.append(
                {
                    "id": contract["id"],
                    "issue_type": contract["issue_type"],
                    "validation_level": contract.get("validation_level", "deterministic"),
                    "reason": skip_reason,
                }
            )
    contracts = _merge_duplicate_contracts(contracts)
    soft_contract_count = sum(1 for contract in contracts if contract.get("validation_level") == "soft_llm")
    supported_contract_count = len(contracts) - soft_contract_count
    return {
        "schema_version": "logic_engine_mvp.repair_contract.v1",
        "sample_id": str(verified_issues.get("sample_id") or candidate_path.parent.name),
        "profile": "logic",
        "supported_contract_count": supported_contract_count,
        "soft_contract_count": soft_contract_count,
        "repairable_contract_count": len(contracts),
        "skipped_contract_count": len(skipped_contracts),
        "skipped_contracts": skipped_contracts,
        "contracts": contracts,
        "policy": {
            "edit_file": "candidate.py",
            "allowed_tools": ["Read", "Edit"],
            "disallowed_tools": ["Bash", "Write"],
            "no_overlap_repair": True,
            "no_sample_specific_rules": True,
            "soft_llm_contracts_allowed": include_soft,
        },
    }


def _is_included_issue(issue: dict[str, Any], *, include_soft: bool) -> bool:
    status = issue.get("verification_status")
    if status == "supported":
        return True
    return include_soft and status == "soft_supported"


def _merge_duplicate_contracts(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for contract in contracts:
        key = (
            str(contract.get("validation_level") or ""),
            str(contract.get("issue_type") or ""),
            str(contract.get("wrong_text") or ""),
            str(contract.get("expected_text") or ""),
        )
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = contract
            merged.append(contract)
            continue
        existing_lines = list(existing.get("source_lines") or [])
        for line_no in contract.get("source_lines") or []:
            if line_no not in existing_lines:
                existing_lines.append(line_no)
        existing["source_lines"] = sorted(existing_lines)
        existing["replace_scope"] = _replace_scope(existing["source_lines"])
    return merged


def _contract_skip_reason(contract: dict[str, Any]) -> str | None:
    if not contract["source_lines"]:
        return "wrong_text_not_found_in_candidate"
    if not _is_parseable_code_line(str(contract.get("expected_text") or "")):
        return "expected_text_not_parseable_code"
    return None


def _is_parseable_code_line(text: str) -> bool:
    text = text.strip()
    try:
        ast.parse(text)
    except SyntaxError:
        try:
            ast.parse(f"_contract_probe({text})")
        except SyntaxError:
            return False
    return True


def _contracts_for_issue(index: int, issue: dict[str, Any], code_text: str) -> list[dict[str, Any]]:
    line_replacement_contracts = _contracts_for_line_replacements(index, issue, code_text)
    if line_replacement_contracts:
        return line_replacement_contracts
    expanded = expand_structured_issue(index, issue, code_text)
    if expanded:
        return [
            _contract_from_resolved(issue, contract_id, wrong_text, expected_text, source_lines)
            for contract_id, wrong_text, expected_text, source_lines in expanded
        ]
    return [_contract_for_issue(index, issue, code_text)]


def _contracts_for_line_replacements(index: int, issue: dict[str, Any], code_text: str) -> list[dict[str, Any]]:
    replacements = issue.get("line_replacements")
    if not isinstance(replacements, list):
        return []
    base_id = str(issue.get("issue_id") or f"issue-{index:03d}")
    contracts = []
    for replacement_index, replacement in enumerate(replacements, start=1):
        if not isinstance(replacement, dict):
            continue
        source_line = _int(replacement.get("source_line"))
        wrong_text = str(replacement.get("exact_code_before") or "").strip()
        expected_text = str(replacement.get("exact_code_after") or "").strip()
        if source_line <= 0 or not wrong_text or not expected_text:
            continue
        contracts.append(
            {
                "id": f"{base_id}-line-{replacement_index}",
                "kind": "text_replacement",
                "issue_type": str(issue.get("issue_type") or "logic_issue"),
                **_validation_metadata(issue),
                "wrong_text": wrong_text,
                "expected_text": expected_text,
                "evidence": trim_agent_text(str(issue.get("evidence") or ""), MAX_AGENT_EVIDENCE_CHARS),
                "source_lines": [source_line],
                "replace_scope": "single_code_line",
                "validators": [
                    {"kind": "must_not_contain_code_line_at", "line": source_line, "text": wrong_text},
                    {"kind": "must_contain_code_line_at", "line": source_line, "text": expected_text},
                    *_protected_duplicate_validators(code_text, wrong_text, allowed_line=source_line),
                ],
            }
        )
    return contracts


def _protected_duplicate_validators(code_text: str, wrong_text: str, *, allowed_line: int) -> list[dict[str, Any]]:
    validators = []
    for line_no, line in enumerate(code_text.splitlines(), start=1):
        if line_no == allowed_line:
            continue
        if line.strip() == wrong_text:
            validators.append({"kind": "must_contain_code_line_at", "line": line_no, "text": wrong_text})
    return validators


def _contract_for_issue(index: int, issue: dict[str, Any], code_text: str) -> dict[str, Any]:
    contract_id = str(issue.get("issue_id") or f"issue-{index:03d}")
    wrong_text, expected_text, source_lines = _resolve_issue_replacement_texts(issue, code_text)
    return _contract_from_resolved(issue, contract_id, wrong_text, expected_text, source_lines)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_issue_replacement_texts(issue: dict[str, Any], code_text: str) -> tuple[str, str, list[int]]:
    pairs = _issue_replacement_pairs(issue)
    fallback: tuple[str, str, list[int]] = ("", "", [])
    for wrong_text, expected_text in pairs:
        resolved_wrong, resolved_expected, source_lines = resolve_contract_texts(code_text, wrong_text, expected_text)
        resolved_expected = normalize_expected_text(resolved_wrong, resolved_expected, code_text=code_text)
        resolved = (resolved_wrong, resolved_expected, source_lines)
        if not fallback[0] and resolved_wrong:
            fallback = resolved
        if source_lines:
            return resolved
    return fallback


def _issue_replacement_pairs(issue: dict[str, Any]) -> list[tuple[str, str]]:
    exact_before = str(issue.get("exact_code_before") or "").strip()
    exact_after = str(issue.get("exact_code_after") or "").strip()
    wrong_text = str(issue.get("wrong_text") or issue.get("wrong_claim") or "").strip()
    expected_text = str(issue.get("expected") or issue.get("expected_text") or "").strip()
    pairs: list[tuple[str, str]] = []
    if exact_before:
        pairs.append((exact_before, exact_after or expected_text))
    if wrong_text:
        pairs.append((wrong_text, expected_text or exact_after))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        if not pair[0] or not pair[1] or pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _contract_from_resolved(
    issue: dict[str, Any],
    contract_id: str,
    wrong_text: str,
    expected_text: str,
    source_lines: list[int],
) -> dict[str, Any]:
    return {
        "id": contract_id,
        "kind": "text_replacement",
        "issue_type": str(issue.get("issue_type") or "logic_issue"),
        **_validation_metadata(issue),
        "wrong_text": wrong_text,
        "expected_text": expected_text,
        "evidence": trim_agent_text(str(issue.get("evidence") or ""), MAX_AGENT_EVIDENCE_CHARS),
        "source_lines": source_lines,
        "replace_scope": _replace_scope(source_lines),
        "validators": _replacement_validators(wrong_text, expected_text),
    }


def _validation_metadata(issue: dict[str, Any]) -> dict[str, str]:
    if issue.get("verification_status") == "soft_supported" or issue.get("validation_level") == "soft_llm":
        return {
            "validation_level": "soft_llm",
            "contract_source": "llm_soft_contract",
            "soft_verification_reason": str(issue.get("soft_verification_reason") or ""),
        }
    if issue.get("source") == "deterministic_logic_facts":
        return {
            "validation_level": "deterministic",
            "contract_source": "deterministic_logic_facts",
        }
    return {
        "validation_level": "deterministic",
        "contract_source": "verified_contract",
    }


def _replacement_validators(wrong_text: str, expected_text: str) -> list[dict[str, str]]:
    validators = []
    for line in nonempty_stripped_lines(wrong_text):
        validators.append({"kind": "must_not_contain_code_line", "text": line})
    for line in nonempty_stripped_lines(expected_text):
        validators.append({"kind": "must_contain_code_line", "text": line})
    return validators


def _replace_scope(source_lines: list[int]) -> str:
    if len(source_lines) > 1:
        return "all_matching_code_lines"
    return "single_code_line"
