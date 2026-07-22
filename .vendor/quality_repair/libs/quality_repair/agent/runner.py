"""Claude Agent SDK runner boundary for quality_repair."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core_candidate_view import CORE_CANDIDATE, PRELUDE, editable_candidate_path
from ..schemas import AgentRunReport, Budget
from .guards import make_pre_tool_use_hook, make_read_tool_guard
from .runner_env import SDK_PROCESS_ENV_KEYS, _load_persistent_sdk_env
from .runner_messages import SDKResultError as _SDKResultError
from .runner_messages import _consume_query, _run_coro, _write_transcript
from .runner_workspace import _hide_checker_config_during_sdk

_ALLOWED_TOOLS = ["Read", "Edit"]
_DISALLOWED_TOOLS = ["Agent", "Task", "Bash", "Write", "WebSearch", "WebFetch", "Grep", "Glob"]
def _system_prompt_for(editable_file: str, workdir: Path) -> str:
    issue_path = _abs_path(workdir, "layout_issue_digest.json")
    editable_path = _abs_path(workdir, editable_file)
    if editable_file != CORE_CANDIDATE:
        return (
            "You are a Manim layout repair agent. "
            f"Only read these exact absolute paths: {issue_path} and {editable_path}. "
            f"Only edit the absolute file path {editable_path}. "
            "Do not use /workspace paths, path aliases, commands, grep, glob, Agent/Task/subagents, or tools other than Read/Edit. "
            f"Read {issue_path} first, read {editable_path} once, then edit if the full issue list shows real source-fixable overlap. "
            "Use short exact old_string snippets for Edit. If an Edit fails because the source changed, reread the editable file once and retry with a smaller exact snippet. "
            "Group issues that share a source object, parent VGroup, or layout statement and fix the highest-impact shared cause first. "
            "Use multiple Edit calls for distinct source-fixable clusters. Do not stop after the first improvement; finish every clearly source-fixable blocking cluster in this pass, or name a specific unsafe-to-edit reason for each remainder. "
            f"If issue_count is nonzero and {editable_path} contains related panel/text/formula layout code, attempt a safe layout edit instead of generic no_fix. "
            "If a repeated Read is denied, use the latest source context already read; do not return no_fix because of read budget. "
            "Preserve text/formula/voiceover strings, math meaning, colors, animations, and teaching order. "
            "Return final compact JSON only after completing the safe repair pass or naming the specific source reason no safe edit remains. "
            "Do not write analysis, reasoning, markdown, code fences, or prose. Final visible text must be compact JSON only."
        )
    candidate_path = _abs_path(workdir, "candidate.py")
    prelude_path = _abs_path(workdir, PRELUDE)
    return (
        "You are a Manim layout repair agent. "
        f"Only read these exact absolute paths: {issue_path} and {editable_path}. "
        f"Only edit the absolute file path {editable_path}. "
        f"Do not read {candidate_path}, {prelude_path}, layout_context.json, facts, commands, grep, glob, or Agent/Task/subagents. Do not use /workspace paths. "
        f"Read {issue_path} first, read {editable_path} once, then edit if the full issue list shows real source-fixable overlap. "
        "candidate.py will be composed and checked automatically after your edit. "
        "Use short exact old_string snippets for Edit. If an Edit fails because the source changed, reread the editable file once and retry with a smaller exact snippet. "
        "Group issues that share a source object, parent VGroup, or layout statement and fix the highest-impact shared cause first. "
        "Use multiple Edit calls for distinct source-fixable clusters. Do not stop after the first improvement; finish every clearly source-fixable blocking cluster in this pass, or name a specific unsafe-to-edit reason for each remainder. "
        f"If issue_count is nonzero and {editable_path} contains related panel/text/formula layout code, attempt a safe layout edit instead of generic no_fix. "
        "If a repeated Read is denied, use the latest source context already read; do not return no_fix because of read budget. "
        "Preserve text/formula/voiceover strings, math meaning, colors, animations, and teaching order. "
        "Return final compact JSON only after completing the safe repair pass or naming the specific source reason no safe edit remains. "
        "Do not write analysis, reasoning, markdown, code fences, or prose. Final visible text must be compact JSON only."
    )


def _abs_path(workdir: Path, name: str) -> str:
    return str((workdir / name).resolve())


class ClaudeSDKRunner:
    """Default LLM executor: lets an SDK agent Read/Edit candidate.py in workdir."""

    name = "claude_sdk"

    def __init__(
        self,
        *,
        model: str | None = None,
        max_turns: int = 14,
        protected: dict | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._model = model
        self._max_turns = max_turns
        self._protected = protected
        self._system_prompt = system_prompt

    def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
        editable_file = editable_candidate_path(workdir)
        candidate = workdir / editable_file
        try:
            before = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            return AgentRunReport(changed=False, error=f"candidate_unreadable:{exc}")
        try:
            sdk_env = _load_persistent_sdk_env()
        except Exception as exc:  # noqa: BLE001 - do not leak env setup details beyond structured error
            return AgentRunReport(changed=False, error=str(exc))
        try:
            import claude_agent_sdk as sdk
        except ImportError:
            return AgentRunReport(changed=False, error="claude_agent_sdk_unavailable")
        try:
            return self._invoke(sdk, workdir, candidate, prompt, budget, before, sdk_env, editable_file)
        except Exception as exc:
            return AgentRunReport(changed=False, error=str(exc))

    def _build_options(self, sdk: Any, workdir: Path, budget: Budget, sdk_env: dict[str, str], editable_file: str) -> Any:
        options = sdk.ClaudeAgentOptions(
            cwd=str(workdir),
            tools=list(_ALLOWED_TOOLS),
            allowed_tools=list(_ALLOWED_TOOLS),
            disallowed_tools=list(_DISALLOWED_TOOLS),
            mcp_servers={},
            strict_mcp_config=True,
            permission_mode="acceptEdits",
            max_turns=self._max_turns,
            model=budget.model or self._model or sdk_env.get("QUALITY_REPAIR_SDK_MODEL"),
            setting_sources=[],
            skills=[],
            env={key: value for key, value in sdk_env.items() if key in SDK_PROCESS_ENV_KEYS},
        )
        options.system_prompt = self._system_prompt or _system_prompt_for(editable_file, workdir)
        phase_state: dict[str, Any] = {"edit_started": False}
        path_hook = make_read_tool_guard(
            {
                "workdir": str(workdir),
                "phase_state": phase_state,
                "allowed_files": [
                    editable_file,
                    "layout_issue_digest.json",
                ],
                "allowed_prefixes": [],
                "denied_files": [
                    "layout_context.json",
                    "facts/layout_context.json",
                    "facts/layout_context.full.json",
                    *(["candidate.py", PRELUDE] if editable_file == CORE_CANDIDATE else []),
                ],
                "denied_prefixes": ["facts/"],
                "max_read_calls": 4,
                "max_candidate_reads": 2,
                "max_candidate_reads_after_edit": 2,
            }
        )
        edit_hook = make_pre_tool_use_hook(
            {
                **(self._protected or {}),
                "workdir": str(workdir),
                "editable_files": [editable_file],
                "validate_python_syntax": True,
                "protect_comment_lines": True,
                "phase_state": phase_state,
            }
        )
        options.hooks = {
            "PreToolUse": [
                sdk.HookMatcher(matcher="Read", hooks=[path_hook]),
                sdk.HookMatcher(matcher="Edit", hooks=[edit_hook]),
            ]
        }
        return options

    def _invoke(
        self,
        sdk: Any,
        workdir: Path,
        candidate: Path,
        prompt: str,
        budget: Budget,
        before: str,
        sdk_env: dict[str, str],
        editable_file: str,
    ) -> AgentRunReport:
        options = self._build_options(sdk, workdir, budget, sdk_env, editable_file)
        transcript_path = workdir / "sdk_messages.jsonl"
        (workdir / "sdk_prompt_latest.md").write_text(prompt, encoding="utf-8")
        try:
            with _hide_checker_config_during_sdk(workdir):
                tokens, cost, tool_calls, records, usage, final_text = _run_coro(_consume_query(sdk, prompt, options))
        except _SDKResultError as exc:
            _write_transcript(transcript_path, exc.records)
            return AgentRunReport(
                changed=False,
                tokens_used=exc.tokens,
                cost_usd=exc.cost,
                transcript_path=transcript_path,
                tool_calls=exc.tool_calls,
                usage=exc.usage,
                final_text=exc.final_text,
                error=str(exc),
            )
        _write_transcript(transcript_path, records)
        after = candidate.read_text(encoding="utf-8")
        return AgentRunReport(
            changed=after != before,
            tokens_used=tokens,
            cost_usd=cost,
            transcript_path=transcript_path,
            tool_calls=tool_calls,
            usage=usage,
            final_text=final_text,
        )
