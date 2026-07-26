"""Declarative registration of the seven Quality Operator MCP tools."""

from collections.abc import Mapping

from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect

from .tool_schemas import (
    APPLY_PATCH_SCHEMA,
    CHECK_RELATION_SCHEMA,
    READ_SOLUTION_SCHEMA,
    RECORD_FINDINGS_SCHEMA,
    REVISION_INPUT_SCHEMA,
)

SERVER = "quality"

# Validation tools run a real render (1200 s cap) plus BBox probe (1200 s cap)
# and the detector in a worker thread; their timeout must cover that chain.
_EXTERNAL_VALIDATION_TIMEOUT_MS = 2_700_000


def register_quality_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        *_read_tools(handlers),
        *_edit_tools(handlers),
        *_validation_tools(handlers),
        _submit_tool(handlers),
    )


def _patch_budget(handlers) -> int:
    session = getattr(handlers, "session", None)
    budget = getattr(session, "max_patch_attempts", 5)
    return budget if isinstance(budget, int) and budget > 0 else 5


def _read_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        _grant(
            "read_solution",
            "Read the complete Solution class and no surrounding framework code.",
            READ_SOLUTION_SCHEMA,
            handlers.read_solution,
            ToolEffect.READ_ONLY,
            1,
            30_000,
        ),
        _grant(
            "check_relation",
            "Evaluate one declared mathematical or geometric relation.",
            CHECK_RELATION_SCHEMA,
            handlers.check_relation,
            ToolEffect.READ_ONLY,
            6,
            8_000,
        ),
    )


def _edit_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        _grant(
            "record_findings",
            "Freeze issues and acceptance criteria before any patch.",
            RECORD_FINDINGS_SCHEMA,
            handlers.record_findings,
            ToolEffect.SESSION_MUTATION,
            4,
            12_000,
        ),
        _grant(
            "apply_patch",
            "Apply one exact block replacement to create a child revision.",
            APPLY_PATCH_SCHEMA,
            handlers.apply_patch,
            ToolEffect.REVISION_MUTATION,
            _patch_budget(handlers),
            8_000,
            max_input_bytes=48_000,
        ),
    )


def _validation_tools(handlers) -> tuple[ManagedToolGrant, ...]:
    return (
        _grant(
            "inspect_layout",
            "Run the bound overlap detector against the current revision.",
            REVISION_INPUT_SCHEMA,
            handlers.inspect_layout,
            ToolEffect.VALIDATION,
            _patch_budget(handlers) + 1,
            30_000,
            timeout_ms=_EXTERNAL_VALIDATION_TIMEOUT_MS,
        ),
        _grant(
            "validate_revision",
            "Run bounded external checks and return facts without accepting.",
            REVISION_INPUT_SCHEMA,
            handlers.validate_revision,
            ToolEffect.VALIDATION,
            _patch_budget(handlers),
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
        1,
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
