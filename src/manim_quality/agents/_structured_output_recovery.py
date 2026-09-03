"""Recover only schema-valid structured output already emitted by the model."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

from jsonschema import ValidationError
from jsonschema.validators import validator_for

from manim_quality.contracts._json_values import thaw_json_object

from ._claude_hook_values import ClaudeSdkProtocolError
from ._claude_result import validate_terminal_result
from ._runtime_models import OutputRejected
from ._structured_output_compat import adapt_structured_output

_MAX_TEXT_CHARS = 200_000


def complete_result_output(result, state, schema, controls):
    """Complete from SDK output or model-emitted, schema-valid evidence."""
    exhausted = bool(getattr(state, "_structured_output_exhausted", False))
    correction_terminal = exhausted and _is_correction_terminal(result)
    if correction_terminal:
        if result.num_turns < state.sdk_turn_floor:
            raise ClaudeSdkProtocolError(
                "SDK turn count mismatch: "
                f"result={result.num_turns}, minimum_sdk_turns={state.sdk_turn_floor}"
            )
        state.validate_subagent_protocol()
    else:
        validate_terminal_result(
            result,
            minimum_turns=state.sdk_turn_floor,
            validate_subagents=state.validate_subagent_protocol,
        )
    if isinstance(result.structured_output, Mapping):
        return controls.complete(result.structured_output), None
    for source, candidate in recovery_candidates(state, schema):
        try:
            return controls.complete(candidate), source
        except OutputRejected:
            continue
    if correction_terminal:
        raise ClaudeSdkProtocolError("structured output correction limit exceeded")
    raise ClaudeSdkProtocolError("SDK result has no structured output object")


def _is_correction_terminal(result) -> bool:
    if not result.is_error:
        return True
    detail = " ".join(str(item) for item in (result.errors or ())).lower()
    return "structured output" in detail and "correct" in detail


def record_tool_candidate(state, value: object) -> None:
    if not isinstance(value, Mapping):
        return
    candidates = getattr(state, "_structured_output_candidates", None)
    if candidates is None:
        candidates = state._structured_output_candidates = []
    candidates.append(thaw_json_object(value))


def recovery_candidates(
    state,
    schema: Mapping[str, object],
) -> Iterable[tuple[str, Mapping[str, object]]]:
    """Yield newest-first candidates that pass the declared JSON Schema."""
    seen: set[str] = set()
    for message in reversed(tuple(state.sdk_messages)):
        if (
            message.get("kind") != "assistant"
            or message.get("parent_tool_use_id") is not None
        ):
            continue
        content = message.get("content")
        if not isinstance(content, (list, tuple)):
            continue
        for block in reversed(content):
            if not isinstance(block, Mapping):
                continue
            if block.get("name") == "StructuredOutput":
                yield from _validated(
                    "assistant_structured_tool", block.get("input"), schema, seen
                )
            text = block.get("text")
            if isinstance(text, str):
                for value in _json_objects(text):
                    yield from _validated("assistant_text", value, schema, seen)
    raw = list(getattr(state, "_structured_output_candidates", ()))
    for value in reversed(raw):
        yield from _validated("structured_tool_input", value, schema, seen)


def _validated(source, value, schema, seen):
    if not isinstance(value, Mapping):
        return
    adapted = adapt_structured_output(value, schema)
    if not isinstance(adapted, Mapping):
        return
    plain = thaw_json_object(adapted)
    try:
        validator = validator_for(thaw_json_object(schema))
        validator.check_schema(thaw_json_object(schema))
        validator(thaw_json_object(schema)).validate(plain)
    except ValidationError:
        return
    fingerprint = json.dumps(
        plain, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if fingerprint in seen:
        return
    seen.add(fingerprint)
    yield source, plain


def _json_objects(text: str) -> Iterable[Mapping[str, object]]:
    bounded = text[-_MAX_TEXT_CHARS:]
    decoder = json.JSONDecoder()
    for index, char in enumerate(bounded):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(bounded[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            yield value
