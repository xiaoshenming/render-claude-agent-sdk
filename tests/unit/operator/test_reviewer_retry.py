import threading
import time
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
            _outcome(read=True),
        ))

    def run(self, request):
        self.requests.append(request)
        return next(self.outcomes)


class VisualFailureRuntime(Runtime):
    def run(self, request):
        self.requests.append(request)
        if request.run_id.startswith("visual_layout_reviewer"):
            raise RuntimeError("visual provider unavailable")
        return next(self.outcomes)


class ParallelRuntime:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def run(self, _request):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            return _outcome(read=True)
        finally:
            with self.lock:
                self.active -= 1


def test_reviewers_run_in_parallel_and_keep_declared_order(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    runtime = ParallelRuntime()

    reviewers, records = run_reviewers(
        runtime, candidate_path=candidate,
        problem_text="求解。", model="test-model",
    )

    assert runtime.max_active == 3
    assert [row["agent_type"] for row in reviewers] == [
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
    ]
    assert len(records) == 3


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

    assert len(reviewers) == 3
    assert len(records) == 3
    assert len(runtime.requests) == 4
    assert [row["agent_type"] for row in reviewers] == [
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
    ]
    assert runtime.requests[1].run_id.endswith("-native-read-retry")
    assert "PROTOCOL REPAIR" in runtime.requests[1].prompt


def test_visual_reviewer_failure_is_recorded_without_blocking(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    runtime = VisualFailureRuntime()

    reviewers, records = run_reviewers(
        runtime,
        candidate_path=candidate,
        problem_text="求解。",
        model="test-model",
    )

    assert len(records) == 2
    assert reviewers[-1]["agent_type"] == "visual_layout_reviewer"
    assert reviewers[-1]["is_error"] is True
    assert reviewers[-1]["payload"] is None
