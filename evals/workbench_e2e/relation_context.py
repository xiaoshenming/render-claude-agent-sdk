"""Build fail-open Expected/Actual evidence for the Logic Reviewer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from evals._expected_relation_probe import evaluate_code
from evals._logic_shadow_io import JsonUsageSink
from manim_quality.agents import (
    AgentRuntime,
    BudgetLimits,
    ClaudeSdkBackend,
    reviewer_profile,
)
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.logic.expectations.extractor import ExpectedRelationExtractor

from .rendering import scene_name


def load_or_build_relation_context(*, cache_path: Path, **kwargs) -> dict[str, object]:
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = None
    if isinstance(cached, dict):
        return cached
    payload = build_relation_context(**kwargs)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def relation_prompt_evidence(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Keep only relation facts that can affect the review decision."""
    if payload.get("status") != "available":
        return None
    contract = payload.get("contract")
    comparison = payload.get("actual_comparison")
    if not isinstance(contract, Mapping) or not isinstance(comparison, Mapping):
        return None
    claims = contract.get("claims")
    comparisons = comparison.get("comparisons")
    if not claims and not comparisons:
        return None
    return {
        "status": "available",
        "scene_id": payload.get("scene_id"),
        "contract": {
            "schema_version": contract.get("schema_version"),
            "claims": claims or [],
        },
        "actual_comparison": {
            "flagged": bool(comparison.get("flagged")),
            "target_hit": comparison.get("target_hit"),
            "counts": comparison.get("counts") or {},
            "comparisons": comparisons or [],
        },
    }


def build_relation_context(
    *,
    sample_id: str,
    code: str,
    problem: str,
    expected: str | None,
    planning: Mapping[str, object],
    workspace: Path,
    model: str,
    provider_env: Mapping[str, str],
    output_dir: Path,
) -> dict[str, object]:
    """Return bounded evidence; extraction failures remain explicit warnings."""
    source = workspace / "expected_relation_source.txt"
    source.write_text(
        _source_text(problem, expected, planning), encoding="utf-8"
    )
    sink = JsonUsageSink(output_dir / "expected_relation_agent_call.json")
    runtime = AgentRuntime(
        ClaudeSdkBackend(provider_env=provider_env), sink, _limits()
    )
    extractor = ExpectedRelationExtractor(
        runtime=runtime,
        profile=reviewer_profile(
            model=model,
            prompt_version="expected-relations-v1-production-readonly",
            schema_version="expected-relations-v1",
            tool_version=f"claude-agent-sdk-{sdk_version}-read-v1",
        ),
    )
    try:
        extraction = extractor.extract(
            run_id=f"expected-{sample_id}",
            workspace=workspace,
            source_path=source,
            estimated_input_tokens=max(1_000, source.stat().st_size // 2),
            reserved_output_tokens=20_000,
        )
        scene_id = scene_name(code)
        comparison = evaluate_code(code, scene_id, extraction.contract)
        payload = {
            "status": "available",
            "scene_id": scene_id,
            "contract": thaw_json_object(
                extraction.call_record.structured_output or {}
            ),
            "actual_comparison": comparison.to_dict(),
            "usage": _usage(extraction.call_record),
        }
    except Exception as error:  # evidence collection must remain fail-open
        payload = {
            "status": "unavailable",
            "error": f"{type(error).__name__}: {error}"[:1000],
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "expected_actual_relations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def _source_text(
    problem: str, expected: str | None, planning: Mapping[str, object]
) -> str:
    relation_plan = {
        key: value
        for key, value in planning.items()
        if key not in {"generation_messages", "expected_actual_relations"}
    }
    return "\n\n".join(
        (
            "[problem]\n" + problem,
            "[solution]\n" + (expected or ""),
            "[plan]\n" + json.dumps(relation_plan, ensure_ascii=False, indent=2),
        )
    )


def _usage(record) -> dict[str, int]:
    return {
        "input_tokens": record.usage.input_tokens,
        "output_tokens": record.usage.output_tokens,
        "cache_read_tokens": record.usage.cache_read_tokens,
        "cache_write_tokens": record.usage.cache_write_tokens,
        "total_tokens": record.usage.total_tokens,
        "elapsed_ms": record.elapsed_ms,
    }


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=80_000,
        max_turns=4,
        max_tool_calls=4,
        max_elapsed_ms=180_000,
        max_input_tokens=50_000,
        max_output_tokens=35_000,
        max_cache_read_tokens=50_000,
        max_cache_write_tokens=50_000,
        max_total_tokens=160_000,
    )
