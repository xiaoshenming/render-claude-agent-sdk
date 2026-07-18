from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

from manim_quality.logic.output_schema import REVIEW_OUTPUT_SCHEMA

ROOT = Path(__file__).resolve().parents[3]
LEGACY_ROOT = ROOT / "vendor" / "logic_self_audit_baseline"
CURRENT_PROMPT = ROOT / "src" / "manim_quality" / "logic" / "prompts" / "reviewer.md"


def _legacy(monkeypatch, module: str):
    monkeypatch.syspath_prepend(str(LEGACY_ROOT))
    return importlib.import_module(f"app.workers.post_render_logic.{module}")


def test_current_reviewer_preserves_and_hardens_legacy_review_contract(
    monkeypatch,
) -> None:
    legacy = _legacy(monkeypatch, "claude_adapters")
    legacy_decisions = legacy.REVIEW_REPORT_SCHEMA["properties"]["decision"]["enum"]
    current_decisions = REVIEW_OUTPUT_SCHEMA["properties"]["decision"]["enum"]

    assert legacy_decisions == ["pass", "repair", "record_only", "human_review"]
    assert current_decisions == [
        "pass",
        "needs_repair",
        "record_only",
        "human_review",
    ]
    assert set(legacy.REVIEW_REPORT_SCHEMA["required"]) <= {
        "review_id",
        "decision",
        "blocked",
        "issues",
    }
    current_prompt = CURRENT_PROMPT.read_text(encoding="utf-8")
    assert "不做视觉" in legacy.REVIEW_SYSTEM_PROMPT
    assert "Do not review layout overlap" in current_prompt
    assert "Every issue needs direct evidence" in current_prompt
    assert "code-only mutation probe" in current_prompt
    assert "Every issue object must include all of these fields" in current_prompt
    assert "`repairable` must always be present" in current_prompt
    assert "Do not add fields outside that list" in current_prompt


def test_legacy_reviewer_binds_repair_issue_and_human_decision(monkeypatch) -> None:
    legacy = _legacy(monkeypatch, "claude_adapters")
    issue = {
        "issue_id": "legacy-issue",
        "issue_type": "final_answer_mismatch",
        "severity": "high",
        "confidence": 0.9,
        "repairable": True,
        "repair_scope": "formula_claim_only",
        "target_scene_ids": ["Scene_02_Solve"],
        "evidence": [{"artifact": "scene_code", "claim": "x=12"}],
        "expected": "x=10",
        "observed": "x=12",
        "acceptance_predicates": [{"predicate": "text_absent", "value": "x=12"}],
        "non_goals": ["layout"],
    }

    repair = legacy._review_from_payload(
        {
            "review_id": "legacy-repair",
            "decision": "repair",
            "blocked": True,
            "issues": [issue],
        },
        "legacy-code-hash",
    )
    human = legacy._review_from_payload(
        {
            "review_id": "legacy-human",
            "decision": "human_review",
            "blocked": True,
            "issues": [],
        },
        "legacy-code-hash",
    )

    assert repair.decision == "repair"
    assert repair.blocked is True
    assert repair.issues[0].expected == "x=10"
    assert repair.issues[0].acceptance_predicates[0]["value"] == "x=12"
    assert human.decision == "human_review"
    assert human.blocked is True


def test_legacy_sdk_runner_is_stateless_no_tool_and_fails_malformed(
    monkeypatch,
) -> None:
    legacy = _legacy(monkeypatch, "sdk_runner")
    captured = {}

    async def structured_query(**kwargs):
        captured["options"] = kwargs["options"]

        class Result:
            structured_output = {"decision": "pass", "issues": []}

        yield Result()

    runner = legacy.ClaudeAgentJsonRunner(query_func=structured_query, cwd=".")
    result = asyncio.run(
        runner.run_json(
            prompt="review",
            schema={"type": "object"},
            system_prompt="system",
        )
    )

    assert result == {"decision": "pass", "issues": []}
    assert captured["options"].tools == []
    assert captured["options"].allowed_tools == []
    assert captured["options"].max_turns == 1

    async def malformed_query(**_kwargs):
        class Result:
            structured_output = None
            result = "[]"

        yield Result()

    malformed = legacy.ClaudeAgentJsonRunner(query_func=malformed_query, cwd=".")
    with pytest.raises(ValueError, match="must be an object"):
        asyncio.run(
            malformed.run_json(
                prompt="review",
                schema={"type": "object"},
                system_prompt="system",
            )
        )
