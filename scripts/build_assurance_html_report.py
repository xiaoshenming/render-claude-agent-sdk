#!/usr/bin/env python3
# ruff: noqa: E501
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path


def main() -> int:
    args = arguments()
    results = load(args.results)["cases"]
    annotations = load(args.annotations)
    tags = invert_tags(annotations)
    media = {}
    if args.video_root is None:
        manifest = load(args.gallery / "manifest.json")["items"]
        media = {
            row["external_key"]: selected_video(row)
            for row in manifest
            if row.get("item_status") == "succeeded"
        }
    video_dir = args.output.parent / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for row in sorted(results, key=lambda value: value["key"]):
        key = row["key"]
        source = (
            args.video_root / f"{key}.mp4"
            if args.video_root is not None
            else args.gallery / media[key]
        )
        target = video_dir / f"{key}.mp4"
        link_video(source, target)
        cards.append(card(row, tags.get(key, ()), f"videos/{key}.mp4"))
    args.output.write_text(page(cards, results, tags), encoding="utf-8")
    print(args.output)
    return 0


def card(row: dict, human_tags: tuple[str, ...], video: str) -> str:
    agent = row["agent"]
    issues = agent.get("issues", [])
    severity = highest_severity(issues)
    issue_html = "".join(
        f"<li><b>{escape(issue.get('category', '问题'))}</b>"
        f"<span>{escape(issue.get('summary', ''))}</span></li>"
        for issue in issues
    ) or "<li><span>Agent 未列出具体问题，但证据仍不完整。</span></li>"
    labels = "".join(f"<span class='tag human'>{escape(tag)}</span>" for tag in human_tags)
    tools = "".join(
        f"<span class='tag {receipt['status']}'>{escape(tool_name(receipt['tool']))}"
        f" · {escape(receipt['status'])}</span>"
        for receipt in agent.get("tool_receipts", [])
    )
    search = " ".join(
        [row["key"], *human_tags, agent.get("summary", "")]
        + [issue.get("summary", "") for issue in issues]
    )
    marked = "yes" if human_tags else "no"
    return f"""
    <article class="card" data-severity="{severity}" data-marked="{marked}"
      data-search="{escape(search.lower())}">
      <div class="video-wrap">
        <video controls preload="metadata" src="{escape(video)}"></video>
        <span class="severity {severity}">{severity_name(severity)}</span>
      </div>
      <div class="body">
        <div class="title-row"><h2>{escape(row["key"])}</h2>{labels}</div>
        <p class="summary">{escape(agent.get("summary", "暂无结论"))}</p>
        <details open><summary>发现的问题（{len(issues)}）</summary>
          <ul class="issues">{issue_html}</ul>
        </details>
        <details><summary>工具证据</summary><div class="tags">{tools}</div></details>
      </div>
    </article>"""


