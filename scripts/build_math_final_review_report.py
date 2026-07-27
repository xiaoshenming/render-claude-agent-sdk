#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def issue_cards(row: dict) -> str:
    cards = []
    for review in row.get("reviews", []):
        for issue in review.get("issues", []):
            cards.append(
                "<div class='issue'>"
                f"<b>{esc(review.get('name'))} · {esc(issue.get('severity'))}</b>"
                f"<div>{esc(issue.get('claim'))}</div>"
                f"<small>证据：{esc(issue.get('evidence'))}</small>"
                f"<small>正确不变量：{esc(issue.get('correct_invariant'))}</small>"
                "</div>"
            )
    arbitration = row.get("arbitration", {}).get("review")
    if arbitration:
        cards.insert(
            0,
            "<div class='arbitration'>"
            f"<b>第三方仲裁：{esc(arbitration.get('decision'))}</b>"
            f"<div>{esc(arbitration.get('diagnosis'))}</div>"
            "</div>",
        )
    return "".join(cards) or "<div class='muted'>未报告数学错误</div>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = []
    for path in sorted(args.cases.glob("*/result.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    counts = {
        name: sum(row.get("status") == name for row in rows)
        for name in ("completed", "failed")
    }
    verdicts = {
        name: sum(
            row.get("status") == "completed" and row.get("verdict") == name
            for row in rows
        )
        for name in ("pass", "math_error")
    }
    cards = []
    order = {"math_error": 0, "failed": 1, "pass": 2}
    for row in sorted(
        rows,
        key=lambda item: (
            order.get(
                item.get("verdict")
                if item.get("status") == "completed"
                else "failed",
                9,
            ),
            item.get("key", ""),
        ),
    ):
        state = row.get("verdict") if row.get("status") == "completed" else "failed"
        decisions = " / ".join(
            f"{item.get('name')}:{item.get('decision')}"
            for item in row.get("reviews", [])
        )
        cards.append(
            f"<details class='case {esc(state)}'>"
            f"<summary><b>{esc(row.get('key'))}</b>"
            f"<span class='pill'>{esc(state)}</span>"
            f"<span class='muted'>{esc(decisions)}</span></summary>"
            f"<p>{esc(row.get('authoritative_problem'))}</p>"
            f"<p class='hash'>SHA256 {esc(row.get('source_sha256'))}</p>"
            + (
                issue_cards(row)
                if row.get("status") == "completed"
                else f"<div class='issue'>{esc(row.get('error'))}</div>"
            )
            + "</details>"
        )
    document = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>111题最终代码 · 数学终审</title>
<style>
body{{margin:0;background:#f4f6fb;color:#182033;font:15px/1.6 system-ui}}
main{{max-width:1180px;margin:auto;padding:32px 20px 80px}}
h1{{margin:0 0 6px}} .sub,.muted{{color:#697386}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}
.stat,.case{{background:white;border:1px solid #dde3ee;border-radius:14px}}
.stat{{padding:18px}} .stat b{{display:block;font-size:30px}}
.case{{margin:10px 0;overflow:hidden}} summary{{padding:16px;cursor:pointer;
display:flex;gap:12px;align-items:center}} .case>p,.case>div{{margin:12px 18px}}
.pill{{padding:2px 9px;border-radius:999px;background:#e8edf5}}
.math_error .pill{{background:#ffe0df;color:#a3211a}}
.pass .pill{{background:#ddf7e7;color:#176b3a}}
.failed .pill{{background:#fff0cb;color:#795500}}
.issue{{padding:12px;border-left:4px solid #e34b42;background:#fff7f6;
border-radius:8px;margin:10px 18px}} .issue small{{display:block;margin-top:7px}}
.arbitration{{padding:12px;border-left:4px solid #5b63d3;background:#f2f3ff;
border-radius:8px;margin:10px 18px}}
.hash{{font:12px ui-monospace;overflow-wrap:anywhere;color:#7a8495}}
@media(max-width:700px){{.stats{{grid-template-columns:repeat(2,1fr)}}}}
</style>
<main><h1>111题最终代码 · 纯数学终审</h1>
<div class="sub">题目原文 + 最终源码 SHA256；双 Reviewer；不渲染、不审 BBox/TTS。</div>
<section class="stats">
<div class="stat"><b>{len(rows)}</b>已落盘</div>
<div class="stat"><b>{counts['completed']}</b>完整双审</div>
<div class="stat"><b>{verdicts['math_error']}</b>数学错误</div>
<div class="stat"><b>{counts['failed']}</b>运行失败</div>
</section>
{''.join(cards)}
</main></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    summary = {
        "results": len(rows),
        **counts,
        **verdicts,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
