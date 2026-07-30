from manim_quality.feedback_loop.models import AssuranceOutcome, Candidate
from manim_quality.feedback_loop.runner import FeedbackLoopRunner
from manim_quality.feedback_loop.store import JsonLoopStore


class FakeCoder:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def repair(self, candidate, issues, repair_round):
        self.calls.append((candidate, issues, repair_round))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeAssurance:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def review(self, candidate, assurance_pass):
        self.calls.append((candidate, assurance_pass))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def candidate(revision):
    return Candidate(
        revision_id=revision,
        source_sha256=f"source-{revision}",
        video_sha256=f"video-{revision}",
        source_path=f"/tmp/{revision}.py",
        video_path=f"/tmp/{revision}.mp4",
    )


def assurance(grade, issue="wrong proof"):
    issues = () if grade in {"A", "B"} else ({
        "category": "mathematical_proof",
        "severity": "high",
        "summary": issue,
        "evidence_ids": ["reviewer:math_geometry_reviewer"],
    },)
    return AssuranceOutcome(grade=grade, status="review", issues=issues)


def run(tmp_path, grades, repairs=()):
    coder = FakeCoder(repairs)
    reviewer = FakeAssurance([assurance(grade) for grade in grades])
    runner = FeedbackLoopRunner(
        coder=coder,
        assurance=reviewer,
        store=JsonLoopStore(tmp_path / "loop.json"),
    )
    return runner.run(candidate("R0")), coder, reviewer


def test_a_or_b_finishes_without_repair(tmp_path):
    result, coder, reviewer = run(tmp_path, ["B"])

    assert result.terminal_reason == "accepted_grade"
    assert result.final_grade == "B"
    assert result.assurance_passes == 1
    assert not coder.calls
    assert len(reviewer.calls) == 1


def test_c_repairs_and_rechecks_until_a(tmp_path):
    result, coder, reviewer = run(
        tmp_path, ["C", "A"], [candidate("R1")]
    )

    assert result.final_candidate.revision_id == "R1"
    assert result.final_grade == "A"
    assert result.assurance_passes == 2
    assert result.repair_rounds == 1
    assert coder.calls[0][1][0]["issue_id"].startswith("fa-")


def test_d_stops_after_three_assurance_passes_and_keeps_best(tmp_path):
    result, coder, reviewer = run(
        tmp_path,
        ["D", "C", "D"],
        [candidate("R1"), candidate("R2")],
    )

    assert result.terminal_reason == "assurance_budget_exhausted"
    assert result.assurance_passes == 3
    assert result.repair_rounds == 2
    assert result.final_grade == "C"
    assert result.final_candidate.revision_id == "R1"


def test_tts_issue_is_not_returned_when_tts_is_disabled(tmp_path):
    outcome = AssuranceOutcome(
        grade="C",
        status="review",
        issues=({
            "category": "tts_sync",
            "severity": "high",
            "summary": "audio mismatch",
            "evidence_ids": ["inspect_tts:1"],
        },),
    )
    coder = FakeCoder([])
    reviewer = FakeAssurance([outcome])
    runner = FeedbackLoopRunner(
        coder=coder,
        assurance=reviewer,
        store=JsonLoopStore(tmp_path / "loop.json"),
        tts_mode="disabled",
    )

    result = runner.run(candidate("R0"))

    assert result.terminal_reason == "no_repairable_issues"
    assert not coder.calls


def test_coder_failure_keeps_last_playable_candidate(tmp_path):
    result, _, _ = run(tmp_path, ["D"], [RuntimeError("coder down")])

    assert result.terminal_reason == "coder_error"
    assert result.final_candidate.revision_id == "R0"
    assert result.final_grade == "D"


def test_resume_does_not_repeat_completed_assurance_pass(tmp_path):
    path = tmp_path / "loop.json"
    first = FeedbackLoopRunner(
        coder=FakeCoder([candidate("R1")]),
        assurance=FakeAssurance([assurance("C"), RuntimeError("stop")]),
        store=JsonLoopStore(path),
    ).run(candidate("R0"))
    assert first.terminal_reason == "assurance_error"

    coder = FakeCoder([])
    reviewer = FakeAssurance([assurance("A")])
    result = FeedbackLoopRunner(
        coder=coder,
        assurance=reviewer,
        store=JsonLoopStore(path),
    ).run(candidate("R0"), resume=True)

    assert reviewer.calls[0][0].revision_id == "R1"
    assert reviewer.calls[0][1] == 2
    assert result.final_grade == "A"
