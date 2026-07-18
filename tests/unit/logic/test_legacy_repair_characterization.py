from tools.logic_engine_mvp.logic_engine_mvp.agent_repair import build_repair_prompt
from tools.logic_engine_mvp.logic_engine_mvp.contract_builder import (
    build_repair_contract,
)


def test_legacy_repair_prompt_used_read_edit_and_outer_validation(tmp_path) -> None:
    prompt = build_repair_prompt(tmp_path)

    assert "Allowed SDK tools: Read, Edit." in prompt
    assert "Disallowed SDK tools: Bash, Write." in prompt
    assert "Do not Read candidate.py after successful Edit" in prompt
    assert "outer validation will verify" in prompt
    assert "Do not repair layout overlap" in prompt


def test_legacy_contract_bound_exact_lines_and_protected_other_matches(
    tmp_path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 12\nvalue = 12\n", encoding="utf-8")
    review = {
        "sample_id": "characterization",
        "issues": [
            {
                "issue_id": "I-1",
                "issue_type": "answer_mismatch",
                "verification_status": "supported",
                "line_replacements": [
                    {
                        "source_line": 1,
                        "exact_code_before": "value = 12",
                        "exact_code_after": "value = 10",
                    }
                ],
            }
        ],
    }

    contract = build_repair_contract(candidate, review)

    assert contract["policy"]["allowed_tools"] == ["Read", "Edit"]
    assert contract["policy"]["disallowed_tools"] == ["Bash", "Write"]
    item = contract["contracts"][0]
    assert item["source_lines"] == [1]
    assert item["replace_scope"] == "single_code_line"
    assert any(
        rule.get("line") == 2 and rule["kind"] == "must_contain_code_line_at"
        for rule in item["validators"]
    )
