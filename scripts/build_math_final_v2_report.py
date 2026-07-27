#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path

ORDER = {
    "MATH_ERROR": 0,
    "SOURCE_MISMATCH": 1,
    "MINOR_ISSUE": 2,
    "PASS": 3,
}


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def cards_for(rows) -> str:
    cards = []
    for row in rows:
        reviews = " / ".join(
            f"{item['name']}:{item['classification']}" for item in row["reviews"]
        )
        arbiter = (
            row.get("arbitration", {}).get("review", {}).get("classification")
            if row.get("arbitration")
            else "未触发"
        )
        summaries = "".join(
            f"<li><b>{esc(item['name'])}</b>：{esc(item['summary'])}</li>"
            for item in row["reviews"]
        )
        cards.append(
            f"<details class='case {esc(row['verdict'])}'>"
            f"<summary><b>{esc(row['key'])}</b>"
            f"<span class='pill'>{esc(row['verdict'])}</span>"
            f"<span class='muted'>{esc(row['failure_code'])}</span></summary>"
            f"<p>{esc(row['authoritative_problem'])}</p>"
            f"<p><b>双审：</b>{esc(reviews)}　<b>仲裁：</b>{esc(arbiter)}</p>"
            f"<ul>{summaries}</ul>"
            f"<p class='muted'>证据模式：只读、非阻断；"
            f"示意图模式：{esc(row['diagram_mode'])}</p>"
            "</details>"
        )
    return "".join(cards)


def build_document(rows) -> tuple[dict[str, int], str]:
    counts = Counter(row["verdict"] for row in rows)
    summary = {
        "total": len(rows),
        "PASS": counts["PASS"],
        "MINOR_ISSUE": counts["MINOR_ISSUE"],
        "SOURCE_MISMATCH": counts["SOURCE_MISMATCH"],
        "MATH_ERROR": counts["MATH_ERROR"],
    }
    return summary, f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>数学终审 V2</title>
<style>
body{{margin:0;background:#f4f6fb;color:#172033;font:15px/1.65 system-ui}}
main{{max-width:1120px;margin:auto;padding:32px 18px 72px}}
h1{{margin-bottom:4px}}.muted{{color:#6b7485}}
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:22px 0}}
.stat,.case{{background:white;border:1px solid #dfe5ee;border-radius:13px}}
.stat{{padding:16px}}.stat b{{display:block;font-size:27px}}
.case{{margin:10px 0;overflow:hidden}}summary{{padding:15px;cursor:pointer;
display:flex;gap:11px;align-items:center}}.case>p,.case>ul{{margin:12px 18px}}
.pill{{padding:2px 9px;border-radius:999px;background:#e8edf4}}
.MATH_ERROR .pill{{background:#ffdeda;color:#a12620}}
.SOURCE_MISMATCH .pill{{background:#ffe9c3;color:#7d5200}}
.MINOR_ISSUE .pill{{background:#e5e8ff;color:#454eb0}}
.PASS .pill{{background:#daf5e4;color:#17673a}}
@media(max-width:720px){{.stats{{grid-template-columns:repeat(2,1fr)}}}}
</style><main>
<h1>数学终审 V2</h1>
<div class="muted">精确率优先；核心数学三方一致才判错；默认只采证、不阻断。</div>
<section class="stats">
<div class="stat"><b>{summary['total']}</b>样本</div>
<div class="stat"><b>{summary['PASS']}</b>通过</div>
<div class="stat"><b>{summary['MINOR_ISSUE']}</b>局部风险</div>
<div class="stat"><b>{summary['SOURCE_MISMATCH']}</b>身份错配</div>
<div class="stat"><b>{summary['MATH_ERROR']}</b>核心数学错误</div>
</section>{cards_for(rows)}</main></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.results.glob("*/result-v2.json")
    ]
    rows.sort(key=lambda row: (ORDER.get(row["verdict"], 9), row["key"]))
    summary, document = build_document(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    args.output.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
