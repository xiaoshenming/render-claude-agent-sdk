# 原生 Quality Agent 优化批次 Claude Review 交接

日期：2026-07-26

## 1. 请 Claude Review 什么

请重点审查以下问题，不要只检查代码能否运行：

1. 本轮是否忠实实现了原生父 Quality Agent、两个前台 Reviewer、受控工具和真实验证闭环；
2. 新增的环境适配、预算、超时、日志和失败恢复是否存在隐性阻断或错误成功；
3. 为什么可观测性明显改善，但逻辑题单轮成功率从 13/17 降到 12/17；
4. 为什么 BBox Top20 仍为 0/20 完整提交，且部分题修改后发生回归；
5. 如何用最小改动提高收敛率，而不是继续无界增加轮次、Token 或拦截；
6. 失败时 Token 仍可能记为 0、StructuredOutput/turn limit 抹掉已生成候选的问题如何修复；
7. 当前全量测试的 7 个失败中，哪些是本分支新增，哪些是迁入基线问题。

## 2. 工作目录与版本

```text
工作目录：
/home/ming/data/Project/NodeProject/chap5/render-claude-agent-sdk-native-optimization-20260726

分支：
codex/manim-quality-agent-native-optimization-20260726

本交接前 HEAD：
3f1325e5c7d0d7a373a38c824ee5601c19e26a23
```

主要提交：

| 提交 | 内容 |
|---|---|
| `2abf6cb` | R0 证据、失败恢复、BBox diff、调用归属和批处理稳定性 |
| `88c1580` | 多批次共享渲染并发槽 |
| `51a843a` | 子进程源码包导入环境 |
| `8ba7af3` | Provider 工具调用与运行时预检 |
| `95ffe1b` | 避免新旧 Provider 凭证污染 |
| `c671fe5` | 显式清空继承的旧认证令牌 |
| `be98fcb` | Reviewer 附加元数据宽容规范化 |
| `41621b5` | Agent、渲染和外层排队超时对齐 |
| `3f1325e` | 归档优化后 37 题正式实测 |

没有 push，没有部署，没有加入新的质量 fail-closed gate。

## 3. 当前架构

```text
批前 Provider/runtime/source preflight
        ↓
宿主保存 R0，并真实 render + ffprobe + BBox
        ↓
启动一个持续存在的父 Quality Agent 会话
        ↓
父 Agent 发布两个前台 Reviewer
├── math_geometry_reviewer
└── animation_lifecycle_reviewer
        ↓
两个 Reviewer ToolResult 自动回到父上下文
        ↓
父 Agent read_solution
        ↓
record_findings
        ↓
apply_patch → R1...R5
        ↓
validate_revision：真实 Manim render + ffprobe
        ↓
inspect_layout：BBox 与 R0 diff
        ↓
继续修复或 submit_revision
        ↓
StructuredOutput
        ↓
外层 Harness 独立重渲染、ffprobe、BBox
        ↓
PROPOSED / HOLD / FAILED
```

预算：

```text
record_findings = 4
apply_patch = 5
validate_revision = 5
inspect_layout = 5
submit_revision = 1
max_turns = 24
max_tool_calls = 32
Agent max elapsed = 1800 秒
case timeout = 3600 秒
全局渲染并发 = 10
```

## 4. 上一批与本轮的正确对比

### 4.1 不能混用的口径

上一批文档最初报告的 `16/17` 是多批 retry 后的累计最好值，不是一次冻结批次。
上一批同口径的冻结单轮结果是 `13/17`。本轮是一次正式冻结批次 `12/17`。

因此正确结论是：本轮逻辑题的单轮完整协议成功率没有提高，反而少成功 1 题。

### 4.2 同口径结果

