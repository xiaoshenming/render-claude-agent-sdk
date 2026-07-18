"""Human-readable source-region report builder."""

from __future__ import annotations


def source_region(
    source: str,
    contracts: list[dict[str, object]],
    findings: list[dict[str, object]],
    notes: list[str],
) -> str:
    line_refs = sorted(
        {
            int(value)
            for item in contracts + findings
            for value in (item.get("line"), item.get("source_line"), item.get("line_no"))
            if isinstance(value, int)
        }
    )
    lines = source.splitlines()
    snippets = []
    for line_no in line_refs[:8]:
        start = max(1, line_no - 2)
        end = min(len(lines), line_no + 2)
        snippets.append("\n".join(f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1)))
    body = "\n\n".join(snippets) if snippets else "No narrow source line issue; generated from deterministic template evidence."
    finding_block = "\n".join(f"- {line}" for line in finding_summary_lines(findings))
    notes_block = "\n".join(f"- {note}" for note in notes)
    return (
        "# 自动逻辑合同源码区域\n\n"
        "## 审查发现\n\n"
        + (finding_block or "- 无自动审查发现。")
        + "\n\n## 模板说明\n\n"
        + (notes_block or "- 无。")
        + "\n\n## 相关源码片段\n\n"
        + body
        + "\n"
    )


def finding_summary_lines(findings: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for finding in findings[:12]:
        kind = finding.get("kind", "issue")
        line = finding.get("source_line") or finding.get("line")
        target = finding.get("target") or "".join(str(item) for item in finding.get("points", []))
        hint = finding.get("repair_hint") or finding.get("reason") or ""
        suggested = finding.get("suggested_replacement")
        parts = [str(kind)]
        if target:
            parts.append(f"target={target}")
        if line:
            parts.append(f"line={line}")
        if suggested:
            parts.append(f"suggested_replacement={suggested}")
        if hint:
            parts.append(f"hint={hint}")
        lines.append("; ".join(parts))
    return lines
