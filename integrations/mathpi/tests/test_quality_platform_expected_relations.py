from __future__ import annotations

import sys
from pathlib import Path


PLATFORM_SOURCE = Path(__file__).resolve().parents[1] / "manim_quality_platform" / "src"
if str(PLATFORM_SOURCE) not in sys.path:
    sys.path.insert(0, str(PLATFORM_SOURCE))

from manim_quality.logic.expectations.comparison import (  # noqa: E402
    ComparisonStatus,
    compare_expected_relations,
)
from manim_quality.logic.expectations.schemas import (  # noqa: E402
    ExpectedRelationClaim,
    ExpectedRelationContract,
    SCHEMA_VERSION,
)
from manim_quality.logic.expectations.symbolic_index import (  # noqa: E402
    build_symbolic_index,
)


def test_compact_point_prefix_matches_semantic_line_endpoints() -> None:
    code = """from manim import *

class Solution(Scene):
    def construct(self):
        pB = [-2, 0, 0]
        pD = [2, 0, 0]
        line_BD = Line(pB, pD)
        self.add(line_BD)
"""
    claim = ExpectedRelationClaim(
        "R-BD",
        "line_endpoints",
        ("BD", "B", "D"),
        "problem",
        "矩形 ABCD 的对角线 BD",
        "derived",
    )
    contract = ExpectedRelationContract(SCHEMA_VERSION, (claim,))

    result = compare_expected_relations(
        contract,
        build_symbolic_index(code, scene_id="Solution"),
    )

    assert result[0].status is ComparisonStatus.SATISFIED
