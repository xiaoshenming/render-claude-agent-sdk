"""Bind directed-Verifier citations to changed candidate Scene code."""

from __future__ import annotations

import difflib
from collections.abc import Mapping

from ._scene_evidence import extract_scenes
from .repair_plan import RepairPlan


def bind_candidate_evidence(
    value: object,
    before: str,
    code: str,
    plan: RepairPlan,
    issue_id: str,
    *,
    require_changed: bool,
) -> None:
    fields = {"scene_id", "line_start", "line_end", "excerpt"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("candidate evidence fields do not match schema")
    scene_id = _text(value.get("scene_id"), "scene_id")
    start, end = value.get("line_start"), value.get("line_end")
    excerpt = _text(value.get("excerpt"), "excerpt")
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        raise ValueError("candidate evidence line bounds are invalid")
    scenes = {scene.scene_id: scene for scene in extract_scenes(code)}
    scene = scenes.get(scene_id)
    issue = next((item for item in plan.issues if item.issue_id == issue_id), None)
    if issue is None or scene_id not in issue.target_scene_ids or scene is None:
        raise ValueError("candidate evidence Scene is outside repair plan")
    if start < scene.line_start or end > scene.line_end:
        raise ValueError("candidate evidence is outside declared Scene")
    lines = code.splitlines()
    if excerpt not in "\n".join(lines[start - 1 : end]):
        raise ValueError("candidate evidence excerpt is not present at declared lines")
    if require_changed and not _matches_issue_hunk(
        before, code, start, end, issue.evidence
    ):
        raise ValueError("resolved candidate evidence must match issue source hunk")


def _matches_issue_hunk(before, after, start, end, citations) -> bool:
    evidence_lines = set(range(start, end + 1))
    source_ranges = [
        set(range(item.line_start, item.line_end + 1))
        for item in citations
        if item.artifact.value == "candidate_code"
        and item.line_start is not None
        and item.line_end is not None
    ]
    return any(
        evidence_lines & new_lines
        and any(source & old_lines for source in source_ranges)
        for old_lines, new_lines in _changed_hunks(before, after)
    )


def _changed_hunks(before: str, after: str):
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines())
    hunks: list[tuple[set[int], set[int]]] = []
    for tag, _old_start, _old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "insert"}:
            old_lines = set(range(_old_start + 1, _old_end + 1))
            if not old_lines:
                old_lines.add(max(1, _old_start + 1))
            new_lines = set(range(new_start + 1, new_end + 1))
            hunks.append((old_lines, new_lines))
    return tuple(hunks)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value
