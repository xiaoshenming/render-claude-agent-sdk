import hashlib
import subprocess
import tarfile
from pathlib import Path

from scripts.build_release_bundle import build_release_bundle, verify_release_bundle


def test_release_bundle_includes_materialized_vendor(tmp_path: Path):
    repo = tmp_path / "sdk"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "QUALITY_AGENT_ABI").write_text(
        "batchops-quality-agent.v3\n", encoding="utf-8"
    )
    vendor = repo / ".vendor/quality_repair"
    checker = vendor / "tools/quality_repair_checkers/layout_probe_check.py"
    checker.parent.mkdir(parents=True)
    checker.write_text("print('ok')\n", encoding="utf-8")
    digest = hashlib.sha256(checker.read_bytes()).hexdigest()
    (vendor / "PAYLOAD_SHA256SUMS.txt").write_text(
        f"{digest}  tools/quality_repair_checkers/layout_probe_check.py\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "src", "QUALITY_AGENT_ABI"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    output = tmp_path / "release.tar.gz"

    build_release_bundle(repo, output, commit)
    receipt = verify_release_bundle(output, commit)

    assert receipt["vendor_files"] == 2
    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())
    assert "RELEASE_COMMIT" in names
    assert ".vendor/quality_repair/PAYLOAD_SHA256SUMS.txt" in names
    checker_name = (
        ".vendor/quality_repair/tools/quality_repair_checkers/layout_probe_check.py"
    )
    assert checker_name in names
