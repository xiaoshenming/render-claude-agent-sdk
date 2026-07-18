from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.quality_repair.tools.check import SubprocessChecker
from libs.quality_repair.tools.frame_at import frame_at
from libs.quality_repair.tools.render_scene import render_scene
from libs.quality_repair.tools.solve_layout import AxialSolver


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_checker_script(tmp_path: Path, payload: object) -> Path:
    checker_script = tmp_path / "checker.py"
    checker_script.write_text(
        "import json\n"
        f"print(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    return checker_script


def _write_tool_config(tmp_path: Path, checker_script: Path) -> None:
    _write_json(
        tmp_path / "tool_config.json",
        {
            "check_cmd": [
                sys.executable,
                str(checker_script),
                "--code",
                "{code}",
                "--workdir",
                "{workdir}",
            ]
        },
    )


def test_subprocess_checker_parses_json_stdout(tmp_path: Path) -> None:
    checker_script = _write_checker_script(
        tmp_path,
        {"passed": True, "blocking_count": 0, "issues": []},
    )
    code_path = tmp_path / "candidate.py"
    code_path.write_text("print('ok')\n", encoding="utf-8")
    _write_tool_config(tmp_path, checker_script)

    result = SubprocessChecker().run_check(code_path, tmp_path)

    assert result.ok is True
    assert result.passed is True
    assert result.blocking_count == 0
    assert result.issues == []


def test_subprocess_checker_accepts_blocking_alias(tmp_path: Path) -> None:
    checker_script = _write_checker_script(
        tmp_path,
        {"passed": False, "blocking": 2, "issues": [{"kind": "overlap"}]},
    )
    code_path = tmp_path / "candidate.py"
    code_path.write_text("print('ok')\n", encoding="utf-8")
    _write_tool_config(tmp_path, checker_script)

    result = SubprocessChecker().run_check(code_path, tmp_path)

    assert result.ok is True
    assert result.blocking_count == 2
    assert result.issues == [{"kind": "overlap"}]


def test_subprocess_checker_accepts_blocking_pairs_alias(tmp_path: Path) -> None:
    checker_script = _write_checker_script(
        tmp_path,
        {
            "passed": False,
            "blocking_pairs": [{"a": "A", "b": "B"}, {"a": "C", "b": "D"}],
            "issues": [],
        },
    )
    code_path = tmp_path / "candidate.py"
    code_path.write_text("print('ok')\n", encoding="utf-8")
    _write_tool_config(tmp_path, checker_script)

    result = SubprocessChecker().run_check(code_path, tmp_path)

    assert result.ok is True
    assert result.blocking_count == 2
    assert result.issues == []


def test_subprocess_checker_preserves_checker_ok_false(tmp_path: Path) -> None:
    checker_script = _write_checker_script(
        tmp_path,
        {"ok": False, "passed": False, "blocking_count": -1, "issues": [], "error": "compile_error"},
    )
    code_path = tmp_path / "candidate.py"
    code_path.write_text("print('bad')\n", encoding="utf-8")
    _write_tool_config(tmp_path, checker_script)

    result = SubprocessChecker().run_check(code_path, tmp_path)

    assert result.ok is False
    assert result.error == "compile_error"
    assert result.blocking_count == -1


def test_subprocess_checker_missing_config_fails_open(tmp_path: Path) -> None:
    result = SubprocessChecker().run_check(tmp_path / "candidate.py", tmp_path)

    assert result.ok is False
    assert result.error is not None


def test_check_cli_missing_config_prints_json_and_exits_zero(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "libs.quality_repair.tools.check",
            "--workdir",
            str(tmp_path / "missing"),
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert payload["ok"] is False
    assert payload["error"]


def test_axial_solver_shifts_on_smaller_overlap_axis(tmp_path: Path) -> None:
    facts = tmp_path / "facts"
    _write_json(facts / "collisions.json", [{"a": "A", "b": "B"}])
    _write_json(
        facts / "layout_context.json",
        {"objects": {"A": [0, 0, 2, 4], "B": [1.5, 0, 4, 4]}},
    )
    _write_json(facts / "safe_area.json", [-10, -10, 10, 10])

    result = AxialSolver().solve(tmp_path)

    assert result
    first = result[0]
    assert first["action"] == "shift"
    assert first["axis"] == "x"
    assert abs(first["delta"]) >= 0.6
    assert first["reason"]


def test_axial_solver_accepts_nested_bbox_and_edge_names(tmp_path: Path) -> None:
    facts = tmp_path / "facts"
    _write_json(facts / "collisions.json", [{"a": "A", "b": "B"}])
    _write_json(
        facts / "layout_context.json",
        {
            "objects": {
                "A": {"bbox": {"left": 0, "right": 2, "top": 0, "bottom": 2}},
                "B": {"left": 1.5, "right": 3, "top": 0, "bottom": 2},
            }
        },
    )
    _write_json(
        facts / "safe_area.json",
        {"safe_area": {"x_min": -10, "y_min": -10, "x_max": 10, "y_max": 10}},
    )

    result = AxialSolver().solve(tmp_path)

    assert result
    assert result[0]["action"] == "shift"
    assert result[0]["axis"] == "x"


def test_axial_solver_skips_when_both_axes_exceed_safe_area(tmp_path: Path) -> None:
    facts = tmp_path / "facts"
    _write_json(facts / "collisions.json", [{"object_a": "A", "object_b": "B"}])
    _write_json(
        facts / "layout_context.json",
        {"bboxes": {"A": [0, 0, 1, 1], "B": [0.5, 0.5, 2, 2]}},
    )
    _write_json(facts / "safe_area.json", [0, 0, 2, 2])

    result = AxialSolver().solve(tmp_path)

    assert result == [{"object": "A", "action": "skip", "reason": "no_axial_solution"}]


def test_render_scene_and_frame_at_return_structured_dicts(tmp_path: Path) -> None:
    code_path = tmp_path / "candidate.py"
    video_path = tmp_path / "video.mp4"
    out_dir = tmp_path / "rendered"
    frame_path = tmp_path / "frame.png"
    code_path.write_text("class Demo: pass\n", encoding="utf-8")
    video_path.write_text("fake", encoding="utf-8")
    _write_json(
        tmp_path / "tool_config.json",
        {
            "render_cmd": ["echo", "{out}", "{code}", "{scene}"],
            "frame_cmd": ["echo", "{out}", "{video}", "{second}"],
        },
    )

    render_result = render_scene(
        code_path=code_path,
        scene_name="DemoScene",
        out_dir=out_dir,
        workdir=tmp_path,
    )
    frame_result = frame_at(
        video_path=video_path,
        second=2.5,
        out_path=frame_path,
        workdir=tmp_path,
    )

    assert set(["ok", "out", "error"]).issubset(render_result)
    assert set(["ok", "out", "error"]).issubset(frame_result)
    assert render_result["ok"] is True
    assert frame_result["ok"] is True
    assert render_result["out"] == str(out_dir)
    assert frame_result["out"] == str(frame_path)
    assert str(out_dir) in str(render_result.get("stdout", ""))
    assert str(frame_path) in str(frame_result.get("stdout", ""))
