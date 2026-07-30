import threading
import time
from pathlib import Path

import anyio
import pytest

from manim_quality.operator.models import CandidateAttempt
from manim_quality.operator.problem_source import extract_problem_text
from manim_quality.operator.runtime_tools.models import ProbeResult, RenderResult
from manim_quality.operator.runtime_tools.services import (
    RealLayoutInspector,
    RealRevisionValidator,
    RuntimeToolchain,
    _render_diagnostic,
)
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
    assert (
        extract_problem_text(
            "# Problem: prove AB = CD.\n# Solution: use congruence.\nimport math\n"
        )
        == "Problem: prove AB = CD.\nSolution: use congruence."
    )


def test_problem_source_rejects_code_without_locked_statement() -> None:
    with pytest.raises(ValueError, match="problem"):
        extract_problem_text("import math\n")


def test_render_diagnostic_returns_bounded_actionable_tail(tmp_path: Path) -> None:
    stderr = tmp_path / "render.stderr.log"
    stderr.write_text(
        ("unhelpful prelude\n" * 200)
        + "candidate.py:1565 in make_ctex_row\n"
        + "ValueError: xelatex error converting to xdv\n",
        encoding="utf-8",
    )

    diagnostic = _render_diagnostic(tmp_path)

    assert "candidate.py:1565" in diagnostic["stderr_tail"]
    assert "xelatex error" in diagnostic["stderr_tail"]
    assert len(diagnostic["stderr_tail"]) <= 6_000
    assert diagnostic["truncated"] is True


