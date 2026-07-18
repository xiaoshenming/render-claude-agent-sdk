"""Small scene-level patch helpers for post-render repair candidates."""

from __future__ import annotations

import difflib
import hashlib
import re

from app.workers.post_render_logic.schemas import RepairAttempt


def apply_scene_replacements(
    *,
    code: str,
    replacements: dict[str, dict[str, str]],
    plan_id: str,
    issue_ids: list[str],
) -> tuple[str, RepairAttempt]:
    """Apply literal replacements only inside named Scene classes."""
    current = code
    touched: list[dict[str, str]] = []
    changed_claims: list[dict[str, str]] = []

    linked_issue_id = issue_ids[0] if issue_ids else ""
    for scene_id, scene_replacements in replacements.items():
        scene_code = _extract_scene_code(current, scene_id)
        if not scene_code:
            continue

        fixed_scene = scene_code
        for before, after in scene_replacements.items():
            if before not in fixed_scene:
                continue
            fixed_scene = fixed_scene.replace(before, after)
            changed_claims.append(
                {
                    "before": before,
                    "after": after,
                    "linked_issue_id": linked_issue_id,
                }
            )

        if fixed_scene == scene_code:
            continue
        current = current.replace(scene_code, fixed_scene, 1)
        touched.append(
            {
                "artifact": "scene_code",
                "scene_id": scene_id,
                "symbol": "class_body",
            }
        )

    attempt = RepairAttempt(
        repair_attempt_id=_attempt_id(plan_id, current),
        plan_id=plan_id,
        declared_scope="scene_logic",
        touched_regions=touched,
        changed_claims=changed_claims,
        patch={
            "format": "unified_diff",
            "content": _diff(code, current),
        },
    )
    return current, attempt


def _extract_scene_code(code: str, scene_id: str) -> str:
    pattern = re.compile(
        rf"(?ms)^class\s+{re.escape(scene_id)}\s*\([^)]*\)\s*:.*?"
        rf"(?=^class\s+Scene_\d+_\w+\s*\(|\Z)"
    )
    match = pattern.search(code or "")
    return match.group(0).strip() if match else ""


def _diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="before.py",
            tofile="after.py",
        )
    )


def _attempt_id(plan_id: str, code: str) -> str:
    digest = hashlib.sha1(f"{plan_id}:{code}".encode("utf-8")).hexdigest()[:10]
    return f"repair-attempt-{digest}"
