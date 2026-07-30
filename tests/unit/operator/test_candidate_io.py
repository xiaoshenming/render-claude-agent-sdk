from pathlib import Path

from manim_quality.operator.candidate_io import live_solution_read


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

    first = normalize({"file_path": str(candidate), "offset": 1, "limit": 999})
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
            "offset": first["offset"],
            "limit": first["limit"],
        }
    )

    assert (first["offset"], first["limit"]) == (3, 3)
    assert (second["offset"], second["limit"]) == (3, 5)
