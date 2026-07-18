import json

from evals.workbench_e2e.logic_stage import _record_only_allowed


def test_record_only_policy_allows_only_nonblocking_low_risk_issues(tmp_path):
    path = tmp_path / "cases" / "job" / "review_report.json"
    path.parent.mkdir(parents=True)
    report = {
        "decision": "record_only",
        "blocked": False,
        "requires_human_review": False,
        "issues": [{"severity": "low"}],
    }
    path.write_text(json.dumps(report), encoding="utf-8")

    assert _record_only_allowed(tmp_path, "job")
    report["issues"][0]["severity"] = "medium"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert not _record_only_allowed(tmp_path, "job")