def page(cards: list[str], rows: list[dict], tags: dict[str, tuple[str, ...]]) -> str:
    total = len(rows)
    marked = len(set(tags) & {row["key"] for row in rows})
    blocking = sum(layout_blocking_count(row) > 0 for row in rows)
    receipts = sum(
        len(row.get("agent", {}).get("tool_receipts", ())) == 7
        and len(row.get("reviewers", ())) == 2
        for row in rows
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{total} 个最终视频全链路审查</title><style>{CSS}</style></head>
<body><header>
  <p class="eyebrow">FINAL ASSURANCE · 2026-07-27</p>
  <h1>{total} 个最终视频全链路审查</h1>
  <p class="lead">每个样本均重新执行最终源码冷渲染、逐帧 BBox、代码双 reviewer、
  多模态风险帧、音轨与最终产物一致性检查。工具风险是分维度证据，不等于视频整体必错。</p>
  <div class="metrics">
    <div><strong>{total}</strong><span>完整 Agent 已完成</span></div>
    <div><strong>{receipts}</strong><span>7 工具 + 2 reviewer 齐全</span></div>
    <div><strong>{blocking}</strong><span>BBox 有 blocking</span></div>
    <div><strong>{marked}</strong><span>人工标注问题视频</span></div>
  </div>
</header>
<section class="notice"><b>怎么看：</b>优先选择“人工标注”和“Blocking”。
每张卡片播放的是最终交付 MP4。静音、布局、数学逻辑、版本证据分别展示，不能混成一个总分。</section>
<nav>
  <input id="search" placeholder="搜索编号、问题或人工标签">
  <button class="active" data-filter="all">全部 {total}</button>
  <button data-filter="marked">只看人工标注</button>
  <button data-filter="blocking">Blocking</button>
  <button data-filter="high">High</button>
</nav>
<main id="grid">{''.join(cards)}</main>
<div id="empty">没有符合条件的视频</div>
<script>{JS}</script></body></html>"""


def layout_blocking_count(row: dict) -> int:
    report = row.get("deterministic", {}).get("inspect_layout", {})
    evidence = report.get("evidence", ())
    if not evidence or not isinstance(evidence[0], dict):
        return 0
    return int(evidence[0].get("blocking_count") or 0)


def selected_video(row: dict) -> str:
    for name in ("overlap", "logic", "before"):
        stage = row.get("stages", {}).get(name, {})
        if stage.get("path"):
            return stage["path"]
    raise ValueError(f"missing final video: {row.get('external_key')}")


def invert_tags(annotations: dict) -> dict[str, tuple[str, ...]]:
    output: dict[str, list[str]] = {}
    for tag, keys in annotations.items():
        for key in keys:
            output.setdefault(key, []).append(tag)
    return {key: tuple(sorted(values)) for key, values in output.items()}


def highest_severity(issues: list[dict]) -> str:
    order = {"blocking": 4, "critical": 4, "high": 3, "medium": 2, "warning": 1}
    return max((issue.get("severity", "info") for issue in issues),
               key=lambda value: order.get(value, 0), default="info")


def severity_name(value: str) -> str:
    return {"blocking": "必须复核", "critical": "必须复核", "high": "高风险",
            "medium": "中风险", "warning": "提醒", "info": "证据不足"}.get(value, value)


def tool_name(value: str) -> str:
    return {
        "inspect_artifact": "视频产物", "inspect_execution": "执行终态",
        "inspect_code_review": "代码审查", "inspect_layout": "布局/BBox",
        "inspect_risk_frames": "多模态画面", "inspect_tts": "TTS",
        "inspect_consistency": "版本一致性",
    }.get(value, value)


def link_video(source: Path, target: Path) -> None:
    if target.is_symlink() and target.resolve() == source.resolve():
        return
    if target.exists() or target.is_symlink():
        target.unlink()
    os.symlink(source.resolve(), target)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--video-root", type=Path)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


CSS = """
:root{font-family:Inter,"Noto Sans SC",sans-serif;color:#172033;background:#f3f6fb}
*{box-sizing:border-box}body{margin:0}header{padding:56px max(5vw,24px) 38px;
background:linear-gradient(135deg,#12233f,#265a69);color:white}.eyebrow{letter-spacing:.15em;
font-size:12px;color:#98e7dc}h1{font-size:clamp(32px,5vw,60px);margin:8px 0 12px}
.lead{max-width:850px;line-height:1.75;color:#d8e6ed}.metrics{display:grid;
grid-template-columns:repeat(4,minmax(120px,1fr));gap:14px;max-width:900px;margin-top:28px}
.metrics div{background:#ffffff13;border:1px solid #ffffff25;border-radius:14px;padding:16px}
.metrics strong{font-size:30px;display:block}.metrics span{font-size:13px;color:#cfdae2}
.notice,nav,main{max-width:1500px;margin:auto}.notice{margin-top:22px;background:#fff8db;
border:1px solid #ead685;border-radius:12px;padding:14px 18px;line-height:1.7}
nav{display:flex;gap:9px;flex-wrap:wrap;padding:22px 0}input{min-width:280px;flex:1;
border:1px solid #ccd5df;border-radius:10px;padding:12px 14px;font-size:15px}
button{border:1px solid #c7d2df;background:white;border-radius:10px;padding:10px 14px;
cursor:pointer}button.active{background:#183f55;color:white;border-color:#183f55}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(390px,1fr));gap:18px;
padding-bottom:60px}.card{background:white;border-radius:16px;box-shadow:0 8px 24px #21334812;
overflow:hidden;border:1px solid #e0e6ed}.video-wrap{position:relative;background:#111}
video{display:block;width:100%;aspect-ratio:16/9}.severity{position:absolute;top:10px;right:10px;
padding:6px 10px;border-radius:999px;font-size:12px;color:white;background:#607080}
.severity.blocking,.severity.critical{background:#a81632}.severity.high{background:#d15d1e}
.severity.medium{background:#b38a17}.body{padding:17px}.title-row{display:flex;gap:8px;
align-items:center;flex-wrap:wrap}.title-row h2{margin:0 8px 0 0;font-size:20px}.tag{display:inline-block;
font-size:11px;border-radius:999px;padding:5px 8px;background:#edf1f5;margin:3px}
.tag.human{background:#ffe2e9;color:#8d1734}.tag.incomplete{background:#fff0c7}
.tag.risk{background:#ffd8d8}.tag.complete{background:#dff5e8}.summary{line-height:1.65;
color:#46546a;font-size:14px}details{border-top:1px solid #edf0f3;padding-top:11px;
margin-top:11px}summary{cursor:pointer;font-weight:650}.issues{padding-left:20px}.issues li{
margin:10px 0}.issues b{display:block;font-size:12px;color:#9a3d25}.issues span{
font-size:13px;line-height:1.55;color:#4b586b}#empty{text-align:center;padding:60px;display:none}
@media(max-width:700px){.metrics{grid-template-columns:1fr 1fr}.notice,nav,main{margin-left:14px;
margin-right:14px}main{grid-template-columns:1fr}header{padding-top:36px}}
"""

JS = """
const cards=[...document.querySelectorAll('.card')],buttons=[...document.querySelectorAll('button')];
const search=document.querySelector('#search'),empty=document.querySelector('#empty');
let filter='all';
function render(){const q=search.value.trim().toLowerCase();let shown=0;
cards.forEach(card=>{const matchText=!q||card.dataset.search.includes(q);
const matchFilter=filter==='all'||(filter==='marked'&&card.dataset.marked==='yes')||
(filter==='blocking'&&['blocking','critical'].includes(card.dataset.severity))||
(filter==='high'&&card.dataset.severity==='high');card.hidden=!(matchText&&matchFilter);
if(!card.hidden)shown++});empty.style.display=shown?'none':'block'}
buttons.forEach(button=>button.onclick=()=>{buttons.forEach(x=>x.classList.remove('active'));
button.classList.add('active');filter=button.dataset.filter;render()});
search.addEventListener('input',render);
"""


if __name__ == "__main__":
    raise SystemExit(main())
