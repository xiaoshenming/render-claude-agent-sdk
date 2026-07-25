"""Small state-transition commands with deterministic evidence identities."""

from manim_quality.contracts import QualityState
from manim_quality.delivery.evidence import content_hash
from manim_quality.revisions.store import (
    Checkpoint,
    QualityJobSnapshot,
    RevisionRepository,
    TransitionEvidence,
)


def transition(
    repository: RevisionRepository,
    snapshot: QualityJobSnapshot,
    target: QualityState,
    run_id: str,
    reason: str,
    evidence_hash: str,
) -> QualityJobSnapshot:
    evidence = TransitionEvidence(f"{run_id}:{reason}", reason, evidence_hash)
    return repository.transition_state(
        snapshot.job_id,
        snapshot.state,
        target,
        evidence,
        expected_version=snapshot.version,
    )


def certify(
    repository: RevisionRepository,
    snapshot: QualityJobSnapshot,
    checkpoint: Checkpoint,
    revision_id: str,
    target: QualityState,
    run_id: str,
    reason: str,
    certificate_hash: str,
) -> QualityJobSnapshot:
    evidence = TransitionEvidence(f"{run_id}:{reason}", reason, certificate_hash)
    return repository.certify_checkpoint_state(
        snapshot.job_id,
        checkpoint,
        revision_id,
        target,
        evidence,
        expected_version=snapshot.version,
    )


def event_hash(kind: str, *identities: str) -> str:
    return content_hash({"identities": list(identities), "kind": kind})
