"""Strict lifecycle and result contract for native foreground Reviewers."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ._reviewer_values import raw_reviewer_payload, reviewer_payload


class SubagentProtocolError(RuntimeError):
    pass


@dataclass(slots=True)
class _Run:
    agent_type: str
    tool_use_id: str
    agent_id: str | None = None
    started_ms: int | None = None
    stopped_ms: int | None = None
    solution_read: bool = False
    result: dict[str, object] | None = None


class NativeSubagentProtocol:
    def __init__(self, expected: Sequence[str]) -> None:
        self._expected = frozenset(expected)
        self._runs: dict[str, _Run] = {}
        self._agent_ids: set[str] = set()

    @property
    def expected_names(self) -> frozenset[str]:
        return self._expected

    @property
    def results(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            run.result for run in self._runs.values() if run.result is not None
        )

    @property
    def completed_names(self) -> frozenset[str]:
        return frozenset(
            name for name, run in self._runs.items() if run.result is not None
        )

    def owns_tool_use_id(self, tool_use_id: str) -> bool:
        return any(run.tool_use_id == tool_use_id for run in self._runs.values())

    def authorize(self, agent_type: str, tool_use_id: str) -> None:
        if agent_type not in self._expected:
            raise SubagentProtocolError("Reviewer type is not registered")
        if agent_type in self._runs:
            raise SubagentProtocolError(f"Reviewer may only run once: {agent_type}")
        self._runs[agent_type] = _Run(agent_type, tool_use_id)

    def start(self, agent_type: object, agent_id: object) -> None:
        run = self._run(agent_type)
        if run.agent_id is not None:
            raise SubagentProtocolError(f"Reviewer started twice: {run.agent_type}")
        if not isinstance(agent_id, str) or not agent_id:
            raise SubagentProtocolError("Reviewer agent_id is required")
        if agent_id in self._agent_ids:
            raise SubagentProtocolError("Reviewer agent_id must be unique")
        run.agent_id = agent_id
        run.started_ms = _now_ms()
        self._agent_ids.add(agent_id)

    def authorize_tool(
        self,
        *,
        agent_type: object,
        agent_id: object,
        tool_name: str,
    ) -> None:
        run = self._active_run(agent_type, agent_id)
        if tool_name.endswith("__read_solution"):
            run.solution_read = True

    def stop(self, agent_type: object, agent_id: object) -> None:
        run = self._active_run(agent_type, agent_id)
        if not run.solution_read:
            raise SubagentProtocolError(
                f"Reviewer completed without read_solution: {run.agent_type}"
            )
        run.stopped_ms = _now_ms()

    def validate_agent_completion(self, tool_use_id: str) -> None:
        run = self._run_for_tool(tool_use_id)
        if run.stopped_ms is None:
            raise SubagentProtocolError("Agent tool completed before Reviewer stop")

    def record_result(
        self,
        *,
        tool_use_id: str,
        content: object,
        is_error: bool,
        parent_tool_use_id: str | None,
    ) -> None:
        run = self._run_for_tool(tool_use_id)
        if run.stopped_ms is None:
            raise SubagentProtocolError("Reviewer ToolResult arrived before stop")
        if run.result is not None:
            raise SubagentProtocolError(
                f"duplicate Reviewer ToolResult: {run.agent_type}"
            )
        if is_error:
            raise SubagentProtocolError(
                f"Reviewer returned an error ToolResult: {run.agent_type}"
            )
        text = _result_text(content)
        try:
            reviewer_text, sdk_metadata = _result_parts(
                text, expected_agent_id=run.agent_id
            )
            raw_payload = raw_reviewer_payload(reviewer_text, SubagentProtocolError)
        except SubagentProtocolError as error:
            if "contains no JSON object" not in str(error):
                raise
            raw_payload = _evidence_payload(text)
            reviewer_text = json.dumps(raw_payload, ensure_ascii=False)
            sdk_metadata = None
        payload = reviewer_payload(reviewer_text, SubagentProtocolError)
        run.result = {
            "agent_type": run.agent_type,
            "agent_id": run.agent_id,
            "tool_use_id": run.tool_use_id,
            "parent_tool_use_id": parent_tool_use_id,
            "started_ms": run.started_ms,
            "stopped_ms": run.stopped_ms,
            "completed_ms": _now_ms(),
            "is_error": False,
            "content": reviewer_text,
            "raw_content": text,
            "payload": payload,
            "raw_payload": raw_payload,
            "sdk_metadata": sdk_metadata,
            "parent_next_message_id": None,
        }

    def bind_parent_message(self, message_id: str | None) -> None:
        for run in self._runs.values():
            if run.result is not None and run.result["parent_next_message_id"] is None:
                run.result["parent_next_message_id"] = message_id

    def validate_complete(self) -> None:
        if set(self._runs) != self._expected:
            raise SubagentProtocolError("required Reviewers were not all authorized")
        for run in self._runs.values():
            if run.agent_id is None or run.stopped_ms is None or run.result is None:
                raise SubagentProtocolError(
                    f"Reviewer lifecycle is incomplete: {run.agent_type}"
                )
            if run.result["parent_next_message_id"] is None:
                raise SubagentProtocolError(
                    f"parent did not consume Reviewer result: {run.agent_type}"
                )

    def _active_run(self, agent_type: object, agent_id: object) -> _Run:
        run = self._run(agent_type)
        if run.agent_id != agent_id:
            raise SubagentProtocolError("Reviewer agent_id does not match start event")
        if run.stopped_ms is not None:
            raise SubagentProtocolError("Reviewer tool call occurred after stop")
        return run

    def _run(self, agent_type: object) -> _Run:
        if not isinstance(agent_type, str) or agent_type not in self._runs:
            raise SubagentProtocolError("unknown Reviewer lifecycle event")
        return self._runs[agent_type]

    def _run_for_tool(self, tool_use_id: str) -> _Run:
        for run in self._runs.values():
            if run.tool_use_id == tool_use_id:
                return run
        raise SubagentProtocolError("ToolResult does not match a Reviewer call")


def _result_text(content: object) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            item.get("text")
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text"
        ]
        if not parts or any(not isinstance(item, str) for item in parts):
            raise SubagentProtocolError("Reviewer ToolResult must contain text")
        text = "\n".join(parts)
    else:
        raise SubagentProtocolError("Reviewer ToolResult must be text")
    if not text.strip() or len(text) > 8_500:
        raise SubagentProtocolError("Reviewer ToolResult exceeds transport bound")
    return text


_SDK_RESULT_TRAILER = re.compile(
    r"""
    \s*agentId:\s*(?P<agent_id>[A-Za-z0-9_-]+)
    \s+\(use\ SendMessage\ with\ to:\s*'(?P=agent_id)',
    \s*summary:\s*'<5-10\ word\ recap>'\s*to\ continue\ this\ agent\)
    \s*<usage>
    \s*subagent_tokens:\s*(?P<tokens>\d+)
    \s*tool_uses:\s*(?P<tool_uses>\d+)
    \s*duration_ms:\s*(?P<duration_ms>\d+)
    \s*</usage>\s*
    """,
    re.VERBOSE,
)


def _result_parts(
    text: str,
    *,
    expected_agent_id: str | None,
) -> tuple[str, Mapping[str, object] | None]:
    """Locate the last reviewer-shaped JSON and preserve prose as evidence."""

    stripped = text.lstrip()
    reason = "Reviewer ToolResult contains no JSON object"
    candidates: list[tuple[int, int]] = []
    for start in _json_candidate_starts(stripped):
        try:
            value, end = json.JSONDecoder().raw_decode(stripped[start:])
        except json.JSONDecodeError:
            continue
        end += start
        if isinstance(value, Mapping) and "decision" in value:
            candidates.append((start, end))
    for start, end in reversed(candidates):
        parts = _accepted_parts(stripped, start, end, expected_agent_id)
        if parts is not None:
            return parts
    raise SubagentProtocolError(reason)


def _accepted_parts(
    stripped: str,
    start: int,
    end: int,
    expected_agent_id: str | None,
) -> tuple[str, Mapping[str, object] | None] | None:
    reviewer_text = stripped[start:end]
    if len(reviewer_text) > 8_000:
        raise SubagentProtocolError("Reviewer ToolResult exceeds 8000 characters")
    trailer = _without_closing_fence(stripped[end:])
    if not trailer.strip():
        return reviewer_text, None
    match = _SDK_RESULT_TRAILER.fullmatch(trailer)
    if match is None:
        return reviewer_text, None
    if expected_agent_id is None or match["agent_id"] != expected_agent_id:
        raise SubagentProtocolError("Reviewer ToolResult agent_id does not match hook")
    return reviewer_text, {
        "agent_id": match["agent_id"],
        "subagent_tokens": int(match["tokens"]),
        "tool_uses": int(match["tool_uses"]),
        "duration_ms": int(match["duration_ms"]),
    }


def _json_candidate_starts(stripped: str) -> list[int]:
    seen: set[int] = set()
    starts: list[int] = []
    for match in re.finditer(r"```(?:json)?\s*\{", stripped):
        position = match.end() - 1
        if position not in seen:
            seen.add(position)
            starts.append(position)
    for match in re.finditer(r"\{", stripped):
        if len(starts) >= 32:
            break
        if match.start() not in seen:
            seen.add(match.start())
            starts.append(match.start())
    return starts


def _without_closing_fence(trailer: str) -> str:
    stripped = trailer.lstrip()
    if stripped.startswith("```"):
        return stripped[3:]
    return trailer


def _evidence_payload(text: str) -> Mapping[str, object]:
    warning = ["unstructured_output_preserved"]
    return {"decision": "needs_repair", "issues": [], "confidence": 0.0,
            "diagnosis": text.strip()[:6_000] or "Reviewer 未返回文本。",
            "coverage": {"protocol_warnings": warning}}


def _now_ms() -> int:
    return int(time.time() * 1_000)
