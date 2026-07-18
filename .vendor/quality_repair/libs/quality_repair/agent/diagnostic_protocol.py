"""Structured decision protocol for exploratory layout repair agents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ACTION_NO_FIX = "no_fix"
ACTION_NEED_MORE_EVIDENCE = "need_more_evidence"
ACTION_FIX = "fix"
ACTION_UNKNOWN = "unknown"
VALID_ACTIONS = {ACTION_NO_FIX, ACTION_NEED_MORE_EVIDENCE, ACTION_FIX}


@dataclass(kw_only=True)
class AgentDecision:
    """Agent's self-reported diagnostic decision.

    The controller treats this as control-plane input only. Any code patch is
    still accepted or rejected exclusively by the checker/safety gates.
    """

    action: str = ACTION_UNKNOWN
    severity: str | None = None
    confidence: float | None = None
    hypothesis: dict[str, Any] = field(default_factory=dict)
    source_target: dict[str, Any] = field(default_factory=dict)
    patch_intent: dict[str, Any] = field(default_factory=dict)
    evidence_requests: list[dict[str, Any]] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None

    @property
    def valid(self) -> bool:
        return self.parse_error is None and self.action in VALID_ACTIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "severity": self.severity,
            "confidence": self.confidence,
            "hypothesis": dict(self.hypothesis),
            "source_target": dict(self.source_target),
            "patch_intent": dict(self.patch_intent),
            "evidence_requests": list(self.evidence_requests),
            "safety_notes": list(self.safety_notes),
            "valid": self.valid,
            "parse_error": self.parse_error,
            "raw": dict(self.raw),
        }


def parse_agent_decision(text: str | None) -> AgentDecision:
    """Parse the final JSON decision from an SDK final response."""
    if not text or not text.strip():
        return AgentDecision(parse_error="empty_final_text")
    payload_text = _extract_json_object(text.strip())
    if not payload_text:
        return AgentDecision(parse_error="decision_json_not_found")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        return AgentDecision(parse_error=f"decision_json_invalid:{exc.msg}")
    if not isinstance(payload, dict):
        return AgentDecision(parse_error="decision_json_not_object")
    action = str(payload.get("action") or ACTION_UNKNOWN)
    if action not in VALID_ACTIONS:
        parse_error = "decision_action_missing" if action == ACTION_UNKNOWN else f"decision_action_invalid:{action}"
        return AgentDecision(action=ACTION_UNKNOWN, raw=payload, parse_error=parse_error)
    return AgentDecision(
        action=action,
        severity=_string_or_none(payload.get("severity")),
        confidence=_float_or_none(payload.get("confidence")),
        hypothesis=_dict_or_empty(payload.get("hypothesis")),
        source_target=_dict_or_empty(payload.get("source_target")),
        patch_intent=_dict_or_empty(payload.get("patch_intent")),
        evidence_requests=_request_list(payload.get("evidence_requests", payload.get("requests"))),
        safety_notes=[str(item) for item in payload.get("safety_notes", []) if item is not None]
        if isinstance(payload.get("safety_notes"), list)
        else [],
        raw=payload,
    )


def _extract_json_object(text: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _request_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_or_none(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
