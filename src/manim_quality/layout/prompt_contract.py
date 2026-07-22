"""Platform-owned guidance appended to the verified vendor layout prompt."""

from __future__ import annotations

from pathlib import Path

_GUIDANCE = """

Platform repair contract:
- Read the issue digest and source, then choose the safest source-level repair yourself. You may adjust placement, grouping, object lifecycle, updater logic, or local layout structure when the evidence supports it.
- For animated or updater-driven labels, verify the initial state, transition states, and final state. A temporary FadeOut is not a complete repair if the final FadeIn restores the collision.
- When many issues share one dense scene, prefer rebuilding a diagram region, proof region, and title region before repeatedly shrinking font size or buff.
- Preserve teaching meaning. If only low-impact geometry contact remains, leave it as reported risk instead of distorting the diagram.
- Read each unchanged source/evidence file once per round. After Edit, trust the tool's current-file confirmation and only re-read when an error or conflicting evidence requires it.
"""


def extend_layout_prompt(prompt: str) -> str:
    """Add platform repair guidance without modifying the signed vendor payload."""
    return f"{prompt.rstrip()}{_GUIDANCE}".strip()


def install_prompt_contract(module: object) -> None:
    """Wrap the vendor prompt builder once at the runtime adapter boundary."""
    original = getattr(module, "prompt_for", None)
    if not callable(original) or getattr(original, "_platform_contract", False):
        return

    def wrapped(profile: str, workdir: Path, *, round_no: int = 1) -> str:
        prompt = original(profile, workdir, round_no=round_no)
        return extend_layout_prompt(prompt) if profile == "layout" else prompt

    setattr(wrapped, "_platform_contract", True)
    setattr(module, "prompt_for", wrapped)