| 指标 | 上一批冻结单轮 | 本轮优化批 | 变化 |
|---|---:|---:|---|
| 逻辑题 PROPOSED | 13/17 | 12/17 | -1 |
| 逻辑题单轮成功率 | 76.5% | 70.6% | -5.9 个百分点 |
| BBox PROPOSED | 0/20 | 0/20 | 无变化 |
| BBox 进入候选/修改 | 至少 19/20 | 18/20 | 略降 |
| BBox blocking 下降 | 至少 12/20 | 12/20 | 基本持平 |
| BBox 清零 | 0/20 | 0/20 | 无变化 |
| R0 render/BBox 统一基线 | 不完整 | 完整 | 改善 |
| 失败调用与最后 revision 留存 | 不完整 | 完整度明显提高 | 改善 |
| Reviewer/父 Agent 调用归属 | 不完整 | 有 caller/agent_id/type | 改善 |

### 4.3 Token

| 批次 | 已记录 Token | 说明 |
|---|---:|---|
| 上一批逻辑累计成功结果 | 1,266,710 | 只统计当时 16 个成功 decision，失败消耗缺失 |
| 本轮逻辑 17 题 | 1,037,598 | 失败 SDK 异常仍可能显示 0，仍非完整成本 |
| 本轮 BBox 20 题 | 648,220 | 同样存在异常前 usage 未刷新的缺口 |
| 本轮合计 | 1,685,818 | 不能与上一批 1,266,710 直接计算节省比例 |

本轮不能据此宣称 Token 更省。两个统计范围不同，而且两边都漏掉部分失败消耗。
本轮的优势是已经明确识别并归档了这个缺口。

## 5. 本轮真正改善的部分

1. 模型调用前执行真实最小 `tool_use`，避免 Key 存在但协议不可用；
2. 固化 Python、SDK、Docker、FFmpeg、runtime stubs 和源码编译信息；
3. Agent 并发与渲染并发拆开，多个批次共享同一个文件信号量；
4. R0 在 Agent 启动前真实渲染，后续 BBox 可以计算 resolved、persistent、introduced；
5. Reviewer 附加 `severity/notes` 不再导致整题 schema 失败；
6. 每次工具调用可区分父 Agent、数学 Reviewer 和生命周期 Reviewer；
7. 失败时保存最后 revision、工具链和 failure，而不是只剩一个 FAILED；
8. 已 submit 但终态摘要格式失败时可以从 session 权威状态恢复候选；
9. 认证令牌和 API Key 不再相互污染；
10. Docker 排队时间不再被错误算入短渲染超时。

## 6. 本轮没有改善、甚至回退的部分

### 6.1 逻辑题

5 个失败题都已经修改到 R3～R5，但在 1800 秒会话时限结束：

| 样本 | 最后 revision | 本轮终态 |
|---|---:|---|
| 017 等边三角形 | R5 | TimeoutError |
| 035 腰上的高求底角 | R5 | TimeoutError |
| 042 线段和差证明 | R3 | TimeoutError |
| 047 全等练习2 | R4 | TimeoutError |
| 080 倍长中线 | R4 | TimeoutError |

这表明“预算数字彼此一致”仍不等于“墙钟时间足够”。真实渲染占用了大量会话时间，
父 Agent 可能已经生成有效候选，却来不及 submit 和 StructuredOutput。

### 6.2 BBox

- 18/20 进入修改，但没有一题完整清零并提交；
- 平均 21.3 轮，已贴近 24 轮上限；
- 有些题先改善后回归，例如 `01KY0F38C8DJZ70A4KSBJTH4G4` 从 5 降到 1，
  后续又回到 5；
- 失败仍集中在 turn、StructuredOutput、patch budget、cache-read 和 timeout；
- 共享 root 聚类已经提供给模型，但未证明父 Agent 能稳定把它变成协调补丁。

## 7. 建议 Claude 优先检查的文件

