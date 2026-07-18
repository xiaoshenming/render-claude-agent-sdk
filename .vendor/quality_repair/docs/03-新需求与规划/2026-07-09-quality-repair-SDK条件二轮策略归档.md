# quality_repair SDK 条件二轮策略归档

日期：2026-07-09

## 归档结论

这版方案是当前 `libs/quality_repair` 的 SDK 重叠修复主线优化版。它不是单纯追求最低 token，而是在保留 fail-open、安全回滚、checker 裁判的前提下，把上一版“机械二轮追清零”改为“强改善后条件停手”，同时允许 Edit 后有限重读当前核心代码，降低 stale `old_string` 造成的无效 Edit 循环。

当前结论：

```text
修复效果优于上一版：
top10 高危样本 blocking 从 474 -> 15，旧版为 474 -> 64。

06 核心样本成本明显下降：
37 -> 0，1 轮，92,596 token；上一版同样清零但约 184,784 token、2 轮。

整体 top10 token 未下降：
新版多修好了 HR0006、HR0002、HR0009，因此总 token 高于旧版。
```

## Git 锚点

### 代码提交

```text
2a25e8530 优化质量修复SDK条件二轮策略
```

本提交包含：

```text
libs/quality_repair/agent/controller.py
libs/quality_repair/agent/guards.py
libs/quality_repair/agent/runner.py
libs/quality_repair/pipeline_io.py
libs/quality_repair/schemas.py
libs/quality_repair/tests/test_agent_controller_loop.py
libs/quality_repair/tests/test_agent_guards.py
libs/quality_repair/tests/test_agent_runner_sdk.py
libs/quality_repair/tests/test_pipeline_io.py
```

### 改动前备份分支

```text
backup/quality-repair-best-before-conditional-loop-20260709-335d7a3d
```

指向：

```text
335d7a3d40312d9017a93a3e16544073d6a37c1f
```

用途：回到条件二轮策略改造前的最好版本。

## 方案目标

上一版的主要问题不是 bbox 输入过大，也不是 core candidate 看不到前置函数，而是 SDK 工具循环在以下位置浪费：

1. 多次 `Edit` 后上下文循环放大。
2. 前一次 Edit 修改源码后，后续仍用旧片段触发 `String to replace not found`。
3. 安全守卫拒绝后，agent 继续用旧上下文猜 patch。
4. 已经明显改善后仍进入第二轮，低残留样本可能被二轮改坏再回滚。

本版目标：

```text
保留多次 Edit 能力；
降低无效二轮；
允许 Edit 后有限重读最新源码；
仍由 checker/acceptance 决定是否采纳；
不新增 render hard gate。
```

## 核心策略

### 1. 条件二轮

新增 layout budget 参数：

```text
accept_degraded_max_blocking = 2
accept_degraded_min_reduction_ratio = 0.5
accept_risk_only_max_blocking = 6
```

含义：

```text
如果一轮已经显著改善，并且残留 blocking 很低，停止继续赌第二轮。
如果残留全部是 label_shape_overlap_risk 且数量较低，也停止继续赌第二轮。
最终仍交给 acceptance judge 判定 SUCCESS_DEGRADED / REPAIR_WORSE / 回滚。
```

### 2. Edit 后有限重读

Read 守卫保持严格 allowlist：

```text
layout_issue_digest.json
candidate.py 或 core_candidate.py
```

但在 Edit 开始后，允许最多 2 次重新读取当前可编辑源码：

```text
max_candidate_reads_after_edit = 2
```

目的：

```text
让 agent 在 Edit 失败或源码已变更后，能拿到最新 core_candidate.py/candidate.py，
而不是继续用 stale old_string 猜 patch。
```

### 3. Prompt 行为调整

旧提示倾向：

```text
Use Edit until every safe source-fixable issue cluster has been handled.
Do not stop after the first successful Edit.
```

新提示倾向：

```text
Use short exact old_string snippets.
If Edit fails because source changed, reread once and retry with smaller exact snippet.
Use multiple Edit calls only for clearly source-fixable layout issues.
After a strong improvement, stop and let checker decide whether another round is needed.
Do not chase low-confidence or risk-only residual issues after a substantial improvement.
```

## 实测结果

### 06 核心样本

样本：

```text
<sample_root>/06_新批次_02_巅峰班加油站第二讲_06_第16题_geometry_ecbc9fb5dd8b
```

运行产物：

```text
tmp/quality_repair_runs/06_conditional_loop_20260709_01/result.json
```

结果：

