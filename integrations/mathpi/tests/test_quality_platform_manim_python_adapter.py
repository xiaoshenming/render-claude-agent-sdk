from pathlib import Path

from app.quality_platform.manim_python_adapter import (
    build_container_command,
    prepare_media_directory,
    prepare_python_entrypoint,
)


def test_maps_handoff_render_paths_into_existing_manim_container() -> None:
    host_root = Path("/opt/mathpi/apps/render/manim_media")
    command = build_container_command(
        (
            "-m",
            "manim",
            "--media_dir",
            str(host_root / "quality-v3/run/render"),
            str(host_root / "quality-v3/run/candidate.py"),
            "Solution",
        ),
        container="manim-worker-2",
        host_root=host_root,
    )

    assert command[:8] == (
        "docker",
        "exec",
        "-u",
        "manimuser",
        "-w",
        "/home/manimuser",
        "-e",
        "PYTHONPATH=/home/manimuser/manim_media",
    )
    assert "manim-worker-2" in command
    assert "/home/manimuser/manim_media/quality-v3/run/candidate.py" in command
    assert "/home/manimuser/manim_media/quality-v3/run/render" in command


def test_rejects_render_paths_outside_shared_media_root() -> None:
    try:
        build_container_command(
            ("-m", "manim", "/tmp/candidate.py", "Solution"),
            container="manim-worker-1",
            host_root=Path("/opt/mathpi/apps/render/manim_media"),
        )
    except ValueError as error:
        assert "outside shared media root" in str(error)
    else:
        raise AssertionError("outside path must be rejected")


def test_prepares_media_directory_for_unprivileged_container(tmp_path: Path) -> None:
    media = tmp_path / "render"
    media.mkdir()
    media.chmod(0o755)

    prepare_media_directory(("--media_dir", str(media)), host_root=tmp_path)

    assert media.stat().st_mode & 0o777 == 0o777


def test_maps_embedded_media_root_in_generated_probe(tmp_path: Path) -> None:
    runner = tmp_path / "quality-v3/layout/probe_runner.py"
    runner.parent.mkdir(parents=True)
    runner.write_text(
        f'config.media_dir = "{runner.parent}/manim_media"\n',
        encoding="utf-8",
    )

    prepare_python_entrypoint((str(runner),), host_root=tmp_path)

    assert runner.read_text(encoding="utf-8") == (
        'config.media_dir = "/home/manimuser/manim_media/'
        'quality-v3/layout/manim_media"\n'
    )
    assert (runner.parent / "manim_media").is_dir()
    assert (runner.parent / "manim_media").stat().st_mode & 0o777 == 0o777
