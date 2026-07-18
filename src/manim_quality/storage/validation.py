"""Store-neutral revision and checkpoint validation."""

from manim_quality.contracts import Revision
from manim_quality.revisions.store import Checkpoint

_PREREQUISITES = {
    Checkpoint.LOGIC_CERTIFIED: Checkpoint.RENDER_BASELINE,
    Checkpoint.LAYOUT_CERTIFIED: Checkpoint.LOGIC_CERTIFIED,
    Checkpoint.DELIVERY: Checkpoint.LAYOUT_CERTIFIED,
}


def require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def require_revision(value: object) -> Revision:
    if not isinstance(value, Revision):
        raise TypeError("revision must be a Revision")
    return value


def checkpoint_prerequisite(checkpoint: Checkpoint) -> Checkpoint:
    return _PREREQUISITES[checkpoint]


def evidence_field(checkpoint: Checkpoint) -> str:
    return checkpoint.value.replace("_revision_id", "_evidence_hash")
