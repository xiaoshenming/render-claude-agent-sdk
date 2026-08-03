import json

from manim_quality.agents.usage import (
    AgentCallRecord,
    JsonlUsageLedger,
    TokenUsage,
    ToolCallRecord,
    aggregate_job_usage,
)


def test_ledger_is_append_only_and_receipt_aggregates_all_dimensions(tmp_path) -> None:
    first = _record("parent", TokenUsage(10, 2, 3, 1), 20, 5)
    second = _record("reviewer", TokenUsage(4, 1, 8, 0), 30, 7)
    ledger = JsonlUsageLedger(tmp_path / "usage.jsonl")
    ledger.save(first)
    ledger.save(second)

    rows = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    receipt = aggregate_job_usage("job-1", (first, second))

    assert [row["role"] for row in rows] == ["parent", "reviewer"]
    assert receipt.calls == 2
    assert receipt.usage == TokenUsage(14, 3, 11, 1)
    assert receipt.elapsed_ms == 50
    assert receipt.external_tool_ms == 12
    assert len(receipt.record_hashes) == 2


def _record(role, usage, elapsed, tool_ms):
    return AgentCallRecord(
        run_id=f"run-{role}", role=role, model="model", prompt="prompt",
        prompt_version="p", schema_version="s", tool_version="t",
        structured_output=None,
        tool_calls=(ToolCallRecord(name="inspect", input={}, allowed=True),),
        usage=usage, turns=1, observed_model_rounds=1, elapsed_ms=elapsed,
        error=None, external_tool_ms=tool_ms,
    )
