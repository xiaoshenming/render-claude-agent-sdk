from manim_quality.operator.models import Finding, FindingCategory, PatchScope
from manim_quality.operator.session import QualitySession

PROBLEM = "Problem: prove AB is parallel to CD."
BASELINE = f'''from manim import *

class Solution(BaseConfigScene):
    """{PROBLEM}"""

    def construct(self):
        line = Line(LEFT, RIGHT)
        self.add(line)
'''


def test_third_patch_is_available_after_two_improving_validations() -> None:
    quality = QualitySession(problem_text=PROBLEM, candidate_code=BASELINE)
    quality.mark_solution_read("R0")
    quality.record_findings(
        (
            Finding(
                finding_id="logic-1",
                category=FindingCategory.LOGIC,
                severity="blocking",
                summary="Three related construction defects remain.",
                acceptance_criteria="All three defects are repaired.",
            ),
        )
    )

    old_text = "Line(LEFT, RIGHT)"
    for index, new_text in enumerate(
        ("Line(LEFT, 2 * RIGHT)", "Line(LEFT, 3 * RIGHT)"),
        start=1,
    ):
        revision = quality.apply_patch(
            scope=PatchScope.LOGIC,
            old_text=old_text,
            new_text=new_text,
            finding_ids=("logic-1",),
        )
        quality.record_validation(
            revision_id=revision.revision_id,
            passed=True,
            improved=True,
            fingerprint="sha256:" + str(index) * 64,
        )
        quality.mark_solution_read(revision.revision_id)
        old_text = new_text

    revision = quality.apply_patch(
        scope=PatchScope.LOGIC,
        old_text=old_text,
        new_text="Line(LEFT, 4 * RIGHT)",
        finding_ids=("logic-1",),
    )

    assert revision.revision_id == "R3"
