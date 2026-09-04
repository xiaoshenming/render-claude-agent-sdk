import copy

import pytest

from manim_quality.assurance.contracts import REQUIRED_TOOLS, validate_assurance_output
from manim_quality.assurance.models import ToolReport
from manim_quality.assurance.output_projection import project_output


def reports():
    return {name: ToolReport(name, "complete", (), ({"id": name + ":fact"},))
            for name in REQUIRED_TOOLS}


def test_executed_receipts_are_complete_even_when_model_omits_or_duplicates_them():
    observed = reports()
    raw = {"summary": "checked", "status": "pass", "issues": [],
           "tool_receipts": [{"tool": "inspect_layout"}] * 2}
    before = copy.deepcopy(raw)
    output = project_output(raw, observed)
    validate_assurance_output(output, expected_reports={k: v.as_dict() for k, v in observed.items()})
    assert len(output["tool_receipts"]) == 6
    assert output["summary"] == raw["summary"] and output["issues"] == raw["issues"]
    assert raw == before


def test_missing_tool_execution_is_never_fabricated():
    observed = reports()
    del observed["inspect_artifact"]
    output = project_output({"status": "pass", "summary": "checked", "issues": [],
                             "tool_receipts": []}, observed)
    assert output["tool_receipts"] == []
    with pytest.raises(ValueError, match="missing"):
        validate_assurance_output(output)


def test_issue_content_preserved_and_incomplete_evidence_cannot_become_pass():
    observed = reports()
    observed["inspect_layout"] = ToolReport("inspect_layout", "incomplete", (), ())
    issues = [{"severity": "high", "category": "math", "summary": "wrong equation",
               "evidence_ids": ["inspect_code_review:fact"]}]
    output = project_output({"status": "pass", "summary": "original", "issues": issues}, observed)
    assert output["status"] == "incomplete"
    assert output["issues"] == issues
    validate_assurance_output(output, expected_reports={k: v.as_dict() for k, v in observed.items()})


def test_failed_parent_keeps_original_messages_and_rejection(tmp_path):
    import json
    from types import SimpleNamespace
    from manim_quality.assurance.parent_evidence import record_parent_attempt
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_tokens=0,
                            cache_write_tokens=0)
    tool = SimpleNamespace(name="StructuredOutput", call_id="out-1", allowed=False,
                           error="unknown evidence", result_status=None,
                           started_at_ms=100, finished_at_ms=100)
    record = SimpleNamespace(run_id="parent", error="correction limit", elapsed_ms=50,
                             turns=1, usage=usage, tool_calls=(tool,))
    record_parent_attempt(tmp_path, 1, record, ({"type": "assistant", "text": "raw"},))
    assert json.loads((tmp_path / "parent-sdk-messages.jsonl").read_text())["message"]["text"] == "raw"
    assert json.loads((tmp_path / "parent-tool-results.jsonl").read_text())["error"] == "unknown evidence"
