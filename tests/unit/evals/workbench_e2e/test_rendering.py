from pathlib import Path

from evals.workbench_e2e.rendering import LocalManimRenderer, scene_name

SOURCE = """from manim import *
class BaseConfigScene(Scene):
    pass
class Solution(BaseConfigScene):
    def construct(self):
        self.wait()
"""


def test_scene_name_prefers_solution_over_base_scene():
    assert scene_name(SOURCE) == "Solution"


def test_renderer_persists_command_and_logs(tmp_path):
    source = tmp_path / "candidate.py"
    source.write_text(SOURCE, encoding="utf-8")

    def run(command, **kwargs):
        assert "MANIM_E2E_API_KEY" not in kwargs["env"]
        output = Path(command[command.index("--media_dir") + 1])
        video = output / "videos" / "candidate" / "480p15" / "result.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"video")
        return _Completed()

    result = LocalManimRenderer(python="python-x", runner=run).render(
        source, tmp_path / "render"
    )

    assert result.succeeded
    assert result.video_path and result.video_path.is_file()
    assert result.command[0] == "python-x"
    assert (tmp_path / "render" / "render.json").is_file()


class _Completed:
    returncode = 0
    stdout = "ok"
    stderr = ""
