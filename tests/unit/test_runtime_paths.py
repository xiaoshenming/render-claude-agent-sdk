from pathlib import Path

import pytest

from manim_quality.runtime_paths import release_asset


def test_release_asset_resolves_through_installed_venv(tmp_path: Path) -> None:
    release = tmp_path / "release"
    module = release / ".venv/lib/python3.12/site-packages/pkg/module.py"
    module.parent.mkdir(parents=True)
    module.touch()
    asset = release / "vendor/layout_probe/probe_runner.txt"
    asset.parent.mkdir(parents=True)
    asset.touch()

    assert release_asset(module, "vendor/layout_probe/probe_runner.txt") == asset


def test_release_asset_rejects_escape(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.touch()

    with pytest.raises(ValueError, match="contained"):
        release_asset(module, "../secret")
