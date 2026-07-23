from pathlib import Path

from evals.workbench_e2e.relation_context import relation_prompt_evidence
from scripts.replay_logic_source_library import _planning


def test_replay_planning_excludes_historical_verdicts(tmp_path: Path) -> None:
    (tmp_path / "problem.txt").write_text("验证勾股定理。", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        '{"logic":{"decision":"needs_repair"},"review_tokens":999}',
        encoding="utf-8",
    )

    planning = _planning(tmp_path)

    assert planning == {"scene_intent": "验证勾股定理。"}


def test_empty_relation_is_not_forwarded_to_reviewer() -> None:
    payload = {
        "status": "available",
        "scene_id": "MainScene",
        "contract": {"schema_version": "v1", "claims": []},
        "actual_comparison": {
            "flagged": False,
            "counts": {"satisfied": 0, "contradiction": 0, "unknown": 0},
            "comparisons": [],
        },
        "usage": {"total_tokens": 12345},
    }

    assert relation_prompt_evidence(payload) is None


def test_relation_prompt_evidence_strips_usage_metadata() -> None:
    payload = {
        "status": "available",
        "scene_id": "MainScene",
        "contract": {"schema_version": "v1", "claims": [{"relation": "parallel"}]},
        "actual_comparison": {
            "flagged": True,
            "target_hit": "AB",
            "counts": {"contradiction": 1},
            "comparisons": [{"status": "contradiction"}],
        },
        "usage": {"total_tokens": 12345},
    }

    result = relation_prompt_evidence(payload)

    assert result is not None
    assert "usage" not in result
    assert result["contract"]["claims"] == [{"relation": "parallel"}]
