import pytest

from manim_quality.operator.models import (
    Finding,
    FindingCategory,
    PatchScope,
)
from manim_quality.operator.session import QualitySession

PROBLEM = "Problem: prove AB is parallel to CD."
BASELINE = f'''from manim import *

class Solution(BaseConfigScene):
    """{PROBLEM}"""

    def construct(self):
        line = Line(LEFT, RIGHT)
        self.add(line)
'''


def _finding(
    finding_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    category: FindingCategory = FindingCategory.LOGIC,
    affected_symbols: tuple[str, ...] = ("Solution.construct",),
) -> Finding:
    return Finding(
        finding_id=finding_id,
        category=category,
        severity="blocking",
        summary=f"Supported defect {finding_id}.",
        acceptance_criteria=f"Repair {finding_id} without regressions.",
        depends_on_finding_ids=depends_on,
        affected_symbols=affected_symbols,
    )


def _session() -> QualitySession:
    value = QualitySession(problem_text=PROBLEM, candidate_code=BASELINE)
    value.mark_solution_read("R0")
    return value


def test_failed_patch_can_recover_best_validated_revision_and_branch() -> None:
    quality = _session()
    quality.record_findings((_finding("logic-1"),))
    first = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=first.revision_id,
        passed=True,
        improved=True,
        fingerprint="sha256:" + "1" * 64,
    )
    quality.mark_solution_read(first.revision_id)
    failed = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, 2 * RIGHT)",
        new_text="Line(LEFT, 3 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=failed.revision_id,
        passed=False,
        improved=False,
        fingerprint="sha256:" + "2" * 64,
    )

    recovered = quality.recover_revision("R1")

    assert recovered.revision_id == "R1"
    assert quality.current_revision.revision_id == "R1"
    quality.mark_solution_read("R1")
    replacement = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, 2 * RIGHT)",
        new_text="Line(LEFT, 4 * RIGHT)",
        finding_ids=("logic-1",),
    )
    assert replacement.revision_id == "R3"
    assert replacement.parent_revision_id == "R1"


def test_recovery_rejects_unvalidated_or_failed_revision() -> None:
    quality = _session()
    quality.record_findings((_finding("logic-1"),))
    failed = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=failed.revision_id,
        passed=False,
        improved=False,
        fingerprint="sha256:" + "3" * 64,
    )
    # Simulate the broker inspecting another branch before requesting recovery.
    quality._active_revision_id = "R0"

    with pytest.raises(ValueError, match="validated passing improved"):
        quality.recover_revision("R1")


def test_patch_must_cover_finding_dependency_closure() -> None:
    quality = _session()
    quality.record_findings(
        (
            _finding("logic-root"),
            _finding("logic-child", depends_on=("logic-root",)),
        )
    )

    with pytest.raises(ValueError, match="dependency closure"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, RIGHT)",
            new_text="Line(LEFT, UP)",
            finding_ids=("logic-child",),
        )

    revision = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-root", "logic-child"),
    )
    assert revision.finding_ids == ("logic-root", "logic-child")


def test_patch_must_cover_findings_with_the_same_precise_root() -> None:
    quality = _session()
    point = _finding(
        "logic-point",
        affected_symbols=("root:point_D", "point:D"),
    )
    line = _finding(
        "logic-line",
        affected_symbols=("root:point_D", "line:BD"),
    )
    quality.record_findings((point, line))

    with pytest.raises(ValueError, match="affected-symbol closure"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, RIGHT)",
            new_text="Line(LEFT, UP)",
            finding_ids=("logic-point",),
        )

    revision = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-point", "logic-line"),
    )
    assert revision.finding_ids == ("logic-point", "logic-line")


def test_finding_dependency_cycle_is_rejected() -> None:
    quality = _session()
    with pytest.raises(ValueError, match="cycle"):
        quality.record_findings(
            (
                _finding("logic-a", depends_on=("logic-b",)),
                _finding("logic-b", depends_on=("logic-a",)),
            )
        )


def test_cross_category_dependency_uses_validated_prior_repair() -> None:
    quality = _session()
    quality.record_findings(
        (
            _finding("logic-root"),
            _finding(
                "layout-child",
                depends_on=("logic-root",),
                category=FindingCategory.LAYOUT,
            ),
        )
    )
    logic = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-root",),
    )
    quality.record_validation(
        revision_id=logic.revision_id,
        passed=True,
        improved=True,
        fingerprint="sha256:" + "4" * 64,
    )
    quality.mark_solution_read(logic.revision_id)

    layout = quality.apply_patch(
        scope=PatchScope.LAYOUT,
        old_text="self.add(line)",
        new_text="self.add(line.shift(UP))",
        finding_ids=("layout-child",),
    )

    assert layout.parent_revision_id == "R1"


def test_failed_branch_finding_reference_is_not_resolved() -> None:
    quality = _session()
    quality.record_findings((_finding("logic-1"),))
    revision = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=revision.revision_id,
        passed=False,
        improved=False,
        fingerprint="sha256:" + "5" * 64,
    )
    quality.record_layout_inspection(
        revision_id=revision.revision_id,
        fingerprint="sha256:" + "6" * 64,
    )

    with pytest.raises(RuntimeError, match="pass validation"):
        quality.submit(revision.revision_id)


def test_recovery_rejects_passing_but_non_improving_revision() -> None:
    quality = _session()
    quality.record_findings((_finding("logic-1"),))
    first = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=first.revision_id,
        passed=True,
        improved=False,
        fingerprint="sha256:" + "7" * 64,
    )
    quality._active_revision_id = "R0"

    with pytest.raises(ValueError, match="improved"):
        quality.recover_revision("R1")


def test_abandoned_layout_branch_does_not_block_logic_repair() -> None:
    quality = _session()
    quality.record_findings(
        (
            _finding("logic-1"),
            _finding("layout-1", category=FindingCategory.LAYOUT),
        )
    )
    logic = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id=logic.revision_id,
        passed=True,
        improved=True,
        fingerprint="sha256:" + "8" * 64,
    )
    quality.mark_solution_read("R1")
    layout = quality.apply_patch(
        scope=PatchScope.LAYOUT,
        old_text="self.add(line)",
        new_text="self.add(line.shift(UP))",
        finding_ids=("layout-1",),
    )
    quality.record_validation(
        revision_id=layout.revision_id,
        passed=False,
        improved=False,
        fingerprint="sha256:" + "9" * 64,
    )

    quality.recover_revision("R1")
    quality.mark_solution_read("R1")
    replacement = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, 2 * RIGHT)",
        new_text="Line(LEFT, 4 * RIGHT)",
        finding_ids=("logic-1",),
    )

    assert replacement.revision_id == "R3"
    assert replacement.parent_revision_id == "R1"
