from manim_quality.feedback_loop.grading import grade_assurance_row


def row(status="pass", issues=(), error=None):
    value = {"agent": {"status": status, "issues": list(issues)}}
    if error:
        value = {"agent_error": error}
    return value


def test_grades_clean_warning_medium_and_blocking():
    assert grade_assurance_row(row()) == "A"
    assert grade_assurance_row(
        row("review", [{"severity": "warning"}])
    ) == "B"
    assert grade_assurance_row(
        row("review", [{"severity": "medium"}])
    ) == "C"
    assert grade_assurance_row(
        row("review", [{"severity": "blocking"}])
    ) == "D"


def test_incomplete_or_agent_error_is_e():
    assert grade_assurance_row(row("incomplete")) == "E"
    assert grade_assurance_row(row(error="runtime unavailable")) == "E"
