"""guards.py 纯逻辑单测（无 mock）+ hook dict 协议双分支。"""

from __future__ import annotations

import asyncio

from libs.quality_repair.agent.guards import check_edit, make_pre_tool_use_hook, make_read_tool_guard


def test_forbidden_pattern_removed_is_denied():
    protected = {"forbidden_patterns": ["show_text("]}
    old = "self.show_text('a', 'title')\nself.show_text('b', '1')\n"
    new = "self.show_text('a', 'title')\n"  # 一处 show_text( 被删
    allowed, reason = check_edit(old, new, protected)
    assert allowed is False
    assert reason == "protected_pattern_removed:show_text("


def test_forbidden_pattern_preserved_is_allowed():
    protected = {"forbidden_patterns": ["show_text("]}
    old = "self.show_text('a', 'title')\n"
    new = "self.show_text('a', 'title', font_size=40)\n"  # 次数不减
    allowed, reason = check_edit(old, new, protected)
    assert allowed is True
    assert reason == ""


def test_string_literal_lost_is_denied():
    protected = {"protect_string_literals": True}
    old = "label = MathTex('x^2 + y^2')\n"
    new = "label = MathTex('x^2')\n"  # 原字面量丢失
    allowed, reason = check_edit(old, new, protected)
    assert allowed is False
    assert reason.startswith("string_literal_removed:")


def test_whitespace_only_spacer_literal_removed_is_allowed_for_layout_edits():
    protected = {"protect_string_literals": True}
    old = 'row = make_formula_row("A. 5", "    ", "B. 2")\n'
    new = 'row = make_formula_row("A. 5", "B. 2")\n'
    allowed, reason = check_edit(old, new, protected)
    assert allowed is True
    assert reason == ""


def test_string_literal_added_is_allowed():
    protected = {"protect_string_literals": True}
    old = "t = Text('hello')\n"
    new = "t = Text('hello')\nq = Text('world')\n"  # 只新增
    allowed, reason = check_edit(old, new, protected)
    assert allowed is True
    assert reason == ""


def test_no_protection_config_allows():
    allowed, reason = check_edit("a = 1", "a = 2", {})
    assert allowed is True
    assert reason == ""


def test_smart_quote_introduction_is_denied():
    old = "lines = [\"已知 AC 平分 ∠DCB\"]\n"
    new = "lines = [“已知 AC 平分 ∠DCB”]\n"
    allowed, reason = check_edit(old, new, {})
    assert allowed is False
    assert reason == "smart_quote_introduced:U+201C"


def test_existing_smart_quote_text_is_not_denied_when_preserved():
    old = "label = Text(\"他说“相等”\")\n"
    new = "label = Text(\"他说“相等”\").scale(0.9)\n"
    allowed, reason = check_edit(old, new, {})
    assert allowed is True
    assert reason == ""


def _run(coro):
    return asyncio.run(coro)


def test_hook_deny_branch_dict_protocol():
    hook = make_pre_tool_use_hook({"forbidden_patterns": ["def construct"]})
    input_data = {
        "tool_input": {
            "old_string": "def construct(self):\n    pass\n",
            "new_string": "    pass\n",
        }
    }
    out = _run(hook(input_data, "tool-1", object()))
    assert out == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "protected_pattern_removed:def construct",
        }
    }


def test_hook_allow_branch_returns_empty_dict():
    hook = make_pre_tool_use_hook({"forbidden_patterns": ["def construct"]})
    input_data = {
        "tool_input": {
            "old_string": "x = 1\n",
            "new_string": "x = 2\n",
        }
    }
    out = _run(hook(input_data, "tool-2", object()))
    assert out == {}


def test_hook_does_not_limit_edit_call_count():
    hook = make_pre_tool_use_hook({})
    input_data = {
        "tool_input": {
            "old_string": "x = 1\n",
            "new_string": "x = 2\n",
        }
    }

    first = _run(hook(input_data, "tool-1", object()))
    second = _run(hook(input_data, "tool-2", object()))

    assert first == {}
    assert second == {}


