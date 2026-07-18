# Manim Quality 完整 E2E 交接运行手册

## 1. 包内已经包含什么

| 路径 | 作用 |
|---|---|
| `src/manim_quality` | 质量平台领域核心 |
| `evals/workbench_e2e` | 已验证的真实 E2E 流程 Harness |
| `evals/_logic_shadow_case.py` | Logic Reviewer 执行包装 |
| `evals/_logic_repair_case.py` | Logic Coder/Verifier 执行包装 |
| `vendor/logic_engine_mvp_baseline` | 代码事实提取基线 |
| `.vendor/quality_repair` | 重叠 Agent 物化运行时和 Hash 清单 |
| `external/layout_probe/probe_runner.py` | 已从 DEV-PB5 收入包内的布局探针 |
| `handoff_data/prompts_minimal.sqlite3` | 仅含 95、98、99 三个提示词版本的最小数据库 |
| `handoff_data/workload_v1.json` | 20 条历史 E2E 数学任务，仅约 9 KB |
| `handoff_data/existing_code_real` | 一条真实生成、曾成功渲染的几何代码及人工注入错误 |
| `evidence/reference_results` | 历史批量运行的精简 JSON/CSV/Markdown 结果 |

本包不包含模型密钥，不包含虚拟环境，也不包含大批量视频。

## 2. 外部环境只需要什么

### 平台 Python

- Python 3.11 或 3.12。
- 安装 `pyproject.toml` 中的依赖。
- 负责运行 Agent SDK、Harness 和报告代码。

### Manim Python

- 可以与平台 Python 相同，也可以是独立环境。
- 必须满足 `python -m manim --version` 成功。
- 必须安装样本所需字体、LaTeX/CTeX 和 FFmpeg。
- 由 `--manim-python` 显式传入，不使用硬编码路径。

### 模型配置

只通过进程环境注入：

```powershell
$env:ANTHROPIC_BASE_URL='https://ai.onegodtoken.top'
$env:QUALITY_MODEL='gemini-3.5-flash-high'
$env:MANIM_QUALITY_API_KEY='<secret>'
```

脚本会把同一密钥映射给 Claude Agent SDK 需要的认证变量，但不会持久化密钥。

## 3. 安装与环境确认

```powershell
cd D:\manim_quality_complete_handoff_20260715_v3
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

.\.venv\Scripts\python.exe scripts\handoff_doctor.py `
  --manim-python 'D:\path\to\manim-python.exe' `
  --require-api-key
```

Doctor 检查：

1. 平台 Python 版本。
2. E2E Harness 文件是否齐全。
3. `logic_engine_mvp` 是否可执行。
4. `quality_repair` 全量 payload Hash 是否匹配。
5. 内置 layout probe 是否有效。
6. 最小 prompt DB 是否包含三个必要版本。
7. Manim 环境是否可调用。
8. 是否注入模型密钥，只报告变量名，不报告值。

## 4. 模式 A：已有代码直接审查修复

使用包内真实样本：

```powershell
.\.venv\Scripts\python.exe scripts\run_existing_code_e2e.py `
  --code handoff_data\existing_code_real\candidate.py `
  --problem handoff_data\existing_code_real\problem.txt `
  --expected-solution handoff_data\existing_code_real\expected_solution.txt `
  --manim-python 'D:\path\to\manim-python.exe' `
  --output runs\existing-code-smoke `
  --allow-vendor-clean-fallback
```

接入业务代码时只替换三个输入文件和 `--output`：

```text
--code                 可渲染 candidate.py
--problem              题目文本
--expected-solution    解题过程、参考答案或生成规划
```

输出：

```text
runs/existing-code-smoke/
├─ candidate_input.py
├─ candidate_final.py
├─ video_final.mp4
├─ result.json
├─ render_baseline/
│  ├─ render.json
│  ├─ stdout.log
│  └─ stderr.log
├─ logic/
│  ├─ logic_summary.json
│  ├─ review/
│  └─ repair/
├─ render_after_logic/
├─ layout/
│  ├─ layout_summary.json
│  ├─ detect/
│  └─ repair_evidence/
└─ render_after_layout/
```

首先读取 `result.json`：

- `deliver`：严格交付。
- `deliver_with_warning`：代码和视频已输出，但存在非阻断告警。
- `logic_hold`：Reviewer/Verifier 不允许自动放行。
- `baseline_render_failed`：输入不是当前环境可渲染代码。
- `logic_render_hold`：逻辑修复后无法渲染。
- `layout_render_hold`：布局修复后无法渲染。

## 5. 模式 B：生成加质量链路

默认只跑一条 `slot-001`：

```powershell
.\.venv\Scripts\python.exe scripts\run_handoff_batch.py `
  --manim-python 'D:\path\to\manim-python.exe' `
  --output runs\batch-smoke `
  --slot slot-001 `
  --workers 1
```

跑多条：

```powershell
.\.venv\Scripts\python.exe scripts\run_handoff_batch.py `
  --manim-python 'D:\path\to\manim-python.exe' `
  --output runs\batch-15 `
  --slot slot-001 --slot slot-002 --slot slot-003 `
  --workers 2
```

整轮运行会生成 `report.json`、`report.csv` 和 `before_after.html`。

## 6. 如何定位断链

| 现象 | 先看文件 | 所属阶段 |
|---|---|---|
| 代码无法渲染 | `render_baseline/stderr.log` | Manim 环境或代码 |
| Reviewer 报错 | `logic/review/cases/*/error.json` | Logic SDK |
| Reviewer 没发现问题 | `logic/review/cases/*/review_report.json` | Logic evidence/prompt |
| Coder 没产生候选 | `logic/repair/cases/*` | Logic Coder |
| 修后不通过 | verifier report、`render_after_logic` | Logic Verifier/Manim |
| 检测器失败 | `layout/detect/local_layout_probe_*/stderr.log` | layout probe |
| 重叠 Agent 失败 | `layout/repair_evidence` | quality_repair SDK |
| 最终无视频 | `render_after_layout/render.json` | final render |

不要只看控制台最后一行。`result.json` 判断终态，各阶段目录判断根因。

## 7. 与 `manim_quality` 核心的关系

当前真实调用关系：

```text
scripts/run_existing_code_e2e.py
→ evals/workbench_e2e
→ manim_quality/logic + manim_quality/layout
→ bundled vendor + bundled probe + external Manim executable
```

这套包已经消除了对其他源码仓库的路径依赖，部署方不需要再从 DEV-PB5 或 `manim_test_tool` 拷文件。但它仍是 Harness 入口，不应伪装成最终产品 API。

企业服务线路的最终目标是：

```text
API/Worker → QualityEngine.repair() → DB/Object Store/Callback
```

具体 composition root 方案见：

`docs/plans/2026-07-15-production-pipeline-composition-root.md`

## 8. 交接验收清单

- Doctor 全部 PASS。
- 模式 A 能产出 `candidate_final.py`、`video_final.mp4` 和 `result.json`。
- 模式 B 单样本能产出 `job_summary.json` 和批次报告。
- 所有脚本不包含本机绝对路径。
- 部署环境未把真实密钥写入包内。
- `MANIFEST.json` 和 `SHA256SUMS.txt` 校验通过。
