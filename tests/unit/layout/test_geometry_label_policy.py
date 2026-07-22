from dataclasses import dataclass, field

from manim_quality.layout.classification import ImpactClassifyingChecker


@dataclass
class Check:
    ok: bool = True
    passed: bool = False
    blocking_count: int = 1
    issues: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class Checker:
    def __init__(self, result: Check) -> None:
        self.result = result

    def run_check(self, code_path, workdir):
        del code_path, workdir
        return self.result


def test_single_character_vertex_label_is_record_only(tmp_path) -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "occurrence_count": 12,
        "a_raw": {"class": "Circle", "kind": "shape"},
        "b_raw": {"class": "MathTex", "kind": "formula", "text": "A"},
    }
    checker = ImpactClassifyingChecker(Checker(Check(issues=[issue])))

    result = checker.run_check(tmp_path / "candidate.py", tmp_path)

    assert result.passed is True
    assert result.blocking_count == 0
    assert result.raw["platform_warnings"][0]["reason"] == (
        "single_character_geometry_label"
    )