def test_hook_applies_protected_rules_to_edit_entry():
    hook = make_pre_tool_use_hook({"protect_string_literals": True})
    out = _run(
        hook(
            {
                "tool_input": {
                    "old_string": "label = Text('重要内容')\n",
                    "new_string": "label = Text('删掉')\n",
                }
            },
            "tool-1",
            object(),
        )
    )

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("string_literal_removed:")


def test_hook_malformed_input_fails_open_allow():
    hook = make_pre_tool_use_hook({"forbidden_patterns": ["a"]})
    out = _run(hook({}, None, object()))  # 缺 tool_input
    assert out == {}


def test_edit_hook_denies_files_other_than_candidate(tmp_path):
    hook = make_pre_tool_use_hook({"workdir": str(tmp_path), "editable_files": ["candidate.py"]})

    allowed = _run(
        hook(
            {"tool_input": {"file_path": "candidate.py", "old_string": "x = 1\n", "new_string": "x = 2\n"}},
            "edit-1",
            object(),
        )
    )
    denied = _run(
        hook(
            {"tool_input": {"file_path": "layout_issue_digest.json", "old_string": "x", "new_string": "y"}},
            "edit-2",
            object(),
        )
    )

    assert allowed == {}
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "edit_path_denied:layout_issue_digest.json"


def test_edit_hook_denies_python_syntax_error_when_configured(tmp_path):
    (tmp_path / "candidate.py").write_text("def make_panel():\n    return panel\n", encoding="utf-8")
    hook = make_pre_tool_use_hook(
        {"workdir": str(tmp_path), "editable_files": ["candidate.py"], "validate_python_syntax": True}
    )

    out = _run(
        hook(
            {
                "tool_input": {
                    "file_path": "candidate.py",
                    "old_string": "    return panel\n",
                    "new_string": "    return panel panel\n",
                }
            },
            "edit-1",
            object(),
        )
    )

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("python_syntax_error_after_edit:")


def test_edit_hook_denies_core_candidate_python_syntax_error_when_configured(tmp_path):
    (tmp_path / "core_candidate.py").write_text("class Solution:\n    def construct(self):\n        self.wait()\n", encoding="utf-8")
    hook = make_pre_tool_use_hook(
        {"workdir": str(tmp_path), "editable_files": ["core_candidate.py"], "validate_python_syntax": True}
    )

    out = _run(
        hook(
            {
                "tool_input": {
                    "file_path": "core_candidate.py",
                    "old_string": "        self.wait()\n",
                    "new_string": "        self.wait(2\n",
                }
            },
            "edit-1",
            object(),
        )
    )

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("python_syntax_error_after_edit:")


def test_edit_hook_can_protect_comment_lines(tmp_path):
    (tmp_path / "candidate.py").write_text("# 35. “中文注释”\nx = 1\n", encoding="utf-8")
    hook = make_pre_tool_use_hook(
        {"workdir": str(tmp_path), "editable_files": ["candidate.py"], "protect_comment_lines": True}
    )

    out = _run(
        hook(
            {
                "tool_input": {
                    "file_path": "candidate.py",
                    "old_string": "# 35. “中文注释”\nx = 1\n",
                    "new_string": "# 35. “the 注释”\nx = 1\n",
                }
            },
            "edit-1",
            object(),
        )
    )

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("comment_line_changed:")


