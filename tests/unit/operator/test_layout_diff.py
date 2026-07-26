from manim_quality.operator.runtime_tools.layout_diff import compare_layout_reports


def issue(issue_id: str, path: str, step: int) -> dict[str, object]:
    return {
        "issue_id": issue_id,
        "category": "overlap",
        "objects": [{"path": path}],
        "phase": {"step": step, "event": "play"},
    }


def test_layout_diff_reports_progress_regressions_and_shared_roots() -> None:
    baseline = {
        "blocking_count": 3,
        "issues": [issue("a", "panel", 1), issue("b", "panel", 2), issue("c", "old", 3)],
    }
    current = {
        "blocking_count": 2,
        "issues": [issue("a2", "panel", 1), issue("d", "panel", 4)],
    }

    result = compare_layout_reports(baseline, current)

    assert result["before"] == 3
    assert result["after"] == 2
    assert result["resolved_count"] == 2
    assert result["persistent_count"] == 1
    assert result["introduced_count"] == 1
    assert result["shared_roots"][0]["root"] == "object:panel"
