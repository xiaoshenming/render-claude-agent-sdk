"""Declarative registration of Quality Operator evidence tools."""

from collections.abc import Mapping

from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect

from .defaults import PARENT_MAX_TOOL_CALLS
from .tool_schemas import (
    CHECK_RELATION_SCHEMA,
    CURRENT_REVISION_SCHEMA,
    RECORD_FINDINGS_SCHEMA,
    REVISION_INPUT_SCHEMA,
)

SERVER = "quality"

# Validation tools run a real render (1200 s cap) plus BBox probe (1200 s cap)
# and the detector in a worker thread; their timeout must cover that chain.
_EXTERNAL_VALIDATION_TIMEOUT_MS = 2_700_000


def register_quality_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        *_evidence_tools(handlers),
        *_validation_tools(handlers),
        _submit_tool(handlers),
    )


def _patch_budget(handlers) -> int:
    session = getattr(handlers, "session", None)
    budget = getattr(session, "max_patch_attempts", 12)
    return budget if isinstance(budget, int) and budget > 0 else 12


def _evidence_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        _grant(
            "check_relation",
            (
                "Evaluate one declared relation. Supported: "
                "numeric_equal [a, b]; parallel / perpendicular "
                "[[dx,dy], [dx,dy]] direction vectors; collinear [p, p, p]; "
                "midpoint [m, a, b]; equal_length [a1, a2, b1, b2]; "
                "equal_distance [center, p1, p2]; point_on_segment "
                "[p, seg_start, seg_end]; angle_degrees "
                "[vertex, point_a, point_b, degrees]. Points are [x, y] "
                "or [x, y, z] numbers. Other relations return "
                "unsupported_or_malformed_relation."
            ),
            CHECK_RELATION_SCHEMA,
            handlers.check_relation,
            ToolEffect.READ_ONLY,
            PARENT_MAX_TOOL_CALLS,
            8_000,
        ),
        _grant(
            "record_findings",
            "Freeze issues and acceptance criteria before any patch.",
            RECORD_FINDINGS_SCHEMA,
            handlers.record_findings,
            ToolEffect.SESSION_MUTATION,
            12,
            12_000,
        ),
        _grant(
            "recover_revision",
            "Restore a previously validated passing revision as the repair base.",
            REVISION_INPUT_SCHEMA,
            handlers.recover_revision,
            ToolEffect.SESSION_MUTATION,
            max(1, _patch_budget(handlers) - 1),
            4_000,
        ),
    )


def _validation_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        _grant(
            "inspect_layout",
            "Run the bound overlap detector against the current revision.",
            CURRENT_REVISION_SCHEMA,
            handlers.inspect_layout,
            ToolEffect.VALIDATION,
            _patch_budget(handlers) + 6,
            30_000,
            timeout_ms=_EXTERNAL_VALIDATION_TIMEOUT_MS,
        ),
        _grant(
            "validate_revision",
            "Run bounded external checks and return facts without accepting.",
            CURRENT_REVISION_SCHEMA,
            handlers.validate_revision,
            ToolEffect.VALIDATION,
            _patch_budget(handlers) + 4,
            30_000,
            timeout_ms=_EXTERNAL_VALIDATION_TIMEOUT_MS,
        ),
    )


def _submit_tool(handlers) -> ManagedToolGrant:
    return _grant(
        "submit_revision",
        "Submit the validated current candidate to the outer Harness.",
        REVISION_INPUT_SCHEMA,
        handlers.submit_revision,
        ToolEffect.SESSION_MUTATION,
        max(4, _patch_budget(handlers) // 3),
        4_000,
    )


def _grant(
    name: str,
    description: str,
    input_schema: Mapping[str, object],
    handler,
    effect: ToolEffect,
    max_calls: int,
    max_result_chars: int,
    *,
    max_input_bytes: int = 16_000,
    timeout_ms: int = 30_000,
) -> ManagedToolGrant:
    return ManagedToolGrant(
        server_name=SERVER,
        name=name,
        description=description,
        input_schema=input_schema,
        handler=handler,
        effect=effect,
        max_calls=max_calls,
        timeout_ms=timeout_ms,
        max_result_chars=max_result_chars,
        max_input_bytes=max_input_bytes,
    )
