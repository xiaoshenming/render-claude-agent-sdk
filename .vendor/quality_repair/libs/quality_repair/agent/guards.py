"""agent.guards — 禁改区守卫（纯逻辑，不 import claude_agent_sdk）。

check_edit 是纯函数（可无 mock 单测）；make_pre_tool_use_hook 把它包成
Claude SDK PreToolUse 钩子，只走 dict 协议，不依赖 SDK 类型。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

# 简单字面量：单引号或双引号，不跨行、不含转义（raw/三引号忽略）。
_LITERAL_RE = re.compile(r"'[^'\\\n]*'|\"[^\"\\\n]*\"")
_SMART_QUOTES = {"“": "U+201C", "”": "U+201D", "‘": "U+2018", "’": "U+2019"}

PreToolUseHook = Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]


def _extract_literals(text: str) -> set[str]:
    return set(_LITERAL_RE.findall(text))


def check_edit(old_string: str, new_string: str, protected: dict) -> tuple[bool, str]:
    """判定一次 Edit 是否触碰禁改区。返回 (allowed, reason)。"""
    for quote, codepoint in _SMART_QUOTES.items():
        if new_string.count(quote) > old_string.count(quote):
            return False, f"smart_quote_introduced:{codepoint}"

    for pat in protected.get("forbidden_patterns", []):
        if pat in old_string and new_string.count(pat) < old_string.count(pat):
            return False, f"protected_pattern_removed:{pat}"

    if protected.get("protect_string_literals"):
        missing = {
            item
            for item in _extract_literals(old_string) - _extract_literals(new_string)
            if _literal_value(item).strip()
        }
        if missing:
            lost = sorted(missing)[0]
            return False, f"string_literal_removed:{lost}"

    if protected.get("protect_comment_lines"):
        old_comments = _comment_lines(old_string)
        new_comments = set(_comment_lines(new_string))
        for comment in old_comments:
            if comment not in new_comments:
                return False, f"comment_line_changed:{comment[:80]}"

    return True, ""


def _literal_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _comment_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.lstrip().startswith("#") and line.strip()]


def make_pre_tool_use_hook(protected: dict) -> PreToolUseHook:
    """返回 async PreToolUse 钩子；deny 时给出 permissionDecision dict。"""
    workdir = Path(str(protected["workdir"])).resolve() if protected.get("workdir") else None
    editable_files = {_config_path(item) for item in protected.get("editable_files", [])}
    phase_state = protected.get("phase_state") if isinstance(protected.get("phase_state"), dict) else None

    async def _hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {}) if isinstance(input_data, dict) else {}
        if editable_files:
            target = _normalize_read_path(str(tool_input.get("file_path") or tool_input.get("filePath") or ""), workdir)
            if not target:
                return _deny("edit_path_missing")
            if target not in editable_files:
                return _deny(f"edit_path_denied:{target}")
        edit_ops = _extract_edit_operations(tool_input)
        if not edit_ops:
            return {}
        for old_string, new_string, _ in edit_ops:
            allowed, reason = check_edit(old_string, new_string, protected)
            if not allowed:
                return _deny(reason)
        if protected.get("validate_python_syntax") and workdir is not None and target in {"candidate.py", "core_candidate.py"}:
            ok, reason = _check_python_syntax_after_edit(workdir / target, edit_ops)
            if not ok:
                return _deny(reason)
        if phase_state is not None:
            phase_state["edit_started"] = True
        return {}

    return _hook


def make_read_tool_guard(config: dict) -> PreToolUseHook:
    """Allow workdir reads/searches; block path hunts outside workdir."""
    workdir = Path(str(config["workdir"])).resolve() if config.get("workdir") else None
    allowed_files = {_config_path(item) for item in config.get("allowed_files", [])}
    allowed_prefixes = tuple(_config_path(item) for item in config.get("allowed_prefixes", []))
    denied_files = {_config_path(item) for item in config.get("denied_files", [])}
    denied_prefixes = tuple(_config_path(item) for item in config.get("denied_prefixes", []))
    max_read_calls = _optional_int(config.get("max_read_calls"))
    max_candidate_reads = _optional_int(config.get("max_candidate_reads"))
    max_candidate_reads_after_edit = _optional_int(config.get("max_candidate_reads_after_edit"))
    max_grep_calls = _optional_int(config.get("max_grep_calls"))
    max_glob_calls = _optional_int(config.get("max_glob_calls"))
    phase_state = config.get("phase_state") if isinstance(config.get("phase_state"), dict) else None
    read_calls = 0
    candidate_reads = 0
    post_edit_candidate_reads = 0
    grep_calls = 0
    glob_calls = 0

    async def _hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        nonlocal read_calls, candidate_reads, post_edit_candidate_reads, grep_calls, glob_calls
        tool_input = input_data.get("tool_input", {}) if isinstance(input_data, dict) else {}
        pattern = str(tool_input.get("pattern") or "")
        raw_path = str(tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path") or "")
        path = _normalize_read_path(raw_path, workdir)
        if path == "" and raw_path.strip() in {".", "./"}:
            path = "."
        if path is None:
            return _deny("absolute_read_path_denied")
        if not path:
            return {}
        if pattern and (path == "." or path == "") and _broad_search_pattern(pattern):
            return _deny("broad_grep_path_denied")
        if path in denied_files or any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/") for prefix in denied_prefixes):
            return _deny(f"read_path_denied:{path}")
        if allowed_files or allowed_prefixes:
            if path in allowed_files or any(path.startswith(prefix.rstrip("/") + "/") for prefix in allowed_prefixes):
                budget_denial = _read_budget_denial(
                    tool_input=tool_input,
                    path=path,
                    edit_started=bool(phase_state and phase_state.get("edit_started")),
                    max_read_calls=max_read_calls,
                    max_candidate_reads=max_candidate_reads,
                    max_candidate_reads_after_edit=max_candidate_reads_after_edit,
                    max_grep_calls=max_grep_calls,
                    max_glob_calls=max_glob_calls,
                    read_calls=read_calls,
                    candidate_reads=candidate_reads,
                    post_edit_candidate_reads=post_edit_candidate_reads,
                    grep_calls=grep_calls,
                    glob_calls=glob_calls,
                )
                if budget_denial:
                    return _deny(budget_denial)
                read_calls, candidate_reads, grep_calls, glob_calls = _increment_read_budget(
                    tool_input=tool_input,
                    path=path,
                    read_calls=read_calls,
                    candidate_reads=candidate_reads,
                    grep_calls=grep_calls,
                    glob_calls=glob_calls,
                )
                if _is_post_edit_candidate_read(tool_input, path, phase_state):
                    post_edit_candidate_reads += 1
                return {}
            return _deny(f"read_path_not_allowed:{path}")
        budget_denial = _read_budget_denial(
            tool_input=tool_input,
            path=path,
            edit_started=bool(phase_state and phase_state.get("edit_started")),
            max_read_calls=max_read_calls,
            max_candidate_reads=max_candidate_reads,
            max_candidate_reads_after_edit=max_candidate_reads_after_edit,
            max_grep_calls=max_grep_calls,
            max_glob_calls=max_glob_calls,
            read_calls=read_calls,
            candidate_reads=candidate_reads,
            post_edit_candidate_reads=post_edit_candidate_reads,
            grep_calls=grep_calls,
            glob_calls=glob_calls,
        )
        if budget_denial:
            return _deny(budget_denial)
        read_calls, candidate_reads, grep_calls, glob_calls = _increment_read_budget(
            tool_input=tool_input,
            path=path,
            read_calls=read_calls,
            candidate_reads=candidate_reads,
            grep_calls=grep_calls,
            glob_calls=glob_calls,
        )
        if _is_post_edit_candidate_read(tool_input, path, phase_state):
            post_edit_candidate_reads += 1
        return {}

    return _hook


def _read_budget_denial(
    *,
    tool_input: dict[str, Any],
    path: str,
    edit_started: bool,
    max_read_calls: int | None,
    max_candidate_reads: int | None,
    max_candidate_reads_after_edit: int | None,
    max_grep_calls: int | None,
    max_glob_calls: int | None,
    read_calls: int,
    candidate_reads: int,
    post_edit_candidate_reads: int,
    grep_calls: int,
    glob_calls: int,
) -> str | None:
    kind = _read_tool_kind(tool_input)
    if edit_started:
        if (
            kind == "read"
            and path in {"candidate.py", "core_candidate.py"}
            and max_candidate_reads_after_edit is not None
            and post_edit_candidate_reads >= max_candidate_reads_after_edit
        ):
            return f"post_edit_candidate_read_budget_exhausted:{max_candidate_reads_after_edit}:edit_current_source_or_return_compact_json"
        return None
    if kind == "read" and path in {"candidate.py", "core_candidate.py"} and max_candidate_reads is not None and candidate_reads >= max_candidate_reads:
        return f"candidate_read_budget_exhausted:{max_candidate_reads}:edit_candidate_py_or_return_compact_json"
    if kind == "grep" and max_grep_calls is not None and grep_calls >= max_grep_calls:
        return f"grep_budget_exhausted:{max_grep_calls}:edit_candidate_py_or_return_compact_json"
    if kind == "glob" and max_glob_calls is not None and glob_calls >= max_glob_calls:
        return f"glob_budget_exhausted:{max_glob_calls}:edit_candidate_py_or_return_compact_json"
    if kind == "read":
        if max_read_calls is not None and read_calls >= max_read_calls:
            return f"read_budget_exhausted:{max_read_calls}:edit_candidate_py_or_return_compact_json"
    return None


def _increment_read_budget(
    *,
    tool_input: dict[str, Any],
    path: str,
    read_calls: int,
    candidate_reads: int,
    grep_calls: int,
    glob_calls: int,
) -> tuple[int, int, int, int]:
    kind = _read_tool_kind(tool_input)
    if kind == "grep":
        return read_calls, candidate_reads, grep_calls + 1, glob_calls
    if kind == "glob":
        return read_calls, candidate_reads, grep_calls, glob_calls + 1
    candidate_reads += 1 if path in {"candidate.py", "core_candidate.py"} else 0
    return read_calls + 1, candidate_reads, grep_calls, glob_calls


def _is_post_edit_candidate_read(tool_input: dict[str, Any], path: str, phase_state: dict[str, Any] | None) -> bool:
    return (
        bool(phase_state and phase_state.get("edit_started"))
        and _read_tool_kind(tool_input) == "read"
        and path in {"candidate.py", "core_candidate.py"}
    )


def _read_tool_kind(tool_input: dict[str, Any]) -> str:
    if tool_input.get("file_path") or tool_input.get("filePath"):
        return "read"
    if tool_input.get("pattern") and tool_input.get("path"):
        return "grep"
    if tool_input.get("pattern"):
        return "glob"
    return "read"


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _broad_search_pattern(pattern: str) -> bool:
    text = pattern.strip()
    return text in {"", ".", "*", ".*", ".+", "\\w+", "[\\s\\S]*", "layout_context", "bbox"}


def _config_path(value: Any) -> str:
    text = str(value).replace("\\", "/").strip()
    if text in {".", "./"}:
        return "."
    return text.lstrip("./")


def _extract_edit_pairs(tool_input: dict[str, Any]) -> list[tuple[str, str]]:
    return [(old_string, new_string) for old_string, new_string, _ in _extract_edit_operations(tool_input)]


def _extract_edit_operations(tool_input: dict[str, Any]) -> list[tuple[str, str, bool]]:
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        pairs: list[tuple[str, str, bool]] = []
        for item in edits:
            if not isinstance(item, dict):
                continue
            old_string = item.get("old_string", item.get("oldString", ""))
            new_string = item.get("new_string", item.get("newString", ""))
            replace_all = bool(item.get("replace_all", item.get("replaceAll", False)))
            pairs.append((str(old_string), str(new_string), replace_all))
        return pairs
    old_string = tool_input.get("old_string", tool_input.get("oldString", ""))
    new_string = tool_input.get("new_string", tool_input.get("newString", ""))
    if old_string or new_string:
        replace_all = bool(tool_input.get("replace_all", tool_input.get("replaceAll", False)))
        return [(str(old_string), str(new_string), replace_all)]
    return []


def _check_python_syntax_after_edit(path: Path, edit_ops: list[tuple[str, str, bool]]) -> tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True, ""
    for old_string, new_string, replace_all in edit_ops:
        if old_string not in text:
            return True, ""
        text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return False, f"python_syntax_error_after_edit:{exc.lineno}:{exc.msg}"
    return True, ""


def _normalize_read_path(raw_path: str, workdir: Path | None) -> str | None:
    path = raw_path.replace("\\", "/")
    if not path:
        return path
    raw = Path(raw_path)
    if not raw.is_absolute():
        if workdir is None:
            return raw.as_posix().lstrip("./")
        resolved = (workdir / raw).resolve()
    else:
        resolved = raw.resolve()
    if workdir is None:
        return None if raw.is_absolute() else raw.as_posix().lstrip("./")
    try:
        return resolved.relative_to(workdir).as_posix()
    except ValueError:
        return None


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
