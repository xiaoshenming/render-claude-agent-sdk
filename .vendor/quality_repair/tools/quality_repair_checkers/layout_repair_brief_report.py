"""CLI/report helpers for layout repair brief generation."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from tools.quality_repair_checkers.layout_repair_brief_geometry import estimated_tokens, file_size
from tools.quality_repair_checkers.layout_repair_brief_model import build_layout_repair_brief, build_layout_repair_contract


def run_single(layout_context: Path, out_dir: Path) -> dict[str, Any]:
    context = read_json(layout_context)
    brief = build_layout_repair_brief(context, source_path=layout_context)
    contract = build_layout_repair_contract(brief)
    write_json(out_dir / "layout_repair_brief.json", brief)
    write_json(out_dir / "layout_repair_contract.json", contract)
    return summary_row(layout_context, brief, contract, out_dir)


def run_batch(batch_root: Path, out_dir: Path, batch_tag: str) -> dict[str, Any]:
    rows = []
    for layout_context in sorted(batch_root.glob(f"*/{batch_tag}/layout_context.json")):
        case_id = layout_context.parent.parent.name
        case_out = out_dir / case_id
        context = read_json(layout_context)
        brief = build_layout_repair_brief(context, case_id=case_id, source_path=layout_context)
        contract = build_layout_repair_contract(brief)
        write_json(case_out / "layout_repair_brief.json", brief)
        write_json(case_out / "layout_repair_contract.json", contract)
        rows.append(summary_row(layout_context, brief, contract, case_out))
    payload = {
        "schema_version": "quality_repair.layout_repair_brief_batch.v1",
        "batch_root": str(batch_root),
        "batch_tag": batch_tag,
        "out_dir": str(out_dir),
        "case_count": len(rows),
        "rows": rows,
        "totals": batch_totals(rows),
    }
    write_json(out_dir / "layout_repair_brief_batch_summary.json", payload)
    (out_dir / "layout_repair_brief_batch_report.md").write_text(batch_markdown(payload), encoding="utf-8")
    (out_dir / "layout_repair_brief_batch_report.html").write_text(batch_html(payload), encoding="utf-8")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def summary_row(layout_context: Path, brief: dict[str, Any], contract: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    brief_bytes = len(json.dumps(brief, ensure_ascii=False, default=str).encode("utf-8"))
    contract_bytes = len(json.dumps(contract, ensure_ascii=False, default=str).encode("utf-8"))
    full_bytes = file_size(layout_context) or 0
    old_summary = old_batch_summary(layout_context.parent / "batch_case_summary.json")
    candidate_path = layout_context.parent / "bundle" / "candidate.py"
    return {
        "case_id": brief.get("case_id"),
        "layout_context": str(layout_context),
        "brief": str(out_dir / "layout_repair_brief.json"),
        "contract": str(out_dir / "layout_repair_contract.json"),
        "blocking_count": brief.get("blocking_count"),
        "primary_failure_type": brief.get("summary", {}).get("primary_failure_type"),
        "primary_confidence": brief.get("summary", {}).get("primary_confidence"),
        "cluster_count": brief.get("summary", {}).get("cluster_count"),
        "full_bytes": full_bytes,
        "brief_bytes": brief_bytes,
        "contract_bytes": contract_bytes,
        "default_input_bytes": brief_bytes + contract_bytes,
        "compression_ratio": round(full_bytes / max(1, brief_bytes + contract_bytes), 2),
        "full_estimated_tokens": estimated_tokens(full_bytes),
        "default_estimated_tokens": estimated_tokens(brief_bytes + contract_bytes),
        "candidate_bytes": file_size(candidate_path),
        "old_tokens_used": old_summary.get("tokens_used"),
        "old_after_blocking": old_summary.get("after_blocking"),
        "old_repair_status": old_summary.get("repair_status"),
    }


def old_batch_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def batch_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    full = sum(int(row.get("full_bytes") or 0) for row in rows)
    default = sum(int(row.get("default_input_bytes") or 0) for row in rows)
    return {
        "full_bytes": full,
        "default_input_bytes": default,
        "compression_ratio": round(full / max(1, default), 2),
        "full_estimated_tokens": estimated_tokens(full),
        "default_estimated_tokens": estimated_tokens(default),
        "saved_estimated_tokens": (estimated_tokens(full) or 0) - (estimated_tokens(default) or 0),
    }


def batch_markdown(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", [])
    totals = payload.get("totals", {})
    lines = [
        "# Layout Repair Brief 旁路实验报告",
        "",
        f"- 样本目录：`{payload.get('batch_root')}`",
        f"- 基准批次：`{payload.get('batch_tag')}`",
        f"- 输出目录：`{payload.get('out_dir')}`",
        f"- 样本数：{payload.get('case_count')}",
        f"- full layout_context 合计：{totals.get('full_bytes')} bytes，约 {totals.get('full_estimated_tokens')} tokens",
        f"- brief+contract 合计：{totals.get('default_input_bytes')} bytes，约 {totals.get('default_estimated_tokens')} tokens",
        f"- 压缩倍率：{totals.get('compression_ratio')}x，约节省 {totals.get('saved_estimated_tokens')} tokens",
        "",
        "## 逐样本结果",
        "",
        "| case | blocking | failure_type | conf | full bytes | brief+contract | ratio | old tokens | old after |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(markdown_row(row) for row in rows)
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- 这轮只验证输入压缩和根因分类，不调用 SDK，不改变候选代码，不新增任何 hard gate。",
            "- 默认给 SDK 的输入可以从 full layout_context 降到 brief+contract；full context 应保留为审计和低置信度 fallback。",
            "- 真实能否提升修复成功率，还需要下一轮把 brief/contract 接入 workdir 后跑 SDK A/B。",
            "",
        ]
    )
    return "\n".join(lines)


def markdown_row(row: dict[str, Any]) -> str:
    return "| {case} | {blocking} | `{failure}` | {conf} | {full} | {default} | {ratio}x | {old_tokens} | {old_after} |".format(
        case=short_case(str(row.get("case_id") or "")),
        blocking=row.get("blocking_count"),
        failure=row.get("primary_failure_type"),
        conf=row.get("primary_confidence"),
        full=row.get("full_bytes"),
        default=row.get("default_input_bytes"),
        ratio=row.get("compression_ratio"),
        old_tokens=row.get("old_tokens_used"),
        old_after=row.get("old_after_blocking"),
    )


def batch_html(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", [])
    totals = payload.get("totals", {})
    row_html = "\n".join(html_row(row) for row in rows)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Layout Repair Brief 旁路实验报告</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; }}
    th {{ background: #f3f4f6; }}
    code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
    .metric {{ display: inline-block; margin-right: 18px; }}
  </style>
</head>
<body>
  <h1>Layout Repair Brief 旁路实验报告</h1>
  <p><span class="metric">样本数：{payload.get('case_count')}</span><span class="metric">压缩倍率：{totals.get('compression_ratio')}x</span><span class="metric">预计节省：{totals.get('saved_estimated_tokens')} tokens</span></p>
  <p>full layout_context: {totals.get('full_bytes')} bytes / 约 {totals.get('full_estimated_tokens')} tokens；brief+contract: {totals.get('default_input_bytes')} bytes / 约 {totals.get('default_estimated_tokens')} tokens。</p>
  <table>
    <thead><tr><th>case</th><th>blocking</th><th>failure_type</th><th>conf</th><th>full bytes</th><th>brief+contract</th><th>ratio</th><th>old tokens</th><th>old after</th></tr></thead>
    <tbody>{row_html}</tbody>
  </table>
  <p>本报告只验证输入压缩和根因分类，不调用 SDK，不修改 candidate.py，不新增拦截。</p>
</body>
</html>
"""


def html_row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(short_case(str(row.get('case_id') or '')))}</td>"
        f"<td>{row.get('blocking_count')}</td>"
        f"<td><code>{html.escape(str(row.get('primary_failure_type')))}</code></td>"
        f"<td>{row.get('primary_confidence')}</td>"
        f"<td>{row.get('full_bytes')}</td>"
        f"<td>{row.get('default_input_bytes')}</td>"
        f"<td>{row.get('compression_ratio')}x</td>"
        f"<td>{row.get('old_tokens_used')}</td>"
        f"<td>{row.get('old_after_blocking')}</td>"
        "</tr>"
    )


def short_case(case_id: str) -> str:
    if len(case_id) <= 28:
        return case_id
    return case_id[:2] + "..." + case_id[-12:]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build layout repair brief/contract payloads.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--layout-context", type=Path, help="Single layout_context.json path.")
    source.add_argument("--batch-root", type=Path, help="Batch root containing case dirs.")
    parser.add_argument("--batch-tag", default="overlap_optimized_batch_20260707_01")
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)
