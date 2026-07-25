from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_holdout import (
    HoldoutEvidence,
    HoldoutStatus,
    build_launch_report,
    load_evidence,
    verify_frozen_manifest,
)


def test_frozen_manifest_verification_rejects_changed_child(tmp_path: Path) -> None:
    child = tmp_path / "logic.json"
    child.write_text('{"frozen":true,"sample_count":2}\n', encoding="utf-8")
    manifest = tmp_path / "holdout.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen": True,
                "suites": [
                    {
                        "name": "logic",
                        "path": "logic.json",
                        "sha256": _sha(child),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    verified = verify_frozen_manifest(manifest)
    assert verified == {"logic": _sha(child)}

    child.write_text('{"frozen":true,"sample_count":3}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_frozen_manifest(manifest)


def test_launch_report_separates_outcomes_and_fails_closed() -> None:
    evidence = HoldoutEvidence(
        logic_good=HoldoutStatus.passed(10, {"over_edit_rate": 0.0}),
        logic_bad=HoldoutStatus.passed(
            10,
            {
                "detection_rate": 0.9,
                "repair_rate": 0.7,
                "verifier_pass_rate": 0.7,
            },
        ),
        overlap=HoldoutStatus.passed(
            10,
            {"clean": 6, "degraded": 2, "unchanged": 2, "accepted_worse": 0},
        ),
        modification=HoldoutStatus.passed(10, {"success_rate": 1.0}),
        fake_load=HoldoutStatus.passed(100, {"duplicate": 0, "completed": 100}),
        real_render=HoldoutStatus.not_run("target Linux renderer unavailable"),
        canary=HoldoutStatus.not_run("production shadow feed unavailable"),
    )

    report = build_launch_report("launch-v1", evidence, rollback_version="5c39be3")

    assert report["launch_decision"] == "HOLD"
    assert report["automatic_repair_enabled"] is False
    assert report["suites"]["logic_bad"]["metrics"]["detection_rate"] == 0.9
    assert report["suites"]["overlap"]["metrics"] == {
        "clean": 6,
        "degraded": 2,
        "unchanged": 2,
        "accepted_worse": 0,
    }
    assert set(report["blocking_reasons"]) == {"real_render:not_run", "canary:not_run"}


def test_status_requires_non_empty_reason_when_not_run() -> None:
    with pytest.raises(ValueError, match="reason"):
        HoldoutStatus(HoldoutStatus.NOT_RUN, 0, {}, "")


def test_committed_launch_evidence_is_hash_bound_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2]

    verified = verify_frozen_manifest(root / "evals" / "launch_manifest_v1.json")
    evidence = load_evidence(root / "evals" / "launch_evidence_v1.json")
    report = build_launch_report("launch-v1", evidence, rollback_version="5c39be3")

    assert len(verified) == 6
    assert report["launch_decision"] == "HOLD"
    assert report["automatic_repair_enabled"] is False
    assert "logic_bad:failed" in report["blocking_reasons"]


def _sha(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