def test_smoke_services_never_claim_full_acceptance() -> None:
    session = QualitySession(
        problem_text="Construct a line.",
        candidate_code=(
            "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n"
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


class _CountingRenderer:
    """Records every render so a duplicate within one round is visible."""

    def __init__(self, video_path: Path) -> None:
        self.calls = 0
        self._video_path = video_path

    def render(self, revision_dir: Path, candidate: Path) -> RenderResult:
        self.calls += 1
        time.sleep(0.05)
        return RenderResult(
            ok=True,
            revision_dir=revision_dir,
            candidate_path=candidate,
            video_path=self._video_path,
            duration_seconds=1.0,
            error=None,
        )


class _StubProbe:
    def inspect(self, revision_dir: Path, candidate_path: Path) -> ProbeResult:
        del candidate_path
        return ProbeResult(
            ok=True,
            raw_path=revision_dir / "bbox_probe.json",
            payload={},
            error=None,
        )


class _StubDetector:
    def detect(
        self, payload: dict[str, object], *, artifact_path: Path
    ) -> dict[str, object]:
        del payload, artifact_path
        return {"issues": [], "blocking_count": 0}


def _toolchain(tmp_path: Path) -> RuntimeToolchain:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = tmp_path / "probe_runner.py"
    runner.touch()
    interpreter = tmp_path / "python"
    interpreter.touch()
    return RuntimeToolchain(
        source_workspace=workspace,
        artifact_root=tmp_path / "artifacts",
        probe_runner=runner,
        python_executable=interpreter,
    )


def _record_entry_threads(
    toolchain: RuntimeToolchain, monkeypatch: pytest.MonkeyPatch
) -> set[int]:
    """Capture which worker thread enters each public toolchain entry point."""
    threads: set[int] = set()
    for name in ("render", "probe"):
        original = getattr(toolchain, name)

        def recorder(revision: CandidateAttempt, _original=original):
            threads.add(threading.get_ident())
            return _original(revision)

        monkeypatch.setattr(toolchain, name, recorder)
    return threads


def test_concurrent_validate_and_inspect_render_revision_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    toolchain = _toolchain(tmp_path)
    renderer = _CountingRenderer(tmp_path / "video.mp4")
    monkeypatch.setattr(toolchain, "_renderer", renderer)
    monkeypatch.setattr(toolchain, "_probe", _StubProbe())
    monkeypatch.setattr(toolchain, "_detector", _StubDetector())
    entry_threads = _record_entry_threads(toolchain, monkeypatch)

    session = QualitySession(
        problem_text="Construct a line.",
        candidate_code=(
            "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n"
        ),
    )
    revision: CandidateAttempt = session.baseline
    results: dict[str, object] = {}

    async def scenario() -> None:
        async def run_validate() -> None:
            results["validation"] = await RealRevisionValidator(toolchain).validate(
                revision, (), session.problem_hash
            )

        async def run_inspect() -> None:
            results["layout"] = await RealLayoutInspector(toolchain).inspect(
                revision, session.problem_hash
            )

        async with anyio.create_task_group() as group:
            group.start_soon(run_validate)
            group.start_soon(run_inspect)

    anyio.run(scenario)

    assert renderer.calls == 1
    assert results["validation"].passed is True
    assert results["layout"]["verified"] is True
    assert results["layout"]["blocking_count"] == 0
    # Two distinct worker threads prove the tools really overlapped, so the
    # single render is the lock plus cache, not accidental serialization.
    assert len(entry_threads) == 2


def test_in_session_verification_facts_survive_on_disk(tmp_path) -> None:
    """Session death must not erase already-computed evidence."""
    import json

    toolchain = _toolchain(tmp_path)
    toolchain._renderer = _CountingRenderer(tmp_path / "video.mp4")
    toolchain._probe = _StubProbe()
    toolchain._detector = _StubDetector()
    session = QualitySession(
        problem_text="Construct a line.",
        candidate_code=(
            "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n"
        ),
    )
    revision = session.baseline
    validator = RealRevisionValidator(toolchain)
    inspector = RealLayoutInspector(toolchain)

    async def scenario() -> None:
        await validator.validate(revision, (), "sha256:" + "0" * 64)
        await inspector.inspect(revision, "sha256:" + "0" * 64)
        await inspector.inspect(revision, "sha256:" + "0" * 64)

    anyio.run(scenario)

    reports = sorted(p.name for p in toolchain.reports_dir.glob("*.json"))
    assert any(name.startswith("validation.R0.") for name in reports)
    layout_reports = [n for n in reports if n.startswith("layout.R0.")]
    assert len(layout_reports) == 2
    payload = json.loads((toolchain.reports_dir / layout_reports[0]).read_text())
    assert payload["revision_id"] == "R0"
    assert "blocking_count" in payload


def test_check_relation_covers_reviewer_needed_relations() -> None:
    from manim_quality.operator.services import BasicRelationChecker

    checker = BasicRelationChecker()

    async def check(relation, operands, expected=True):
        return await checker.check(
            {"relation": relation, "operands": operands, "expected": expected}
        )

    async def scenario() -> None:
        # 035 real geometry: apex 50°, base angles 65° at B=(0,0), A=(2.57,5.5)-ish
        angle = await check(
            "angle_degrees",
            [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], 45.0],
        )
        assert angle["verified"] and angle["holds"] is True

        wrong = await check(
            "angle_degrees",
            [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], 50.0],
        )
        assert wrong["verified"] and wrong["holds"] is False

        equal = await check(
            "equal_length",
            [[0, 0], [3, 0], [10, 10], [10, 13]],
        )
        assert equal["verified"] and equal["holds"] is True

        iso = await check("equal_distance", [[0, 0], [3, 4], [5, 0]])
        assert iso["verified"] and iso["holds"] is True

        on_seg = await check("point_on_segment", [[1, 1], [0, 0], [2, 2]])
        assert on_seg["verified"] and on_seg["holds"] is True

        off_seg = await check("point_on_segment", [[3, 3], [0, 0], [2, 2]])
        assert off_seg["verified"] and off_seg["holds"] is False

        unsupported = await check("angle_bisector", [[0, 0], [1, 0]])
        assert unsupported["verified"] is False

    anyio.run(scenario)
