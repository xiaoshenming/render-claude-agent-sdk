"""Source-derived repair, render, append, and verification-state flow."""

from manim_quality.contracts import QualityState, RevisionStage
from manim_quality.revisions.store import RevisionRepository

from .checkpoints import require_proposal, require_rendered
from .failures import StageExecutionError
from .ports import LayoutRepairPort, LogicRepairPort, RenderStage
from .transitions import transition


class RepairCoordinator:
    def __init__(
        self,
        repository: RevisionRepository,
        logic_repair: LogicRepairPort,
        layout_repair: LayoutRepairPort,
        renderer: RenderStage,
    ) -> None:
        self._repository = repository
        self._logic_repair = logic_repair
        self._layout_repair = layout_repair
        self._renderer = renderer

    def repair(self, request, parent, assessment, snapshot, stage):
        layout = stage is RevisionStage.LAYOUT_REPAIR
        repairing, verifying, prefix = _states(layout)
        snapshot = transition(
            self._repository,
            snapshot,
            repairing,
            request.run_id,
            f"{prefix}_repair_started",
            assessment.evidence_hash,
        )
        producer = self._layout_repair if layout else self._logic_repair
        candidate = require_proposal(
            producer.propose(parent, assessment, request), parent, stage
        )
        rendered = self._render(candidate, request)
        snapshot = self._repository.append_revision(
            request.job_id,
            rendered.revision.revision,
            expected_version=snapshot.version,
        )
        snapshot = transition(
            self._repository,
            snapshot,
            verifying,
            request.run_id,
            f"{prefix}_verification_started",
            rendered.render.manifest_evidence_hash,
        )
        return snapshot, rendered.revision, rendered.render

    def _render(self, candidate, request):
        try:
            result = self._renderer.render(candidate, request)
        except Exception as error:
            raise StageExecutionError("render_error", str(error)) from error
        return require_rendered(result, candidate)


def _states(layout: bool):
    if layout:
        return (
            QualityState.LAYOUT_REPAIRING,
            QualityState.LAYOUT_VERIFYING,
            "layout",
        )
    return (
        QualityState.LOGIC_REPAIRING,
        QualityState.LOGIC_VERIFYING,
        "logic",
    )
