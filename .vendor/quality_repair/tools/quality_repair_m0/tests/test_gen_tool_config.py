import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "gen_tool_config.py"


def write_bundle(path: Path, payload: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "bundle.json").write_text(json.dumps(payload), encoding="utf-8")


def test_generates_layout_tool_config_with_scene_name(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundles" / "layout" / "c001"
    repo_root = tmp_path / "repo"
    write_bundle(bundle_dir, {"profile": "layout", "scene_name": "Scene_05"})

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "bundles"), "--repo-root", str(repo_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    config = json.loads((bundle_dir / "tool_config.json").read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert config["check_cmd"] == [
        sys.executable,
        str(repo_root / "tools" / "quality_repair_checkers" / "layout_probe_check.py"),
        "--code",
        "{code}",
        "--workdir",
        "{workdir}",
        "--scene",
        "Scene_05",
    ]


def test_generates_logic_tool_config(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundles" / "logic" / "c001"
    repo_root = tmp_path / "repo"
    write_bundle(bundle_dir, {"profile": "logic", "scene_name": "Scene_01"})

    subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "bundles"), "--repo-root", str(repo_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    config = json.loads((bundle_dir / "tool_config.json").read_text(encoding="utf-8"))
    assert config["check_cmd"] == [
        sys.executable,
        str(repo_root / "tools" / "quality_repair_checkers" / "logic_contract_check.py"),
        "--code",
        "{code}",
        "--workdir",
        "{workdir}",
    ]
