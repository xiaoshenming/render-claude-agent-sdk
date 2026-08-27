"""Fallback payload for unstructured Reviewer evidence."""

from collections.abc import Mapping


def evidence_payload(text: str) -> Mapping[str, object]:
    return {"decision": "needs_repair", "issues": [], "confidence": 0.0,
            "diagnosis": text.strip()[:6_000] or "Reviewer 未返回文本。",
            "coverage": {"protocol_warnings": ["unstructured_output_preserved"]}}
