from pathlib import Path

from libs.quality_repair.evidence import write_rounds
from libs.quality_repair.schemas import read_json


def test_write_rounds_persists_core_and_full_candidate_diffs(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    write_rounds(
        evidence_dir,
        rounds=[
            {
                "round": 1,
                "changed": True,
                "attempted_changed": True,
                "accepted": True,
                "before_blocking": 3,
                "after_blocking": 0,
                "tokens": 100,
                "blocking": 0,
                "signature": "sig",
                "base_code": "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n",
                "attempted_code": "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait(2)\n",
                "core_base_code": "class Solution(Scene):\n    def construct(self):\n        self.wait()\n",
                "core_attempted_code": "class Solution(Scene):\n    def construct(self):\n        self.wait(2)\n",
                "compose_report": {"enabled": True, "scene_class": "Solution"},
                "usage": {},
            }
        ],
        input_code="from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n",
        final_code="from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait(2)\n",
    )

    round_dir = evidence_dir / "round_01"
    usage = read_json(round_dir / "usage.json")
    assert usage["compose_report_path"] == "round_01/compose_report.json"
    assert usage["core_diff_path"] == "round_01/core_diff.patch"
    assert usage["full_diff_path"] == "round_01/full_diff.patch"
    assert "self.wait(2)" in (round_dir / "core_candidate.after.py").read_text(encoding="utf-8")
    assert "self.wait(2)" in (round_dir / "candidate.full.after.py").read_text(encoding="utf-8")
    assert "self.wait(2)" in (round_dir / "core_diff.patch").read_text(encoding="utf-8")
    assert "self.wait(2)" in (round_dir / "full_diff.patch").read_text(encoding="utf-8")
    assert read_json(round_dir / "compose_report.json")["enabled"] is True