def test_read_budget_is_released_after_edit_starts(tmp_path):
    phase_state: dict[str, bool] = {}
    read_hook = make_read_tool_guard(
        {
            "allowed_files": ["candidate.py", "layout_issue_digest.json"],
            "max_read_calls": 2,
            "max_candidate_reads": 1,
            "max_candidate_reads_after_edit": 1,
            "phase_state": phase_state,
        }
    )
    edit_hook = make_pre_tool_use_hook({"phase_state": phase_state})
    candidate_read = {"tool_input": {"file_path": "candidate.py"}}
    digest_read = {"tool_input": {"file_path": "layout_issue_digest.json"}}

    assert _run(read_hook(digest_read, "read-1", object())) == {}
    assert _run(read_hook(candidate_read, "read-2", object())) == {}
    denied = _run(read_hook(candidate_read, "read-3", object()))
    assert denied["hookSpecificOutput"]["permissionDecisionReason"].startswith("candidate_read_budget_exhausted:")
    assert _run(edit_hook({"tool_input": {"old_string": "x = 1", "new_string": "x = 2"}}, "edit-1", object())) == {}
    assert _run(read_hook(digest_read, "read-4", object())) == {}
    assert _run(read_hook(candidate_read, "read-5", object())) == {}
    denied_after_edit = _run(read_hook(candidate_read, "read-6", object()))
    assert denied_after_edit["hookSpecificOutput"]["permissionDecisionReason"].startswith("post_edit_candidate_read_budget_exhausted:")


def test_read_hook_denies_absolute_paths():
    hook = make_read_tool_guard({"workdir": "/tmp/quality-repair-workdir"})
    out = _run(hook({"tool_input": {"file_path": "/tmp/outside/candidate.py", "offset": 1, "limit": 80}}, "read-1", object()))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"] == "absolute_read_path_denied"


def test_read_hook_denies_workspace_absolute_alias():
    hook = make_read_tool_guard({"workdir": "/tmp/quality-repair-workdir", "allowed_files": ["candidate.py", "layout_issue_digest.json"]})

    denied = _run(hook({"tool_input": {"file_path": "/workspace/layout_issue_digest.json"}}, "read-1", object()))

    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "absolute_read_path_denied"


def test_read_hook_allows_sdk_normalized_absolute_paths_inside_workdir(tmp_path):
    hook = make_read_tool_guard({"workdir": str(tmp_path)})

    brief = _run(hook({"tool_input": {"file_path": str(tmp_path / "layout_repair_brief.json")}}, "read-1", object()))
    candidate = _run(hook({"tool_input": {"file_path": str(tmp_path / "candidate.py")}}, "read-2", object()))

    assert brief == {}
    assert candidate == {}


def test_read_hook_allows_full_candidate_read_inside_workdir(tmp_path):
    hook = make_read_tool_guard({"workdir": str(tmp_path)})

    out = _run(hook({"tool_input": {"file_path": str(tmp_path / "candidate.py")}}, "read-1", object()))

    assert out == {}


def test_read_hook_allows_relative_full_candidate_read():
    hook = make_read_tool_guard({})
    out = _run(hook({"tool_input": {"file_path": "candidate.py"}}, "read-1", object()))

    assert out == {}


def test_read_hook_does_not_limit_repeated_candidate_reads():
    hook = make_read_tool_guard({})
    allowed = {"tool_input": {"file_path": "candidate.py"}}

    assert _run(hook(allowed, "read-1", object())) == {}
    assert _run(hook(allowed, "read-2", object())) == {}
    assert _run(hook(allowed, "read-3", object())) == {}


def test_read_hook_allows_repair_brief_contract_without_anchor():
    hook = make_read_tool_guard({})

    for file_path in ("layout_repair_brief.json", "layout_repair_contract.json"):
        assert _run(hook({"tool_input": {"file_path": file_path}}, "read-1", object())) == {}


