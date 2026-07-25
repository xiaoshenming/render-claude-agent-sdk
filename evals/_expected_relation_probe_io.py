"""Input validation and reporting for the expected relation probe."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.agents import AgentRunFailed

PROVIDER_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


def selection(path: Path) -> tuple[str, ...]:
    payload = json_object(path.resolve(strict=True))
    values = payload.get("sample_ids")
    if not isinstance(values, list) or not values:
        raise ValueError("selection sample_ids must be a non-empty array")
    result = tuple(plain_text(value, "sample_id") for value in values)
    if len(result) != len(set(result)):
        raise ValueError("selection contains duplicate sample IDs")
    return result


def case_dir(root: Path, sample_id: str) -> Path:
    path = (root / "samples" / sample_id).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_dir():
        raise ValueError("selected sample escapes dataset root")
    return path


def required(root: Path, name: str) -> Path:
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"required sample artifact is invalid: {name}")
    return path


def json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path.name}")
    return value


def provider_environment(environ: Mapping[str, str]) -> dict[str, str]:
    values = {
        name: value
        for name in PROVIDER_ENV
        if (value := environ.get(name, "")).strip()
    }
    authentication = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
    if not any(name in values for name in authentication):
        raise ValueError("provider authentication is required")
    return values


def text(value: Mapping[str, object], key: str) -> str:
    return plain_text(value.get(key), key)


def plain_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def integer(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int) or result < 1:
        raise ValueError(f"{key} must be a positive integer")
    return result


def error_text(error: Exception) -> str:
    if isinstance(error, AgentRunFailed):
        return error.record.error or str(error)
    return f"{type(error).__name__}: {error}"


def build_report(
    results: Sequence[Mapping[str, object]], model: str, sdk_version: str
) -> dict[str, object]:
    successful = [item for item in results if not item.get("error")]
    attempted = len(results)
    target_hits = _sum_truth(successful, "mutated", "target_hit")
    original_flags = _sum_truth(successful, "original", "flagged")
    mutation_flags = _sum_truth(successful, "mutated", "flagged")
    claims = sum(int(item.get("claim_count", 0)) for item in successful)
    unknown = _sum_int(successful, "mutated", "counts", "unknown")
    total_tokens = _sum_int(successful, "usage", "total_tokens")
    metrics = {
        "attempted": attempted,
        "successful": len(successful),
        "errors": attempted - len(successful),
        "claims": claims,
        "average_claims": _average(claims, len(successful)),
        "mutation_flag_rate": _ratio(mutation_flags, len(successful)),
        "target_line_recall": _ratio(target_hits, len(successful)),
        "original_false_positive_rate": _ratio(original_flags, len(successful)),
        "unknown_claim_rate": _ratio(unknown, claims),
        "total_tokens": total_tokens,
        "average_tokens": _average(total_tokens, len(successful)),
        "average_model_rounds": _average(
            _sum_int(successful, "usage", "model_rounds"), len(successful)
        ),
        "average_elapsed_ms": _average(
            _sum_int(successful, "usage", "elapsed_ms"), len(successful)
        ),
    }
    return {
        "schema_version": "manim-quality.expected-relation-probe-report.v1",
        "model": model,
        "claude_agent_sdk_version": sdk_version,
        "metrics": metrics,
        "cases": list(results),
    }


def print_metrics(value: object) -> None:
    metrics = value if isinstance(value, Mapping) else {}
    print(
        "probe summary: "
        f"successful={metrics.get('successful')}/{metrics.get('attempted')} "
        f"target_recall={metrics.get('target_line_recall')} "
        f"control_fpr={metrics.get('original_false_positive_rate')} "
        f"avg_tokens={metrics.get('average_tokens')}",
        flush=True,
    )


def _sum_truth(values: Sequence[Mapping[str, object]], *keys: str) -> int:
    return sum(bool(_nested(item, *keys)) for item in values)


def _sum_int(values: Sequence[Mapping[str, object]], *keys: str) -> int:
    return sum(int(_nested(item, *keys) or 0) for item in values)


def _nested(value: Mapping[str, object], *keys: str) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _average(total: int, count: int) -> float | None:
    return total / count if count else None
