from pathlib import Path

import pytest

from manim_quality.agents.guards import ToolGuard
from manim_quality.agents.profile import operator_profile
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.operator.candidate_io import (
    find_baseline_candidate,
    live_solution_read,
)


def test_baseline_candidate_is_an_agent_owned_copy(tmp_path: Path) -> None:
    source = tmp_path / "candidate.py"
    baseline = "class Solution: pass\n"
    source.write_text(baseline, encoding="utf-8")

    editable = find_baseline_candidate(tmp_path, baseline)
    editable.write_text("class Solution: changed\n", encoding="utf-8")

    assert editable != source
    assert source.read_text(encoding="utf-8") == baseline
    assert editable.parent.name.startswith(".quality-agent-session-")


def test_live_solution_read_recomputes_after_edit(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "from manim import *\n\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        self.wait()\n\n"
        "print('suffix')\n",
        encoding="utf-8",
    )
    normalize = live_solution_read(candidate)

    first = normalize({"file_path": str(candidate)})
    candidate.write_text(
        candidate.read_text(encoding="utf-8").replace(
            "        self.wait()\n",
            "        self.wait()\n"
            "        self.play(Create(Dot()))\n"
            "        self.wait()\n",
        ),
        encoding="utf-8",
    )
    second = normalize(
        {
            "file_path": str(candidate),
        }
    )

    assert (first["offset"], first["limit"]) == (3, 3)
    assert (second["offset"], second["limit"]) == (3, 5)


def test_live_solution_read_rebinds_mistyped_candidate_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    pass\n", encoding="utf-8"
    )
    normalize = live_solution_read(candidate)

    result = normalize(
        {
            "file_path": str(tmp_path / "candidate.p"),
            "offset": 999,
            "limit": 999,
        }
    )

    assert result["file_path"] == str(candidate)
    assert (result["offset"], result["limit"]) == (2, 1)


def test_live_solution_read_records_real_native_read(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    pass\n", encoding="utf-8"
    )
    reads = []
    normalize = live_solution_read(candidate, on_read=lambda: reads.append("R0"))

    normalize({"file_path": str(candidate), "offset": 1, "limit": 1})

    assert reads == ["R0"]


def test_live_read_preserves_observed_helper_ranges_and_replays(tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "# header\n" * 1888 + "class Solution(BaseConfigScene):\n" + "    pass\n" * 153)
    guard = ToolGuard(
        workspace=tmp_path,
        profile=operator_profile(model="fake", prompt_version="test"),
        readable_paths=(candidate,), editable_paths=(candidate,),
        tool_policies={"Read": ToolInputPolicy(
            max_calls=120, input_normalizer=live_solution_read(candidate))},
    )
    # Exact requests seen in a production failed Coder session. The old
    # normalizer rewrote both helper ranges to (1889,154), then denied them.
    for offset, limit in [(1889, 154), (380, 35), (610, 170), (610, 170)]:
        result = guard.authorize("Read", {
            "file_path": str(candidate), "offset": offset, "limit": limit})
        assert (result["offset"], result["limit"]) == (offset, limit)


@pytest.mark.parametrize("count", [0, -1, True, "3"])
def test_live_read_rejects_invalid_range(tmp_path, count):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("class Solution(BaseConfigScene):\n    pass\n")
    with pytest.raises(ValueError, match="positive integer"):
        live_solution_read(candidate)({"offset": count})
