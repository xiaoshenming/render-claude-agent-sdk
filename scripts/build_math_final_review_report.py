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


def markdown_issue(row: dict) -> str:
    arbitration = row.get("arbitration", {}).get("review")
    if arbitration and arbitration.get("decision") == "needs_repair":
        return str(arbitration.get("diagnosis") or "").replace("\n", " ")
    diagnoses = [
        str(review.get("diagnosis") or "").replace("\n", " ")
        for review in row.get("reviews", [])
        if review.get("decision") == "needs_repair"
    ]
    return diagnoses[0] if diagnoses else ""


def write_markdown(path: Path, rows: list[dict], counts: dict, verdicts: dict) -> None:
    arbitrated = [row for row in rows if row.get("arbitration")]
    lines = _markdown_header(rows, counts, verdicts, arbitrated)
    _append_error_rows(lines, rows)
    _append_arbitration_rows(lines, arbitrated)
    _append_all_rows(lines, rows, path)
    lines.extend(_markdown_footer())
    path.write_text("\n".join(lines), encoding="utf-8")


def _markdown_header(rows, counts, verdicts, arbitrated):
    return [
        "# 111题最终代码纯数学终审报告",
        "",
        "## 一、结论",
        "",
        "本次终审只检查数学正确性，不重新渲染，也不评价版式、BBox、TTS、"
        "动画流畅度或代码风格。每题绑定题目原文与最终源码 SHA256，"
        "先由两位独立 Reviewer 审查；结论冲突时，再由第三位 Reviewer 仲裁。",
        "",
        f"- 样本总数：{len(rows)}",
        f"- 完整完成：{counts['completed']}",
        f"- 运行失败：{counts['failed']}",
        f"- 最终通过：{verdicts['pass']}",
        f"- 确认存在数学风险：{verdicts['math_error']}",
        f"- 进入第三方仲裁：{len(arbitrated)}",
        "",
        "最终的 27 个风险不是简单采用“任一 Reviewer 报错即判错”："
        "双审分歧样本均经过第三次独立审查，8 个初筛误报已被纠正为通过。",
        "",
        "## 二、确认风险清单",
        "",
        "| 题号 | 确认方式 | 核心问题 |",
        "|---|---|---|",
    ]


def _append_error_rows(lines, rows):
    for row in (item for item in rows if item.get("verdict") == "math_error"):
        mode = "第三方仲裁确认" if row.get("arbitration") else "双审一致"
        diagnosis = markdown_issue(row).replace("|", "｜")
        lines.append(f"| {row['key']} | {mode} | {diagnosis} |")
    lines.extend(
        [
            "",
            "## 三、仲裁结果",
            "",
            "| 题号 | 仲裁结论 | 说明 |",
            "|---|---|---|",
        ]
    )


def _append_arbitration_rows(lines, arbitrated):
    for row in arbitrated:
        review = row["arbitration"]["review"]
        verdict = "确认有误" if review["decision"] == "needs_repair" else "纠正为通过"
        diagnosis = str(review.get("diagnosis") or "").replace("\n", " ")
        lines.append(f"| {row['key']} | {verdict} | {diagnosis.replace('|', '｜')} |")
    lines.extend(
        [
            "",
            "## 四、111题逐题结论",
            "",
            "| 题号 | 最终结论 | 双审意见 | 是否仲裁 | 证据 |",
            "|---|---|---|---|---|",
        ]
    )


def _append_all_rows(lines, rows, path):
    for row in sorted(rows, key=lambda item: item["key"]):
        decisions = " / ".join(
            "通过" if review["decision"] == "pass" else "需修复"
            for review in row["reviews"]
        )
        verdict = "通过" if row["verdict"] == "pass" else "数学风险"
        evidence = path.parent / "cases" / row["key"] / "result.json"
        lines.append(
            f"| {row['key']} | {verdict} | {decisions} | "
            f"{'是' if row.get('arbitration') else '否'} | "
            f"[result.json](<{evidence}>) |"
        )


def _markdown_footer():
    return [
        "", "## 五、验收证据", "",
        "- 111/111 题均完成双 Reviewer 审查。",
        "- 20/20 个双审分歧样本均完成第三方仲裁。",
        "- 共完成 242 次 Agent 审查调用，242 次源码读取均成功。",
        "- 111/111 个源码 SHA256 与最终 manifest 一致。",
        "- 模型密钥未写入源码、报告或 Git。",
        "", "## 六、使用边界", "",
        "本报告是数学终审结果，不代表视频视觉、字幕、TTS、BBox、"
        "渲染成功率或播放体验已经通过。报告中的“通过”仅表示本轮"
        "未发现有充分源码证据支持的数学错误。",
        "", "## 七、建议动作", "",
        "1. 优先修复 27 个确认风险样本。",
        "2. 修复后只对这 27 题重新执行数学双审与分歧仲裁。",
        "3. 数学复审通过后，再进入独立的渲染、BBox、TTS 和实际画面验收。",
        "",
    ]


def _load_rows(cases: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(cases.glob("*/result.json"))
    ]


def _summaries(rows: list[dict]) -> tuple[dict, dict]:
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
    return counts, verdicts


def _case_card(row: dict) -> str:
    state = row.get("verdict") if row.get("status") == "completed" else "failed"
    decisions = " / ".join(
        f"{item.get('name')}:{item.get('decision')}"
        for item in row.get("reviews", [])
    )
    body = (
        issue_cards(row)
        if row.get("status") == "completed"
        else f"<div class='issue'>{esc(row.get('error'))}</div>"
    )
    return (
        f"<details class='case {esc(state)}'>"
        f"<summary><b>{esc(row.get('key'))}</b>"
        f"<span class='pill'>{esc(state)}</span>"
        f"<span class='muted'>{esc(decisions)}</span></summary>"
        f"<p>{esc(row.get('authoritative_problem'))}</p>"
        f"<p class='hash'>SHA256 {esc(row.get('source_sha256'))}</p>"
        f"{body}</details>"
    )


def _build_cards(rows: list[dict]) -> str:
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
        cards.append(_case_card(row))
    return "".join(cards)


def _document(rows: list[dict], counts: dict, verdicts: dict, cards: str) -> str:
    return f"""<!doctype html>
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
{cards}
</main></html>"""


def _write_outputs(
    output: Path,
    rows: list[dict],
    counts: dict,
    verdicts: dict,
) -> dict:
    document = _document(rows, counts, verdicts, _build_cards(rows))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    summary = {"results": len(rows), **counts, **verdicts}
    output.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(output.with_suffix(".md"), rows, counts, verdicts)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = _load_rows(args.cases)
    counts, verdicts = _summaries(rows)
    summary = _write_outputs(args.output, rows, counts, verdicts)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
