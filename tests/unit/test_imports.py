def test_public_package_imports() -> None:
    import manim_quality

    assert manim_quality.__version__ == "0.1.0"


def test_storage_public_exports_preserve_artifacts_and_queue_contracts() -> None:
    from manim_quality import storage

    assert {
        "ArtifactStore",
        "LocalArtifactStore",
        "IntakeLimits",
        "QueueClass",
        "QueueItem",
        "QueueState",
    } <= set(storage.__all__)


def test_wheel_includes_api_and_worker_applications() -> None:
    import tomllib
    from pathlib import Path

    config = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    force_include = config["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    assert force_include["apps"] == "apps"