```text
scripts/batch_runtime.py
scripts/run_unified_quality_batch.py
scripts/docker_manim_python
src/manim_quality/agents/_controls.py
src/manim_quality/agents/usage.py
src/manim_quality/operator/agent.py
src/manim_quality/operator/artifacts.py
src/manim_quality/operator/cli.py
src/manim_quality/operator/failure_artifacts.py
src/manim_quality/operator/harness.py
src/manim_quality/operator/runtime_tools/layout_diff.py
src/manim_quality/operator/runtime_tools/services.py
src/manim_quality/operator/session.py
src/manim_quality/operator/tool_registry.py
```

设计方案：

`docs/experiments/2026-07-26-native-quality-agent-detail-optimization-plan.md`

本轮结果：

`docs/experiments/2026-07-26-native-quality-agent-37-case-optimized-run.md`

旧基线与口径校正：

```text
docs/experiments/2026-07-26-unified-quality-agent-migration-and-evaluation.md
docs/experiments/2026-07-26-native-quality-agent-correct-route-and-evidence.md
```

## 8. 正式产物路径

本轮正式结果：

`/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726`

汇总：

```text
/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726/logic17/batch_summary.json
/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726/bbox20/batch_summary.json
```

上一批证据：

```text
/home/ming/下载/ManimQualityAgent_20260726-BBox排行榜Top20最终结果
/home/ming/下载/ManimQualityAgent_17题与BBoxTop20结果差异审计报告_20260726.md
```

不要把以下中途诊断目录当成正式结果：

```text
/home/ming/下载/ManimQualityAgent-native-optimized-37-20260726
/home/ming/下载/ManimQualityAgent-native-optimized-37-final-20260726
/home/ming/下载/ManimQualityAgent-native-optimized-37-final2-20260726
```

## 9. 当前验证状态

- 本轮核心模块定向测试：`183 passed`；
- `git diff --check`：通过；
- 全量测试：`1462 passed, 7 failed`。

全量失败不能忽略：

1. `scripts/batch_runtime.py` 的 `preflight` 超过函数 60 行限制；
2. `scripts/batch_runtime.py` 超过单文件 300 行限制；
3. 一个旧 SDK 集成用例仍使用旧工具名；
4. 三个 Artifact `file:///` 路径测试失败；
5. 一个 frozen holdout hash 不一致；
6. 一个 vendor source hash 不一致。

其中工程行数限制和旧工具名测试应在合并前处理；冻结哈希必须先确认来源，不能为了
变绿盲目刷新。

## 10. 推荐的最小下一步

1. 不重新从 R0 跑 37 题；
2. 从 5 个逻辑失败题的最后已验证 revision 继续，单独测“候选恢复后提交”；
3. 把外部真实渲染等待从父 Agent 推理墙钟预算中拆出，而不是继续扩大模型轮数；
4. BBox 只选择 3 个代表题测试共享 root 协调 patch；
5. 每个 ResultMessage/AssistantMessage 到达时增量写 usage，避免异常后 Token 为 0；
6. submit 成功后终态 JSON 失败应直接恢复，不再消费额外 Agent 轮次；
7. 修复工程行数和旧工具名测试后再执行全量回归；
8. 所有 checker 保持 evidence-only，不新增布局质量拦截。

## 11. 给 Claude 的建议 Review 命令

```bash
cd /home/ming/data/Project/NodeProject/chap5/render-claude-agent-sdk-native-optimization-20260726
git status --short
git log --oneline --decorate -12
git diff 34e4e3c..HEAD -- \
  scripts \
  src/manim_quality/agents \
  src/manim_quality/operator \
  tests
.venv/bin/python -m pytest -q tests/unit/operator tests/unit/agents
.venv/bin/python -m pytest -q
```

Claude 应把审查结论分成：

```text
P0：会产生错误成功、源码破坏或证据造假
P1：导致有效候选丢失、超时或明显 Token 浪费
P2：可观测性、维护性和测试债务
```

请避免把“增加硬 gate”作为默认解决方案。
