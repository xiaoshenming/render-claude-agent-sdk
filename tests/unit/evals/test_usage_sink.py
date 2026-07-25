import json

from evals._logic_shadow_io import JsonSequenceUsageSink
from manim_quality.agents import AgentCallRecord, TokenUsage


def record(run_id: str) -> AgentCallRecord:
    return AgentCallRecord(
        run_id,
        "coder",
        "model",
        "prompt",
        "prompt-v1",
        "schema-v1",
        "tool-v1",
        None,
        (),
        TokenUsage(input_tokens=10),
        1,
        1,
        100,
        None,
    )


def test_sequence_sink_persists_every_agent_call(tmp_path) -> None:
    sink = JsonSequenceUsageSink(tmp_path, "coder")

    sink.save(record("first"))
    sink.save(record("second"))

    assert [item.run_id for item in sink.records] == ["first", "second"]
    assert (
        json.loads((tmp_path / "coder-call-001.json").read_text())["run_id"] == "first"
    )
    assert (
        json.loads((tmp_path / "coder-call-002.json").read_text())["run_id"] == "second"
    )