def test_read_hook_with_allowlist_allows_only_digest_and_candidate():
    hook = make_read_tool_guard(
        {
            "allowed_files": ["candidate.py", "layout_issue_digest.json"],
            "allowed_prefixes": [],
            "denied_files": ["layout_context.json", "facts/layout_context.full.json"],
            "denied_prefixes": ["facts/"],
        }
    )

    assert _run(hook({"tool_input": {"file_path": "layout_issue_digest.json"}}, "read-1", object())) == {}
    assert _run(hook({"tool_input": {"file_path": "candidate.py"}}, "read-2", object())) == {}
    denied_root = _run(hook({"tool_input": {"file_path": "layout_context.json"}}, "read-3", object()))
    denied_full = _run(hook({"tool_input": {"file_path": "facts/layout_context.full.json"}}, "read-4", object()))
    denied_evidence = _run(hook({"tool_input": {"file_path": "evidence_queries/round_01/results.json"}}, "read-5", object()))
    denied_contract = _run(hook({"tool_input": {"file_path": "layout_repair_contract.json"}}, "read-6", object()))
    denied_other = _run(hook({"tool_input": {"file_path": "random.md"}}, "read-7", object()))

    assert denied_root["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_denied:layout_context.json"
    assert denied_full["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_denied:facts/layout_context.full.json"
    assert denied_evidence["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_not_allowed:evidence_queries/round_01/results.json"
    assert denied_contract["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_not_allowed:layout_repair_contract.json"
    assert denied_other["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_not_allowed:random.md"


def test_read_hook_with_core_allowlist_denies_full_candidate_and_prelude():
    hook = make_read_tool_guard(
        {
            "allowed_files": ["core_candidate.py", "layout_issue_digest.json"],
            "allowed_prefixes": [],
            "denied_files": ["candidate.py", "candidate_prelude.txt", "layout_context.json"],
            "denied_prefixes": ["facts/"],
            "max_candidate_reads": 1,
        }
    )

    assert _run(hook({"tool_input": {"file_path": "layout_issue_digest.json"}}, "read-1", object())) == {}
    assert _run(hook({"tool_input": {"file_path": "core_candidate.py"}}, "read-2", object())) == {}
    denied_full = _run(hook({"tool_input": {"file_path": "candidate.py"}}, "read-3", object()))
    denied_prelude = _run(hook({"tool_input": {"file_path": "candidate_prelude.txt"}}, "read-4", object()))
    denied_context = _run(hook({"tool_input": {"file_path": "facts/layout_context.full.json"}}, "read-5", object()))

    assert denied_full["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_denied:candidate.py"
    assert denied_prelude["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_denied:candidate_prelude.txt"
    assert denied_context["hookSpecificOutput"]["permissionDecisionReason"] == "read_path_denied:facts/layout_context.full.json"


def test_read_hook_enforces_candidate_read_budget_when_configured():
    hook = make_read_tool_guard({"allowed_files": ["candidate.py"], "max_candidate_reads": 1})
    allowed = {"tool_input": {"file_path": "candidate.py"}}

    assert _run(hook(allowed, "read-1", object())) == {}
    denied = _run(hook(allowed, "read-2", object()))

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == (
        "candidate_read_budget_exhausted:1:edit_candidate_py_or_return_compact_json"
    )


def test_read_hook_enforces_grep_budget_when_configured():
    hook = make_read_tool_guard({"allowed_files": ["."], "max_grep_calls": 1})
    grep = {"tool_input": {"path": ".", "pattern": "make_step_panel"}}

    assert _run(hook(grep, "grep-1", object())) == {}
    denied = _run(hook(grep, "grep-2", object()))

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "grep_budget_exhausted:1:edit_candidate_py_or_return_compact_json"


def test_read_hook_with_allowlist_allows_workspace_grep_path():
    hook = make_read_tool_guard(
        {
            "allowed_files": [".", "candidate.py"],
            "denied_files": ["layout_context.json"],
        }
    )

    assert _run(hook({"tool_input": {"path": ".", "pattern": "make_step_panel"}}, "grep-1", object())) == {}


def test_read_hook_with_allowlist_denies_broad_workspace_grep():
    hook = make_read_tool_guard(
        {
            "allowed_files": [".", "candidate.py"],
            "denied_files": ["layout_context.json"],
        }
    )

    denied = _run(hook({"tool_input": {"path": ".", "pattern": "bbox"}}, "grep-1", object()))

    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "broad_grep_path_denied"


def test_read_hook_guards_grep_glob_path_field(tmp_path):
    hook = make_read_tool_guard({"workdir": str(tmp_path)})

    allowed = _run(hook({"tool_input": {"path": str(tmp_path), "pattern": "make_step_panel"}}, "grep-1", object()))
    denied = _run(hook({"tool_input": {"path": "/etc", "pattern": "secret"}}, "grep-2", object()))

    assert allowed == {}
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "absolute_read_path_denied"
