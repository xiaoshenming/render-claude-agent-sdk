from types import SimpleNamespace

from manim_quality.agents.usage import TokenUsage
from scripts.run_final_assurance_demo import arguments, run_agent_case, usage_dict


def test_demo_defaults_parent_to_production_turn_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "sys.argv", ["run_final_assurance_demo.py", "--output", str(tmp_path)]
    )

    assert arguments().max_turns == 24


def test_demo_exports_all_result_message_usage_dimensions() -> None:
    record = SimpleNamespace(
        usage=TokenUsage(
            input_tokens=101,
            output_tokens=23,
            cache_read_tokens=47,
            cache_write_tokens=5,
        )
    )

    assert usage_dict(record) == {
        "input_tokens": 101,
        "output_tokens": 23,
        "cache_read_tokens": 47,
        "cache_write_tokens": 5,
        "total_tokens": 176,
    }


def test_demo_does_not_publish_missing_usage_as_zero() -> None:
    record = SimpleNamespace(usage=TokenUsage())

    assert usage_dict(record) is None


def test_case_result_keeps_parent_and_reviewer_usage_separate(tmp_path) -> None:
    parent = _record(TokenUsage(100, 20, 30, 4), turns=3)
    aggregate = _record(TokenUsage(150, 35, 50, 6), turns=7)
    result = SimpleNamespace(
        output={"status": "pass", "issues": []},
        reports={},
        reviewers=({
            "agent_type": "math_geometry_reviewer",
            "usage": {
                "input_tokens": 50,
                "output_tokens": 15,
                "cache_read_tokens": 20,
                "cache_write_tokens": 2,
            },
        },),
        parent_call_record=parent,
        call_record=aggregate,
    )
    agent = SimpleNamespace(run=lambda _case, _output: result)
    args = SimpleNamespace(output=tmp_path)

    row = run_agent_case(SimpleNamespace(key="CASE"), args, {}, agent)

    assert row["agent"]["token_usage"]["total_tokens"] == 154
    assert row["reviewers"][0]["usage"]["input_tokens"] == 50
    assert row["agent_usage"]["token_usage"]["total_tokens"] == 241


def _record(usage: TokenUsage, *, turns: int):
    return SimpleNamespace(
        usage=usage,
        usage_complete=True,
        model="gpt",
        elapsed_ms=123,
        turns=turns,
        tool_calls=(),
    )
