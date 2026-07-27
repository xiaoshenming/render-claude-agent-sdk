"""Deep binders and compact JSON schemas for Quality Operator tools."""

from __future__ import annotations

from collections.abc import Mapping

from .models import Finding, FindingCategory, PatchScope


def schema(
    properties: Mapping[str, object],
    required: tuple[str, ...],
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


def bind_read_range(value: Mapping[str, object]) -> tuple[str, int, int]:
    revision_id = _text(value.get("revision_id"), "revision_id")
    start = _integer(value.get("start_line"), "start_line")
    end = _integer(value.get("end_line"), "end_line")
    if start < 1 or end < start or end - start > 399:
        raise ValueError("read range must contain 1 to 400 ordered lines")
    return revision_id, start, end


def bind_revision_id(value: Mapping[str, object]) -> str:
    return _text(value.get("revision_id"), "revision_id")


def bind_findings(value: Mapping[str, object]) -> tuple[Finding, ...]:
    raw = value.get("findings")
    if not isinstance(raw, (list, tuple)):
        raise ValueError("findings must be an array")
    findings: list[Finding] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"finding {index} must be an object")
        required = {
            "finding_id",
            "category",
            "severity",
            "summary",
            "acceptance_criteria",
        }
        optional = {
            "depends_on_finding_ids",
            "affected_symbols",
            "source_reviewer_ids",
        }
        if not required.issubset(item) or not set(item).issubset(required | optional):
            raise ValueError(f"finding {index} has invalid fields")
        try:
            category = FindingCategory(item["category"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"finding {index} has invalid category") from error
        findings.append(
            Finding(
                finding_id=_text(item["finding_id"], "finding_id"),
                category=category,
                severity=_text(item["severity"], "severity"),
                summary=_bounded_text(item["summary"], "summary", 2_000),
                acceptance_criteria=_bounded_text(
                    item["acceptance_criteria"],
                    "acceptance_criteria",
                    2_000,
                ),
                depends_on_finding_ids=_text_items(
                    item.get("depends_on_finding_ids", ()),
                    "depends_on_finding_ids",
                    maximum=12,
                ),
                affected_symbols=_text_items(
                    item.get("affected_symbols", ()),
                    "affected_symbols",
                    maximum=24,
                ),
                source_reviewer_ids=_text_items(
                    item.get("source_reviewer_ids", ()),
                    "source_reviewer_ids",
                    maximum=2,
                ),
            )
        )
    if len(findings) > 12:
        raise ValueError("findings cannot exceed 12 items")
    return tuple(findings)


def bind_patch(value: Mapping[str, object]) -> dict[str, object]:
    try:
        scope = PatchScope(value.get("scope"))
    except (TypeError, ValueError) as error:
        raise ValueError("scope must be logic or layout") from error
    finding_ids = value.get("finding_ids")
    if not isinstance(finding_ids, (list, tuple)) or not finding_ids:
        raise ValueError("finding_ids must be a non-empty array")
    if len(finding_ids) > 12:
        raise ValueError("finding_ids cannot exceed 12 items")
    return {
        "base_revision_id": _text(
            value.get("base_revision_id"), "base_revision_id"
        ),
        "base_code_hash": _sha256(value.get("base_code_hash"), "base_code_hash"),
        "scope": scope,
        "old_text": _bounded_text(value.get("old_text"), "old_text", 20_000),
        "new_text": _bounded_text(value.get("new_text"), "new_text", 20_000),
        "finding_ids": tuple(_text(item, "finding_id") for item in finding_ids),
    }


def bind_relation(value: Mapping[str, object]) -> Mapping[str, object]:
    relation = _text(value.get("relation"), "relation")
    operands = value.get("operands")
    if not isinstance(operands, (list, tuple)) or not 1 <= len(operands) <= 6:
        raise ValueError("operands must contain 1 to 6 values")
    return {
        "relation": relation,
        "operands": list(operands),
        "expected": value.get("expected"),
    }


def _text(value: object, name: str) -> str:
    return _bounded_text(value, name, 200)


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _sha256(value: object, name: str) -> str:
    text = _text(value, name)
    if not text.startswith("sha256:") or len(text) != 71:
        raise ValueError(f"{name} must be a sha256 digest")
    return text


def _text_items(value: object, name: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > maximum:
        raise ValueError(f"{name} must be an array of at most {maximum} items")
    result = tuple(_text(item, name) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result
