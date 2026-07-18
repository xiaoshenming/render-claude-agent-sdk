from __future__ import annotations

import json
from pathlib import Path

from libs.quality_repair.core_candidate_view import (
    compose_candidate_from_core,
    prepare_core_candidate_view,
    read_core_candidate_view,
)


def _write_candidate(workdir: Path, source: str) -> None:
    (workdir / "candidate.py").write_text(source, encoding="utf-8")


def test_prepare_core_candidate_view_writes_first_construct_scene_view(tmp_path: Path) -> None:
    source = (
        "from manim import *\n"
        "\n"
        "class GlobalConfig:\n"
        "    value = 1\n"
        "\n"
        "class Helper:\n"
        "    pass\n"
        "\n"
        "class Solution(BaseConfigScene):\n"
        "    def setup(self):\n"
        "        self.flag = True\n"
        "\n"
        "    def construct(self):\n"
        "        self.add(Text('old'))\n"
        "\n"
        "class ExtraScene(Scene):\n"
        "    def construct(self):\n"
        "        pass\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    pass\n"
    )
    _write_candidate(tmp_path, source)

    view = prepare_core_candidate_view(tmp_path)

    assert view.enabled is True
    assert view.fallback is False
    assert view.scene_class == "Solution"
    assert (tmp_path / "candidate_prelude.txt").read_text(encoding="utf-8") == (
        "from manim import *\n"
        "\n"
        "class GlobalConfig:\n"
        "    value = 1\n"
        "\n"
        "class Helper:\n"
        "    pass\n"
        "\n"
    )
    assert (tmp_path / "core_candidate.py").read_text(encoding="utf-8").startswith(
        "class Solution(BaseConfigScene):\n"
    )
    assert "class ExtraScene(Scene):" in (tmp_path / "core_candidate.py").read_text(encoding="utf-8")

    core_map = json.loads((tmp_path / "candidate_core_map.json").read_text(encoding="utf-8"))
    assert core_map["enabled"] is True
    assert core_map["fallback"] is False
    assert core_map["scene_class"] == "Solution"
    assert core_map["core_start_line"] == 9
    assert core_map["compose_strategy"] == "prelude_plus_core_to_candidate_py"
    assert len(core_map["candidate_sha256"]) == 64
    assert len(core_map["core_sha256"]) == 64
    assert len(core_map["prelude_sha256"]) == 64


def test_read_view_and_compose_candidate_from_edited_core(tmp_path: Path) -> None:
    _write_candidate(
        tmp_path,
        "from manim import *\n"
        "\n"
        "class Solution(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Text('old'))\n",
    )
    prepared = prepare_core_candidate_view(tmp_path)
    assert prepared.enabled is True

    core_path = tmp_path / "core_candidate.py"
    core_path.write_text(core_path.read_text(encoding="utf-8").replace("old", "new"), encoding="utf-8")

    loaded = read_core_candidate_view(tmp_path)
    composed = compose_candidate_from_core(tmp_path)

    assert loaded.enabled is True
    assert loaded.scene_class == "Solution"
    assert composed.ok is True
    assert composed.fallback is False
    assert composed.target_path == tmp_path / "candidate.py"
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == (
        "from manim import *\n"
        "\n"
        "class Solution(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Text('new'))\n"
    )


def test_prepare_core_candidate_view_fail_open_on_syntax_error(tmp_path: Path) -> None:
    _write_candidate(tmp_path, "class Broken(Scene):\n    def construct(self):\n        if\n")

    view = prepare_core_candidate_view(tmp_path)

    assert view.enabled is False
    assert view.fallback is True
    assert view.reason.startswith("parse_error:")
    core_map = json.loads((tmp_path / "candidate_core_map.json").read_text(encoding="utf-8"))
    assert core_map["enabled"] is False
    assert core_map["fallback"] is True
    assert core_map["reason"].startswith("parse_error:")


def test_prepare_core_candidate_view_fail_open_when_no_construct_scene(tmp_path: Path) -> None:
    _write_candidate(tmp_path, "class Helper:\n    def build(self):\n        pass\n")

    view = prepare_core_candidate_view(tmp_path)

    assert view.enabled is False
    assert view.fallback is True
    assert view.reason == "no_scene_with_construct"
    assert not (tmp_path / "core_candidate.py").exists()
    assert not (tmp_path / "candidate_prelude.txt").exists()


def test_read_and_compose_fail_open_on_bad_map_without_raising(tmp_path: Path) -> None:
    _write_candidate(tmp_path, "class Solution(Scene):\n    def construct(self):\n        pass\n")
    (tmp_path / "candidate_core_map.json").write_text("{bad json", encoding="utf-8")

    view = read_core_candidate_view(tmp_path)
    composed = compose_candidate_from_core(tmp_path)

    assert view.enabled is False
    assert view.fallback is True
    assert view.reason.startswith("map_read_error:")
    assert composed.ok is False
    assert composed.fallback is True
    assert composed.reason.startswith("map_read_error:")


def test_compose_fail_open_when_enabled_view_files_are_missing(tmp_path: Path) -> None:
    _write_candidate(tmp_path, "class Solution(Scene):\n    def construct(self):\n        pass\n")
    (tmp_path / "candidate_core_map.json").write_text(
        json.dumps(
            {
                "schema_version": "quality_repair.core_candidate_view.v1",
                "enabled": True,
                "fallback": False,
                "candidate_path": "candidate.py",
                "prelude_path": "candidate_prelude.txt",
                "core_path": "core_candidate.py",
                "scene_class": "Solution",
            }
        ),
        encoding="utf-8",
    )

    composed = compose_candidate_from_core(tmp_path)

    assert composed.ok is False
    assert composed.fallback is True
    assert composed.reason == "view_files_missing"
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == (
        "class Solution(Scene):\n    def construct(self):\n        pass\n"
    )
