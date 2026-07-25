from dataclasses import dataclass, field
from pathlib import Path

from manim_quality.layout.classification import ImpactClassifyingChecker


@dataclass
class Check:
    ok: bool
    passed: bool
    blocking_count: int
    issues: list[dict]
    raw: dict = field(default_factory=dict)
    error: str | None = None


class Checker:
    def __init__(self, result: Check) -> None:
        self._result = result

    def run_check(self, code_path: Path, workdir: Path) -> Check:
        del code_path, workdir
        return self._result


def _issue(label_bbox: dict[str, float]) -> dict:
    return {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "a_raw": {
            "class": "Polygon",
            "kind": "shape",
            "bbox": {
                "left": -1.0,
                "right": 1.0,
                "top": 1.0,
                "bottom": -1.0,
                "width": 2.0,
                "height": 2.0,
                "center_x": 0.0,
                "center_y": 0.0,
            },
        },
        "b_raw": {
            "class": "MathTex",
            "kind": "formula",
            "text": "a^2",
            "bbox": label_bbox,
        },
    }


def test_centered_contained_geometry_label_is_record_only(tmp_path: Path) -> None:
    issue = _issue(
        {
            "left": -0.2,
            "right": 0.2,
            "top": 0.2,
            "bottom": -0.2,
            "width": 0.4,
            "height": 0.4,
            "center_x": 0.0,
            "center_y": 0.0,
        }
    )
    checker = ImpactClassifyingChecker(
        Checker(Check(ok=True, passed=False, blocking_count=1, issues=[issue]))
    )

    result = checker.run_check(tmp_path / "candidate.py", tmp_path)

    assert result.passed is True
    assert result.blocking_count == 0
    assert result.issues == []
    assert result.raw["platform_warning_count"] == 1
    assert (tmp_path / "platform_overlap_classification.json").is_file()


def test_edge_crossing_geometry_label_remains_blocking(tmp_path: Path) -> None:
    issue = _issue(
        {
            "left": 0.8,
            "right": 1.2,
            "top": 0.2,
            "bottom": -0.2,
            "width": 0.4,
            "height": 0.4,
            "center_x": 1.0,
            "center_y": 0.0,
        }
    )
    checker = ImpactClassifyingChecker(
        Checker(Check(ok=True, passed=False, blocking_count=1, issues=[issue]))
    )

    result = checker.run_check(tmp_path / "candidate.py", tmp_path)

    assert result.passed is False
    assert result.blocking_count == 1
    assert result.issues == [issue]
    assert result.raw["platform_warning_count"] == 0


def test_centered_long_content_remains_blocking(tmp_path: Path) -> None:
    issue = _issue(
        {
            "left": -0.8,
            "right": 0.8,
            "top": 0.2,
            "bottom": -0.2,
            "width": 1.6,
            "height": 0.4,
            "center_x": 0.0,
            "center_y": 0.0,
        }
    )
    issue["b_raw"]["text"] = "This is explanatory content"
    checker = ImpactClassifyingChecker(
        Checker(Check(ok=True, passed=False, blocking_count=1, issues=[issue]))
    )

    result = checker.run_check(tmp_path / "candidate.py", tmp_path)

    assert result.blocking_count == 1
    assert result.raw["platform_warning_count"] == 0


def test_centered_short_label_crossing_shape_edge_remains_blocking(
    tmp_path: Path,
) -> None:
    issue = _issue(
        {
            "left": -1.01,
            "right": 1.01,
            "top": 0.2,
            "bottom": -0.2,
            "width": 2.02,
            "height": 0.4,
            "center_x": 0.0,
            "center_y": 0.0,
        }
    )
    checker = ImpactClassifyingChecker(
        Checker(Check(ok=True, passed=False, blocking_count=1, issues=[issue]))
    )

    result = checker.run_check(tmp_path / "candidate.py", tmp_path)

    assert result.blocking_count == 1
    assert result.raw["platform_warning_count"] == 0
