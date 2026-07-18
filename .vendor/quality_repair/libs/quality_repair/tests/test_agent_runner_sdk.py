import sys
from pathlib import Path

from libs.quality_repair.agent import runner_workspace
from libs.quality_repair.agent.runner import ClaudeSDKRunner
from libs.quality_repair.schemas import Budget


def test_runner_sdk_missing_degrades(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())
    assert report.error == "claude_agent_sdk_unavailable"
    assert report.changed is False


def test_runner_preserves_sdk_result_error_detail(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")

    class FakeSDK(_BaseFakeSDK):
        class ResultMessage:
            subtype = "success"
            num_turns = 1
            usage = {"input_tokens": 0, "output_tokens": 0}
            total_cost_usd = 0
            is_error = True
            result = "Failed to authenticate. API Error: 403 no access"
            api_error_status = 403
            errors = None

        @staticmethod
        async def query(prompt, options):
            yield FakeSDK.ResultMessage()
            raise RuntimeError("trailing process error")

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error == "claude_sdk_result_error:http_403:Failed to authenticate. API Error: 403 no access"
    assert report.changed is False
    assert report.transcript_path is not None
    assert report.transcript_path.exists()


def test_runner_uses_private_env_model_without_leaking_to_child_env(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    env_file = tmp_path / "sdk.env"
    env_file.write_text("ANTHROPIC_BASE_URL=https://sdk.example.invalid\nANTHROPIC_API_" "KEY=api-key-value\nQUALITY_REPAIR_SDK_MODEL=gemini-3.5-flash-high\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("QUALITY_REPAIR_SDK_ENV", str(env_file))
    captured: dict = {}

    class FakeSDK(_BaseFakeSDK):
        class ClaudeAgentOptions:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.__dict__.update(kwargs)

        @staticmethod
        async def query(prompt, options):
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert captured["model"] == "gemini-3.5-flash-high"
    assert captured["env"] == {"ANTHROPIC_BASE_URL": "https://sdk.example.invalid", "ANTHROPIC_API_KEY": "api-key-value"}
    assert "effort" not in captured
    assert "thinking" not in captured
    assert "max_thinking_tokens" not in captured


def test_runner_sdk_options_disable_subagents(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    env_file = tmp_path / "sdk.env"
    env_file.write_text("ANTHROPIC_API_" "KEY=api-key-value\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("QUALITY_REPAIR_SDK_ENV", str(env_file))
    captured: dict = {}

    class FakeSDK(_BaseFakeSDK):
        class ClaudeAgentOptions:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        @staticmethod
        async def query(prompt, options):
            captured["system_prompt"] = options.system_prompt
            captured["hooks"] = options.hooks
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert captured["tools"] == ["Read", "Edit"]
    assert captured["allowed_tools"] == ["Read", "Edit"]
    assert "Agent" in captured["disallowed_tools"]
    assert "Task" in captured["disallowed_tools"]
    assert "Bash" in captured["disallowed_tools"]
    assert "Write" in captured["disallowed_tools"]
    assert "Grep" in captured["disallowed_tools"]
    assert "Glob" in captured["disallowed_tools"]
    assert captured["mcp_servers"] == {}
    assert captured["strict_mcp_config"] is True
    assert captured["setting_sources"] == []
    assert captured["skills"] == []
    assert set(captured["hooks"]) == {"PreToolUse"}
    hook_matchers = captured["hooks"]["PreToolUse"]
    assert {matcher.matcher for matcher in hook_matchers} == {"Read", "Edit"}
    assert str(tmp_path / "layout_issue_digest.json") in captured["system_prompt"]
    assert str(tmp_path / "candidate.py") in captured["system_prompt"]
    assert "Use short exact old_string snippets" in captured["system_prompt"]
    assert "after a strong improvement, stop and let the checker decide" in captured["system_prompt"]
    assert "or absolute paths" not in captured["system_prompt"]
    assert "Do not use /workspace paths" in captured["system_prompt"]
    assert "layout_issue_digest.json" in captured["system_prompt"]
    assert "candidate_anchor_windows.md" not in captured["system_prompt"]
    assert f"read {tmp_path / 'candidate.py'} once" in captured["system_prompt"]
    assert "agent_safety_contract.json" not in captured["system_prompt"]
    assert "Do not write analysis" in captured["system_prompt"]
    assert "compact JSON only" in captured["system_prompt"]
    assert "need_more_evidence" not in captured["system_prompt"]
    assert "layout_repair_contract.json" not in captured["system_prompt"]
    assert "offset and limit" not in captured["system_prompt"]


def test_runner_sdk_options_use_core_candidate_when_available(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n", encoding="utf-8")
    (tmp_path / "candidate_prelude.txt").write_text("from manim import *\n\n", encoding="utf-8")
    (tmp_path / "core_candidate.py").write_text("class Solution(Scene):\n    def construct(self):\n        self.wait()\n", encoding="utf-8")
    (tmp_path / "candidate_core_map.json").write_text('{"enabled":true,"scene_class":"Solution","core_start_line":3}', encoding="utf-8")
    captured: dict = {}

    class FakeSDK(_BaseFakeSDK):
        class ClaudeAgentOptions:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.__dict__.update(kwargs)

        @staticmethod
        async def query(prompt, options):
            captured["system_prompt"] = options.system_prompt
            captured["hooks"] = options.hooks
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert str(tmp_path / "layout_issue_digest.json") in captured["system_prompt"]
    assert str(tmp_path / "core_candidate.py") in captured["system_prompt"]
    assert "Only edit the absolute file path" in captured["system_prompt"]
    assert "Do not use /workspace paths" in captured["system_prompt"]
    assert "or absolute paths" not in captured["system_prompt"]
    assert "candidate.py will be composed and checked automatically" in captured["system_prompt"]


def test_runner_persists_exact_prompt_and_usage_breakdown(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")

    class FakeSDK(_BaseFakeSDK):
        class ResultMessage:
            num_turns = 1
            usage = {
                "input_tokens": 120,
                "output_tokens": 30,
                "cache_creation_input_tokens": 11,
                "cache_read_input_tokens": 22,
            }
            total_cost_usd = 0.25
            is_error = False

        @staticmethod
        async def query(prompt, options):
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "exact sdk prompt", Budget())

    assert report.error is None
    assert report.tokens_used == 150
    assert report.usage["input_tokens"] == 120
    assert report.usage["output_tokens"] == 30
    assert report.usage["cache_creation_input_tokens"] == 11
    assert report.usage["cache_read_input_tokens"] == 22
    assert (tmp_path / "sdk_prompt_latest.md").read_text(encoding="utf-8") == "exact sdk prompt"


def test_runner_preserves_final_assistant_text(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")

    class FakeSDK(_BaseFakeSDK):
        class TextBlock(_BaseFakeSDK.TextBlock):
            text = '{"action":"no_fix","confidence":0.7}'

        class AssistantMessage:
            content: list = []
            usage: dict = {}

        @staticmethod
        async def query(prompt, options):
            yield FakeSDK.AssistantMessage()
            yield FakeSDK.ResultMessage()

    FakeSDK.AssistantMessage.content = [FakeSDK.TextBlock()]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert report.final_text == '{"action":"no_fix","confidence":0.7}'


def test_runner_allows_full_read_layout_repairs_without_expanded_turn_budget(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "libs.quality_repair.agent.runner._load_persistent_sdk_env", lambda: {}
    )
    captured: dict = {}

    class FakeSDK(_BaseFakeSDK):
        class ClaudeAgentOptions:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.__dict__.update(kwargs)

        @staticmethod
        async def query(prompt, options):
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(
        tmp_path, "fix it", Budget(token_hard_cap=12_345)
    )

    assert report.error is None
    assert captured["max_turns"] == 14
    assert captured["task_budget"] == {"total": 12_345}


def test_runner_hides_tool_config_while_sdk_runs(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tool_config.json").write_text('{"check_cmd":[]}', encoding="utf-8")
    seen: dict[str, bool] = {}

    class FakeSDK(_BaseFakeSDK):
        @staticmethod
        async def query(prompt, options):
            seen["tool_config_visible"] = (Path(options.cwd) / "tool_config.json").exists()
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert seen["tool_config_visible"] is False
    assert (tmp_path / "tool_config.json").exists()


def test_runner_no_longer_mirrors_workspace_absolute_paths(tmp_path: Path, monkeypatch):
    (tmp_path / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(runner_workspace, "WORKSPACE_ROOT", workspace)
    seen: dict[str, bool] = {}

    class FakeSDK(_BaseFakeSDK):
        @staticmethod
        async def query(prompt, options):
            seen["workspace_visible"] = workspace.exists()
            yield FakeSDK.ResultMessage()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", FakeSDK)

    report = ClaudeSDKRunner().run(tmp_path, "fix it", Budget())

    assert report.error is None
    assert seen["workspace_visible"] is False
    assert not workspace.exists()


class _BaseFakeSDK:
    class AssistantMessage:
        content: list = []
        usage: dict = {}

    class ToolUseBlock:
        name = "Read"

    class ToolResultBlock:
        tool_use_id = "t1"
        content = ""
        is_error = False

    class TextBlock:
        text = ""

    class UserMessage:
        content = ""

    class ResultMessage:
        num_turns = 1
        usage = {"input_tokens": 1, "output_tokens": 1}
        total_cost_usd = 0
        is_error = False

    class ClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HookMatcher:
        def __init__(self, matcher=None, hooks=None, timeout=None):
            self.matcher = matcher
            self.hooks = hooks or []
            self.timeout = timeout
