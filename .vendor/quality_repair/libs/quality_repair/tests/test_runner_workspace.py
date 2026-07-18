from pathlib import Path

from libs.quality_repair.agent import runner_workspace


def test_mirror_workspace_files_exposes_only_sdk_inputs(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(runner_workspace, "WORKSPACE_ROOT", workspace)

    for name in ("layout_issue_digest.json", "layout_repair_brief.json", "layout_repair_contract.json", "layout_context.json", "candidate.py"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    with runner_workspace._mirror_workspace_files_during_sdk(tmp_path):
        assert (workspace / "layout_issue_digest.json").is_symlink()
        assert (workspace / "candidate.py").is_symlink()
        assert not (workspace / "layout_repair_brief.json").exists()
        assert not (workspace / "layout_repair_contract.json").exists()
        assert not (workspace / "layout_context.json").exists()

    assert not (workspace / "layout_issue_digest.json").exists()
    assert not (workspace / "candidate.py").exists()
    assert not (workspace / "layout_repair_brief.json").exists()
    assert not (workspace / "layout_repair_contract.json").exists()