| 指标 | 结果 |
|---|---:|
| 状态 | `SUCCESS_CLEAN` |
| before -> after | `37 -> 0` |
| 轮数 | `1` |
| token | `92,596` |
| input_tokens | `63,919` |
| output_tokens | `28,677` |
| cache_read_input_tokens | `187,567` |

对比上一版：

| 指标 | 上一版 | 本版 |
|---|---:|---:|
| before -> after | `37 -> 0` | `37 -> 0` |
| 轮数 | `2` | `1` |
| token | `184,784` | `92,596` |

结论：06 样本同样清零，但 token 约减半。

### top10 高危样本

运行产物：

```text
tmp/quality_repair_runs/high_risk_top10_conditional_loop_20260709_01/reports/summary.html
tmp/quality_repair_runs/high_risk_top10_conditional_loop_20260709_01/reports/summary.csv
tmp/quality_repair_runs/high_risk_top10_conditional_loop_20260709_01/reports/aggregate.json
```

汇总：

| 指标 | 上一版 | 本版 |
|---|---:|---:|
| 样本数 | `10` | `10` |
| 外部成功 | `8` | `9` |
| SUCCESS_CLEAN | `5` | `6` |
| SUCCESS_DEGRADED | `3` | `3` |
| REPAIR_UNCHANGED | `2` | `1` |
| blocking 总量 | `474 -> 64` | `474 -> 15` |
| blocking 降幅 | `86.5%` | `96.84%` |
| token 总量 | `1,698,253` | `1,936,874` |
| input_tokens 总量 | `1,237,347` | `1,552,898` |
| output_tokens 总量 | `460,906` | `383,976` |
| cache_read_input_tokens 总量 | `2,962,441` | `2,864,251` |

关键变化：

```text
HR0006：旧版 SDK 崩溃/未修，51 -> 51；本版 51 -> 0。
HR0002：旧版 80 -> 4；本版 80 -> 0。
HR0009：旧版 8 -> 6；本版 8 -> 0。
HR0010：本版仍未修好，8 -> 8，是后续重点样本。
```

## 当前判断

这版方案更适合作为当前归档版本，原因：

1. 06 样本显著提效，说明条件停手策略有效。
2. top10 修复质量显著提高，说明没有因为少追二轮而降低整体修复能力。
3. HR0006 的 SDK 运行异常没有复现，说明降低并发/更稳策略下可恢复高危样本。
4. checker/acceptance 仍是唯一采纳裁判，安全边界没有放松。

不应误判为：

```text
这版不是总 token 最低版本。
这版是“修复质量更高，部分样本更省，整体成本因多修好样本而上升”的版本。
```

## 剩余风险

### HR0010 仍需专项处理

现象：

```text
旧版 checker best 到过 8 -> 2，但最终回滚；
本版 8 -> 8，第一轮改坏后回滚。
```

判断：

```text
HR0010 属于“模型误判布局改法/触碰数学字符串风险”样本，
不是单纯二轮策略可以解决。
```

后续建议：

```text
单独审查 HR0010 的 issue digest、core_candidate、rejected_diff。
给 agent 更明确的布局 edit 目标：只改位置/scale/buff，不改 MathTex/Text 字符串。
```

### `old_string` 失败仍未完全消除

本版允许 Edit 后有限重读，但 top10 里仍出现：

```text
String to replace not found
candidate_read_budget_exhausted
post_edit_candidate_read_budget_exhausted
```

后续建议：

```text
进一步降低 old_string 粒度；
或增加本地 line-based patch 工具，减少 Claude Edit 的字符串替换失败。
```

## 验证记录

本版已跑：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider libs/quality_repair/tests -q
```

结果：

```text
203 passed
```

同时跑过：

```bash
git diff --check -- libs/quality_repair/schemas.py libs/quality_repair/agent/controller.py libs/quality_repair/agent/guards.py libs/quality_repair/agent/runner.py libs/quality_repair/pipeline_io.py libs/quality_repair/tests/test_agent_controller_loop.py libs/quality_repair/tests/test_agent_guards.py libs/quality_repair/tests/test_agent_runner_sdk.py libs/quality_repair/tests/test_pipeline_io.py
tools/codex-finish-check.sh
```

结果：

```text
whitespace: ok
sensitive filenames: ok
secret scan: ok
```

## 回滚方式

回到改造前最好版本：

```bash
git switch backup/quality-repair-best-before-conditional-loop-20260709-335d7a3d
```

或从当前分支回退本方案代码提交：

```bash
git revert 2a25e8530
```

如果只想保留代码、不要本文档，可 revert 文档提交，不影响 SDK 修复逻辑。
