"""Source-level non-geometry findings for generated logic contracts."""

from __future__ import annotations

import io
import re
import tokenize

from .source_utils import LATEX_COMMAND_RE, string_prefix


def unescaped_latex_findings(source: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    lines = source.splitlines()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue
            line = lines[token.start[0] - 1] if 1 <= token.start[0] <= len(lines) else ""
            if "make_formula" in line:
                continue
            prefix = string_prefix(token.string)
            command = LATEX_COMMAND_RE.search(token.string)
            if command and "r" not in prefix.lower() and re.search(r"[\u4e00-\u9fff]", token.string):
                findings.append({"kind": "unescaped_latex_command", "line": token.start[0], "command": command.group(0)})
    except tokenize.TokenError:
        return findings
    return findings


def lifecycle_findings(source: str) -> list[dict[str, object]]:
    add_count = len(re.findall(r"geometry_all\.add\(", source))
    fade_count = len(re.findall(r"FadeOut\(geometry_all|FadeOut\(region_|FadeOut\(aux_", source))
    if add_count >= 2 and fade_count == 0:
        return [{"kind": "geometry_lifecycle_risk", "reason": "geometry_all accumulates auxiliary objects without matching FadeOut"}]
    return []


def latex_contracts(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "kind": "no_unescaped_latex_command",
            "line": item["line"],
            "text": item["command"],
            "label": "Python string must not corrupt LaTeX command",
        }
        for item in findings
    ]
