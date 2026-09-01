#!/usr/bin/env python3
# ruff: noqa: E501
from __future__ import annotations

import argparse
import copy
import html
import json
import os
from collections import Counter
from pathlib import Path

from manim_quality.assurance.metrics import summarize


def main() -> int:
    args = arguments()
    payload = load(args.results)
    modes = {row["key"]: row.get("tts_mode", "required") for row in load(args.manifest)}
    rows = [reclassify(row, modes.get(row["key"], "required")) for row in payload["cases"]]
    corrected = {"summary": summarize(rows), "cases": rows}
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / "results.tts-aware.json", corrected)
    link_videos(args.video_root, args.output / "videos", rows)
    (args.output / "index.html").write_text(page(rows), encoding="utf-8")
    print(args.output / "index.html")
    return 0


def reclassify(source: dict, tts_mode: str) -> dict:
    row = copy.deepcopy(source)
    if tts_mode.lower() not in {"silent", "disabled", "off"}:
        return row
    report = row["deterministic"]["inspect_tts"]
    report.update(
        status="complete",
        risk_codes=[],
        evidence=[{
            "id": f"{row['key']}:tts-audio",
            "tts_mode": tts_mode.lower(),
            "audio_required": False,
            "inspection": "not_applicable",
            "reason": "tts_disabled_by_sample_contract",
        }],
    )
    agent = row["agent"]
    agent["issues"] = [
        issue for issue in agent.get("issues", [])
        if not (
            issue.get("category") == "audio"
            and f"{row['key']}:tts-audio" in issue.get("evidence_ids", [])
        )
    ]
    for receipt in agent.get("tool_receipts", []):
        if receipt.get("tool") == "inspect_tts":
            receipt["status"] = "complete"
    reports = row["deterministic"].values()
    if any(report["status"] == "incomplete" for report in reports):
        agent["status"] = "incomplete"
    elif any(report["status"] == "risk" for report in reports) or agent["issues"]:
        agent["status"] = "review"
    else:
        agent["status"] = "pass"
    count = len(agent["issues"])
    agent["summary"] = (
        "本样本按量化合同关闭 TTS，静音不计为质量问题。"
        + (
            f"终审仍确认 {count} 个非 TTS 问题，详见下方问题与证据。"
            if count
            else "其余终审工具与双 Reviewer 未确认需返修问题。"
        )
    )
    row["detected_by_tools"] = any(
        report["status"] == "risk" for report in reports
    )
    row["tts_mode"] = tts_mode.lower()
    row["grade"] = grade(row)
    return row


def grade(row: dict) -> str:
    agent = row.get("agent", {})
    if agent.get("status") == "incomplete":
        return "E"
    issues = agent.get("issues", [])
    severities = Counter(issue.get("severity", "info") for issue in issues)
    if severities["blocking"] or severities["critical"]:
        return "E"
    high = severities["high"]
    if high >= 2:
        return "D"
    if high == 1:
        return "C"
    if issues:
        return "B"
    return "A"


