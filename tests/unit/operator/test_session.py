import pytest

from manim_quality.operator.models import Finding, FindingCategory, PatchScope
from manim_quality.operator.session import QualitySession
from manim_quality.operator.session_errors import (
    DuplicatePatch,
    InvalidSessionTransition,
    ProblemLockViolation,
    ScopeViolation,
)
from manim_quality.operator.source_view import SolutionSourceError

PROBLEM = "Problem: prove AB is parallel to CD."
BASELINE = f'''from manim import *

class Solution(BaseConfigScene):
    """{PROBLEM}"""

    def construct(self):
        line = Line(LEFT, RIGHT)
        self.add(line)
'''


def finding(
    finding_id: str = "logic-1",
    category: FindingCategory = FindingCategory.LOGIC,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        category=category,
        severity="blocking",
        summary="The constructed relation contradicts the stated proof.",
        acceptance_criteria="The rendered relation matches the locked problem.",
    )


def session() -> QualitySession:
    quality = QualitySession(problem_text=PROBLEM, candidate_code=BASELINE)
    quality.mark_solution_read("R0")
    return quality


def test_session_preserves_immutable_problem_and_r0() -> None:
    quality = session()

    assert quality.problem_text == PROBLEM
    assert quality.baseline.code == BASELINE
    assert quality.current_revision.revision_id == "R0"
    assert quality.problem_hash.startswith("sha256:")
    assert quality.baseline.code_hash.startswith("sha256:")


def test_patch_requires_frozen_findings() -> None:
    quality = session()

    with pytest.raises(InvalidSessionTransition, match="findings"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, RIGHT)",
            new_text="Line(LEFT, UP)",
            finding_ids=("logic-1",),
        )


def test_problem_text_cannot_be_changed_by_patch() -> None:
    quality = session()
    quality.record_findings((finding(),))

    with pytest.raises(ProblemLockViolation):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text=PROBLEM,
            new_text="Problem: prove AB is perpendicular to CD.",
            finding_ids=("logic-1",),
        )


def test_logic_and_layout_are_separate_validated_candidate_attempts() -> None:
    quality = session()
    quality.record_findings(
        (
            finding(),
            finding("layout-1", FindingCategory.LAYOUT),
        )
    )

    logic = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    assert logic.revision_id == "R1"
    assert logic.parent_revision_id == "R0"
    assert logic.scope is PatchScope.LOGIC

    with pytest.raises(InvalidSessionTransition, match="validated"):
        quality.apply_patch(
            scope=PatchScope.LAYOUT,
            old_text="self.add(line)",
            new_text="self.add(line.shift(UP))",
            finding_ids=("layout-1",),
        )

    quality.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "1" * 64,
    )
    quality.mark_solution_read("R1")
    layout = quality.apply_patch(
        scope=PatchScope.LAYOUT,
        old_text="self.add(line)",
        new_text="self.add(line.shift(UP))",
        finding_ids=("layout-1",),
    )

    assert layout.revision_id == "R2"
    assert layout.parent_revision_id == "R1"
    assert layout.scope is PatchScope.LAYOUT
    assert quality.baseline.code == BASELINE


def test_logic_patch_is_forbidden_after_layout_patch() -> None:
    quality = session()
    quality.record_findings(
        (
            finding(),
            finding("layout-1", FindingCategory.LAYOUT),
        )
    )
    quality.apply_patch(
        scope=PatchScope.LAYOUT,
        old_text="self.add(line)",
        new_text="self.add(line.shift(UP))",
        finding_ids=("layout-1",),
    )
    quality.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "2" * 64,
    )

    with pytest.raises(InvalidSessionTransition, match="after layout"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, RIGHT)",
            new_text="Line(LEFT, UP)",
            finding_ids=("logic-1",),
        )


def test_duplicate_patch_and_non_improving_retry_are_stopped() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id="R1",
        passed=False,
        improved=False,
        fingerprint="sha256:" + "3" * 64,
    )

    with pytest.raises(InvalidSessionTransition, match="did not improve"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, UP)",
            new_text="Line(LEFT, RIGHT)",
            finding_ids=("logic-1",),
        )

    duplicate = session()
    duplicate.record_findings((finding(),))
    duplicate.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    duplicate.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "4" * 64,
    )
    duplicate.mark_solution_read("R1")
    with pytest.raises(DuplicatePatch):
        duplicate.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="Line(LEFT, UP)",
            new_text="Line(LEFT, RIGHT)",
            finding_ids=("logic-1",),
        )


def test_submit_requires_latest_revision_validation() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    quality.mark_solution_read("R1")

    with pytest.raises(InvalidSessionTransition, match="validated"):
        quality.submit("R1")

    quality.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "5" * 64,
    )
    with pytest.raises(InvalidSessionTransition, match="layout"):
        quality.submit("R1")

    quality.record_layout_inspection(
        revision_id="R1",
        fingerprint="sha256:" + "6" * 64,
    )
    submitted = quality.submit("R1")

    assert submitted.revision_id == "R1"
    assert quality.submitted_revision_id == "R1"


