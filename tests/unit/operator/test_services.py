import anyio
import pytest

from manim_quality.operator.models import CandidateAttempt
from manim_quality.operator.problem_source import extract_problem_text
from manim_quality.operator.services import (
    BasicRelationChecker,
    CompileOnlyValidator,
    UnverifiedLayoutInspector,
)
from manim_quality.operator.session import QualitySession


@pytest.mark.parametrize(
    ("relation", "operands", "expected"),
    [
        ("numeric_equal", [0.5, 1 / 2], True),
        ("parallel", [[1, 0], [3, 0]], True),
        ("perpendicular", [[1, 0], [0, 2]], True),
        ("collinear", [[0, 0], [1, 1], [2, 2]], True),
        ("midpoint", [[1, 1], [0, 0], [2, 2]], True),
    ],
)
def test_basic_relation_checker_returns_deterministic_facts(
    relation, operands, expected
) -> None:
    result = anyio.run(
        BasicRelationChecker().check,
        {"relation": relation, "operands": operands, "expected": expected},
    )

    assert result["holds"] is expected
    assert result["verified"] is True


def test_problem_source_prefers_module_docstring_then_leading_comments() -> None:
    assert extract_problem_text('"""Prove AB = CD."""\nclass Scene:\n    pass\n') == (
        "Prove AB = CD."
    )
    assert extract_problem_text(
        "# Problem: prove AB = CD.\n# Solution: use congruence.\nimport math\n"
    ) == "Problem: prove AB = CD.\nSolution: use congruence."


def test_problem_source_rejects_code_without_locked_statement() -> None:
    with pytest.raises(ValueError, match="problem"):
        extract_problem_text("import math\n")


def test_smoke_services_never_claim_full_acceptance() -> None:
    session = QualitySession(
        problem_text="Construct a line.",
        candidate_code=(
            "class Solution(BaseConfigScene):\n"
            "    def construct(self):\n"
            "        pass\n"
        ),
    )
    revision: CandidateAttempt = session.baseline

    validation = anyio.run(
        CompileOnlyValidator().validate,
        revision,
        (),
        session.problem_hash,
    )
    layout = anyio.run(
        UnverifiedLayoutInspector().inspect,
        revision,
        session.problem_hash,
    )

    assert validation.passed is True
    assert validation.details["rendered"] is False
    assert layout["verified"] is False
