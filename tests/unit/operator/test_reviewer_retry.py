from types import SimpleNamespace

from manim_quality.operator.reviewers import run_reviewers


def _outcome(*, read: bool):
    tool_calls = (
        (SimpleNamespace(allowed=True, name="Read"),) if read else ()
    )
    record = SimpleNamespace(
        tool_calls=tool_calls,
        usage=SimpleNamespace(total_tokens=0),
        usage_complete=True,
        model="test-model",
        elapsed_ms=1,
        turns=1,
    )
    return SimpleNamespace(
        record=record,
        structured_output={
            "decision": "pass",
            "diagnosis": "ok",
            "issues": [],
            "coverage": {},
            "confidence": 1.0,
        },
    )


class Runtime:
    def __init__(self):
        self.requests = []
        self.outcomes = iter((
            _outcome(read=False),
            _outcome(read=True),
            _outcome(read=True),
        ))

    def run(self, request):
        self.requests.append(request)
        return next(self.outcomes)


def test_reviewer_retries_once_after_missing_native_read(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    runtime = Runtime()

    reviewers, records = run_reviewers(
        runtime,
        candidate_path=candidate,
        problem_text="求解。",
        model="test-model",
    )

    assert len(reviewers) == 2
    assert len(records) == 2
    assert len(runtime.requests) == 3
    assert runtime.requests[1].run_id.endswith("-native-read-retry")
    assert "PROTOCOL REPAIR" in runtime.requests[1].prompt