def test_findings_can_be_added_in_logic_then_layout_batches() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.mark_solution_read("R1")

    with pytest.raises(InvalidSessionTransition, match="validated"):
        quality.record_findings(
            (finding("layout-1", FindingCategory.LAYOUT),)
        )

    quality.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "7" * 64,
    )
    quality.record_findings(
        (finding("layout-1", FindingCategory.LAYOUT),)
    )

    assert [item.finding_id for item in quality.findings] == [
        "logic-1",
        "layout-1",
    ]


def test_submit_rejects_failed_validation_and_blocking_layout() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, UP)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id="R1",
        passed=False,
        improved=True,
        fingerprint="sha256:" + "8" * 64,
    )
    quality.record_layout_inspection(
        revision_id="R1",
        fingerprint="sha256:" + "9" * 64,
        blocking_count=0,
    )

    with pytest.raises(InvalidSessionTransition, match="pass validation"):
        quality.submit("R1")

    blocked = session()
    blocked.record_findings(())
    blocked.record_layout_inspection(
        revision_id="R0",
        fingerprint="sha256:" + "a" * 64,
        blocking_count=1,
    )
    with pytest.raises(InvalidSessionTransition, match="blocking layout"):
        blocked.submit("R0")


def test_layout_patch_cannot_change_semantic_invariant() -> None:
    quality = session()
    quality.record_findings(
        (finding("layout-1", FindingCategory.LAYOUT),)
    )

    with pytest.raises(ScopeViolation, match="semantic"):
        quality.apply_patch(
            scope=PatchScope.LAYOUT,
            old_text="Line(LEFT, RIGHT)",
            new_text="Line(LEFT, UP)",
            finding_ids=("layout-1",),
        )

    assert quality.current_revision.revision_id == "R0"


def test_findings_require_current_solution_read() -> None:
    quality = QualitySession(problem_text=PROBLEM, candidate_code=BASELINE)

    with pytest.raises(InvalidSessionTransition, match="read_solution"):
        quality.record_findings(())
    quality.mark_solution_read("R0")
    quality.record_findings(())


def test_r0_submission_rejects_unrepaired_blocking_finding() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.record_layout_inspection(
        revision_id="R0",
        fingerprint="sha256:" + "b" * 64,
        blocking_count=0,
    )

    with pytest.raises(InvalidSessionTransition, match="blocking findings"):
        quality.submit("R0")


def test_leading_comment_problem_source_is_outside_patch_boundary() -> None:
    candidate = (
        "# Problem: prove AB is parallel to CD.\n"
        "# Solution: compare corresponding angles.\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        self.wait()\n"
    )
    problem = (
        "Problem: prove AB is parallel to CD.\n"
        "Solution: compare corresponding angles."
    )
    quality = QualitySession(problem_text=problem, candidate_code=candidate)
    quality.mark_solution_read("R0")
    quality.record_findings((finding(),))

    with pytest.raises(SolutionSourceError, match="inside Solution"):
        quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text="parallel to CD",
            new_text="perpendicular to CD",
            finding_ids=("logic-1",),
        )


def test_best_validated_revision_prefers_lowest_blocking_count() -> None:
    quality = session()
    quality.record_findings(
        (
            finding(),
            finding("layout-1", FindingCategory.LAYOUT),
        )
    )
    assert quality.best_validated_revision_id() is None

    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "1" * 64,
    )
    quality.record_layout_inspection(
        revision_id="R1",
        fingerprint="sha256:" + "2" * 64,
        blocking_count=2,
    )
    quality.mark_solution_read("R1")
    quality.apply_patch(
        scope=PatchScope.LAYOUT,
        old_text="self.add(line)",
        new_text="self.add(line.shift(UP))",
        finding_ids=("layout-1",),
    )
    quality.record_validation(
        revision_id="R2",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "3" * 64,
    )
    quality.record_layout_inspection(
        revision_id="R2",
        fingerprint="sha256:" + "4" * 64,
        blocking_count=5,
    )

    assert quality.best_validated_revision_id() == "R1"


def test_best_validated_revision_ignores_failed_validation() -> None:
    quality = session()
    quality.record_findings((finding(),))
    quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    quality.record_validation(
        revision_id="R1",
        passed=False,
        improved=False,
        fingerprint="sha256:" + "1" * 64,
    )

    assert quality.best_validated_revision_id() is None


def test_patch_budget_can_only_be_raised_before_findings() -> None:
    quality = session()
    quality.raise_patch_budget(7)
    assert quality.max_patch_attempts == 7
    assert quality.patches_remaining == 7

    with pytest.raises(InvalidSessionTransition, match="raised"):
        quality.raise_patch_budget(6)

    quality.record_findings((finding(),))
    with pytest.raises(InvalidSessionTransition, match="frozen"):
        quality.raise_patch_budget(8)


def test_patch_budget_for_blocking_maps_pressure_to_budget() -> None:
    from manim_quality.operator.session_rules import patch_budget_for_blocking

    assert patch_budget_for_blocking(0) == 5
    assert patch_budget_for_blocking(2) == 5
    assert patch_budget_for_blocking(3) == 6
    assert patch_budget_for_blocking(8) == 6
    assert patch_budget_for_blocking(9) == 7
    assert patch_budget_for_blocking(36) == 7
