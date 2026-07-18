"""Secret-free records persisted for quality-platform admin inspection."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.core.config import settings
from app.quality_platform.retention_layout import layout_summary


_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_AUTH_PATTERN = re.compile(
    r"\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+|"
    r"\bbearer\s+[^\s,;]+",
    re.IGNORECASE,
)
_KEY_PATTERN = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token)\s*[:=]\s*"
    r"[^\s,;]+",
    re.IGNORECASE,
)
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)


def build_review_retention(
    *,
    model: str,
    status: str,
    review: Mapping[str, Any] | None,
    candidate_code_hash: str,
    selected_code_hash: str,
    fail_open: bool,
    error: str = "",
) -> dict[str, Any]:
    """Return an explicit allowlist; provider credentials cannot enter this record."""
    source = review if isinstance(review, Mapping) else {}
    issues = source.get("issues") if isinstance(source.get("issues"), list) else []
    return {
        "model": _text(model, 200),
        "status": _text(status, 80),
        "decision": _text(source.get("decision"), 80),
        "summary": _sanitize_text(source.get("summary"), 4000),
        "issues": [_issue(item) for item in issues[:100] if isinstance(item, Mapping)],
        "candidate_code_hash": _text(candidate_code_hash, 160),
        "selected_code_hash": _text(selected_code_hash, 160),
        "fail_open": bool(fail_open),
        "error": _sanitize_text(error, 1000),
    }


def quality_event_record(
    evidence: Mapping[str, Any], *, manifest_url: str = ""
) -> tuple[dict[str, Any], dict[str, str]]:
    """Select only the retention contract for the quality_events JSON columns."""
    fallback_hash = str(evidence.get("archive_code_hash") or "")
    payload = build_review_retention(
        model=str(evidence.get("model") or ""),
        status=str(evidence.get("status") or ""),
        review={
            "decision": evidence.get("decision"),
            "summary": evidence.get("summary"),
            "issues": evidence.get("issues"),
        },
        candidate_code_hash=str(
            evidence.get("candidate_code_hash") or fallback_hash
        ),
        selected_code_hash=str(
            evidence.get("selected_code_hash") or fallback_hash
        ),
        fail_open=bool(evidence.get("fail_open", evidence.get("fail_open_used"))),
        error=str(evidence.get("error") or ""),
    )
    payload.update(
        schema_version=_text(evidence.get("schema_version"), 160),
        source_head=_text(evidence.get("source_head"), 160),
        logic=_stage(evidence.get("logic"), "logic"),
        layout=_stage(evidence.get("layout"), "layout"),
        elapsed_ms=_number(evidence.get("elapsed_ms")),
    )
    references = {
        "manifest_path": _text(evidence.get("manifest_path"), 1000),
        "manifest_url": _text(manifest_url, 2000),
    }
    return payload, references


async def persist_quality_event(
    log_event: Any,
    task_data: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    manifest_url: str = "",
) -> bool:
    """Persist the admin-visible record without affecting the render archive."""
    payload, references = quality_event_record(
        evidence, manifest_url=manifest_url
    )
    try:
        await log_event(
            "pre_archive_quality_platform_completed",
            task_data,
            payload=payload,
            evidence=references,
        )
        return True
    except Exception:  # noqa: BLE001 - observability must remain fail-open.
        return False


def _issue(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "scene": _sanitize_text(value.get("scene"), 300),
        "issue": _sanitize_text(value.get("issue"), 2000),
        "evidence": _sanitize_text(value.get("evidence"), 4000),
    }


def _stage(value: Any, kind: str) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    names = (
        (
            "status",
            "decision",
            "review_tokens",
            "repair_tokens",
            "review_elapsed_ms",
            "repair_elapsed_ms",
            "error",
        )
        if kind == "logic"
        else (
            "status",
            "before_blocking",
            "after_blocking",
            "rounds",
            "tokens",
            "elapsed_ms",
            "requires_render_recheck",
            "error",
            "issue_summary",
        )
    )
    return {
        name: (
            _sanitize_text(value.get(name), 1000)
            if name in {"status", "decision", "error"}
            else layout_summary(
                value.get(name), text=_text, sanitize=_sanitize_text, number=_number
            ) if name == "issue_summary" else value.get(name)
        )
        for name in names
    }


def _number(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _sanitize_text(value: Any, limit: int) -> str:
    text = str(value or "")
    configured = (
        settings.MANIM_QUALITY_ANTHROPIC_API_KEY,
        settings.MANIM_QUALITY_ANTHROPIC_BASE_URL,
    )
    for secret in sorted(
        (str(item) for item in configured if str(item or "").strip()),
        key=len,
        reverse=True,
    ):
        text = text.replace(secret, "[REDACTED]")
    text = _AUTH_PATTERN.sub("[REDACTED_AUTH]", text)
    text = _KEY_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _SK_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _URL_PATTERN.sub("[REDACTED_URL]", text)
    return text[:limit]