def page(rows: list[dict]) -> str:
    counts = Counter(row["grade"] for row in rows)
    cards = "".join(card(row) for row in sorted(rows, key=lambda row: row["key"]))
    metrics = "".join(
        f"<div><strong>{letter}</strong><span>{counts[letter]} 题</span></div>"
        for letter in "ABCDE"
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>r10 最终 60 题终审报告</title><style>{CSS}</style></head><body>
<header><p class="eyebrow">NATIVE READ/EDIT R10 · FINAL ASSURANCE</p>
<h1>最终 60 题视频终审报告</h1>
<p>已按样本合同排除预期关闭的 TTS。每题均展示最终视频、A–E 等级、
终审结论、问题证据、双 Reviewer 状态与资源消耗。</p>
<section class="metrics">{metrics}</section></header>
<aside><b>评级规则：</b>A＝无非 TTS 问题；B＝仅中风险；C＝1 个高风险；
D＝至少 2 个高风险；E＝关键/阻断问题或证据不完整。评级用于修复排序，不替代人工看片。</aside>
<nav><input id="q" placeholder="搜索题号或问题">
<button class="on" data-grade="all">全部 60</button>
{''.join(f'<button data-grade="{x}">{x}级 {counts[x]}</button>' for x in "ABCDE")}</nav>
<main>{cards}</main><div id="empty">没有匹配结果</div><script>{JS}</script></body></html>"""


def card(row: dict) -> str:
    agent = row["agent"]
    issues = agent.get("issues", [])
    issue_html = "".join(
        "<li><div><b>{}</b><em>{}</em></div><p>{}</p><small>{}</small></li>".format(
            esc(issue.get("severity", "info").upper()),
            esc(issue.get("category", "问题")),
            esc(issue.get("summary", "")),
            esc(" · ".join(issue.get("evidence_ids", []))),
        )
        for issue in issues
    ) or "<li class='clean'>未确认非 TTS 返修问题</li>"
    receipts = "".join(
        f"<span class='{esc(item['status'])}'>{esc(tool_name(item['tool']))} · "
        f"{esc(item['status'])}</span>"
        for item in agent.get("tool_receipts", [])
    )
    reviewers = " / ".join(
        f"{reviewer.get('agent_type')}："
        f"{reviewer.get('payload', {}).get('decision', 'unknown')}"
        for reviewer in row.get("reviewers", [])
    )
    usage = row.get("agent_usage", {})
    search = " ".join(
        [row["key"], agent.get("summary", "")]
        + [issue.get("summary", "") for issue in issues]
    ).lower()
    return f"""<article data-grade="{row['grade']}" data-search="{esc(search)}">
<div class="video"><video controls preload="metadata"
src="videos/{esc(row['key'])}.mp4"></video><i>{row['grade']}</i></div>
<section><h2>{esc(row['key'])}</h2><p class="summary">{esc(agent['summary'])}</p>
<div class="usage"><b>{usage.get('tokens', 0):,}</b> tokens
<b>{usage.get('turns', 0)}</b> 轮 <b>{usage.get('tool_calls', 0)}</b> 工具</div>
<details open><summary>终审问题（{len(issues)}）</summary><ul>{issue_html}</ul></details>
<details><summary>工具与 Reviewer 证据</summary><div class="receipts">{receipts}</div>
<p class="reviewers">{esc(reviewers)}</p></details></section></article>"""


def link_videos(video_root: Path, target: Path, rows: list[dict]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for row in rows:
        source = (video_root / f"{row['key']}.mp4").resolve(strict=True)
        link = target / source.name
        if link.is_symlink() and link.resolve() == source:
            continue
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(source, link)


def tool_name(value: str) -> str:
    return {
        "inspect_artifact": "交付视频", "inspect_execution": "冷渲染",
        "inspect_code_review": "源码审查", "inspect_layout": "BBox布局",
        "inspect_tts": "TTS合同",
        "inspect_consistency": "版本一致性",
    }.get(value, value)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


CSS = """
:root{font-family:Inter,"Noto Sans SC",sans-serif;color:#172033;background:#f2f5fa}
*{box-sizing:border-box}body{margin:0}header{padding:48px 5vw 32px;color:#fff;
background:linear-gradient(135deg,#132744,#176766)}.eyebrow{color:#9debe2;letter-spacing:.13em}
h1{font-size:clamp(32px,5vw,58px);margin:8px 0}header>p{max-width:920px;line-height:1.7}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;max-width:850px}
.metrics div{background:#ffffff14;border:1px solid #ffffff28;padding:13px;border-radius:12px}
.metrics strong{font-size:27px;display:block}.metrics span{color:#dce8ed}
aside,nav,main{max-width:1500px;margin:auto}aside{margin-top:18px;background:#fff9dc;
border:1px solid #ead787;padding:14px 18px;border-radius:12px;line-height:1.7}
nav{display:flex;gap:8px;padding:20px 0;flex-wrap:wrap}input{flex:1;min-width:260px;
padding:11px;border:1px solid #cad3de;border-radius:9px}button{padding:10px 13px;
border:1px solid #c7d1dd;background:#fff;border-radius:9px}button.on{background:#183f55;color:#fff}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(410px,1fr));gap:17px;
padding-bottom:60px}article{background:#fff;border:1px solid #e0e6ee;border-radius:15px;
overflow:hidden;box-shadow:0 8px 25px #21334812}.video{position:relative;background:#111}
video{display:block;width:100%;aspect-ratio:16/9}.video i{position:absolute;right:12px;top:12px;
font-style:normal;font-size:25px;font-weight:800;color:#fff;background:#166765;padding:6px 13px;
border-radius:10px}article[data-grade=D] .video i,article[data-grade=E] .video i{background:#a92b3c}
article>section{padding:16px}h2{font-size:18px;margin:0}.summary{color:#4a576a;line-height:1.65}
.usage{font-size:12px;color:#647187}.usage b{color:#1c4556;margin-left:8px}.usage b:first-child{margin:0}
details{border-top:1px solid #edf0f4;margin-top:12px;padding-top:10px}summary{font-weight:700}
ul{padding-left:20px}li{margin:12px 0}li div{display:flex;gap:9px}li b{color:#b6442c}
li em{font-style:normal;color:#795b13}li p{font-size:13px;line-height:1.6;margin:4px 0}
li small{color:#8590a0;word-break:break-all}.clean{color:#16705a}.receipts span{display:inline-block;
font-size:11px;padding:5px 8px;margin:4px;border-radius:99px;background:#e0f4e8}
.receipts .risk{background:#ffdadd}.receipts .incomplete{background:#fff0bd}
.reviewers{font-size:12px;color:#5e6b7c}#empty{display:none;text-align:center;padding:60px}
@media(max-width:700px){aside,nav,main{margin-left:12px;margin-right:12px}.metrics{grid-template-columns:
repeat(3,1fr)}main{grid-template-columns:1fr}}
"""

JS = """
const cards=[...document.querySelectorAll('article')],q=document.querySelector('#q');
const buttons=[...document.querySelectorAll('button')],empty=document.querySelector('#empty');
let grade='all';function render(){let n=0,s=q.value.trim().toLowerCase();cards.forEach(c=>{
let ok=(grade==='all'||c.dataset.grade===grade)&&(!s||c.dataset.search.includes(s));
c.hidden=!ok;if(ok)n++});empty.style.display=n?'none':'block'}
buttons.forEach(b=>b.onclick=()=>{buttons.forEach(x=>x.classList.remove('on'));b.classList.add('on');
grade=b.dataset.grade;render()});q.oninput=render;
"""


if __name__ == "__main__":
    raise SystemExit(main())
