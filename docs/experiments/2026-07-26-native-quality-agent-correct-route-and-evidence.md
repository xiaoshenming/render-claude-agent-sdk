# 原生统一 Quality Agent 正确路线与实验证据归档

日期：2026-07-26

归档基线：`34e4e3c`

分支：`codex/manim-quality-agent-native-optimization-20260726`

## 1. 本文目的

本文冻结 `ManimQualityAgent_20260726` 的真实主线架构、17 题与 BBox
Top20 的执行差异、统计口径和证据路径，避免后续把以下不同方案混为一谈：

1. 原生父 Quality Agent + 两个 Reviewer 子 Agent；
2. `reproduction_inputs/MathPi_17` 中的单 Coder Read/Edit 辅助脚本；
3. 后续隔离实验分支中的 no-tools / structured-batch 方案。

当前正确路线是第 1 种。本文只归档证据，不修改 Agent 行为。

## 2. 主线架构

这里的“统一单 Agent”是指一个持续存在的父 Quality Agent 决策会话，不是指
全系统只有一个模型角色。

```text
输入 candidate.py
        ↓
宿主抽取 class Solution
        ↓
保存不可变 R0
        ↓
启动一次父 Quality Agent 会话
        ↓
父 Agent 调用 math_geometry_reviewer
        ↓
Reviewer 读取完整 Solution，返回数学/几何问题
        ↓
父 Agent 调用 animation_lifecycle_reviewer
        ↓
Reviewer 读取完整 Solution，返回漂移/updater/生命周期问题
        ↓
两个 ToolResult 自动进入父上下文
        ↓
父 Agent read_solution(R0)
        ↓
父 Agent 核对证据，record_findings
        ↓
apply_patch 创建 R1
        ↓
validate_revision(R1)：真实 Manim 渲染 + ffprobe
        ↓
inspect_layout(R1)：BBox 快照与重叠检测
        ↓
父 Agent 根据事实决定继续 patch 或 submit
        ↓
可能生成 R2、R3……
        ↓
submit_revision
        ↓
StructuredOutput
        ↓
外层 Harness 独立重新渲染、ffprobe、BBox 复检
        ↓
PROPOSED / HOLD / FAILED
```

角色边界：

| 角色 | 能做什么 | 不能做什么 |
|---|---|---|
| 两个 Reviewer | 只读完整 Solution，输出审查证据 | 修改、提交、验收 |
| 父 Quality Agent | 综合证据、调用受控工具、提出候选 | 直接写文件、宣布最终验收 |
| 宿主 Harness | 应用补丁、管理 revision、渲染、BBox、独立验收 | 代替模型编造修复 |

## 3. 七个受控工具

| 工具 | 作用 |
|---|---|
| `read_solution` | 返回当前 revision 的完整 Solution 与 Hash |
| `check_relation` | 检查确定性数学或几何关系 |
| `record_findings` | 在修改前冻结问题和验收条件 |
| `apply_patch` | 精确块替换并创建新 revision |
| `validate_revision` | 真实渲染并把事实反馈给父 Agent |
| `inspect_layout` | 运行 BBox 探针并返回阻塞问题 |
| `submit_revision` | 将当前候选提交给外层 Harness |

父 Agent没有 Bash、任意 Read/Edit/Write、Glob、Grep、Web 或仓库浏览权限。

## 4. 17 题成功样本的真实路径

样本：

`047_12_春季班全等三角形综合（一）15_03_练习2`

实际调用：

```text
Agent(math reviewer)
→ Agent(lifecycle reviewer)
→ 两个 Reviewer 各 read_solution
→ check_relation × 3
→ 父 read_solution
→ record_findings：5 个问题
→ apply_patch：logic-1，生成 R1
→ validate_revision(R1)
→ apply_patch：logic-2..5，生成 R2
→ validate_revision(R2)
→ inspect_layout(R2)：blocking=0
→ submit_revision(R2)
→ StructuredOutput
→ 外层独立验收
→ PROPOSED
```

该题虽然记录了 5 个问题，但能压缩到两个协调补丁：

1. 修正第一幅图的基础坐标；
2. 一次修正第二幅图坐标、fit 后端点重绑、等长标记和讲解数值。

因此第一次正式布局检查已经为 0，不需要继续布局修复。

## 5. BBox Top20 榜首样本的真实路径

样本：`01KXZSE3J65B70FSW0RB6617YN`

根据不可变 R1～R5、ffprobe、layout detector 和 stderr 还原：

```text
相同 Reviewer / 父 Agent / findings 入口
→ patch + render：R1
→ patch + render：R2
→ inspect_layout(R2)：37
→ patch + render：R3
→ inspect_layout(R3)：36
→ patch + render：R4
→ inspect_layout(R4)：19
→ patch + render：R5
→ 第 4 次 inspect_layout 被次数上限拒绝
→ 未 submit
→ 未 StructuredOutput
→ 未进入外层验收
→ FAILED
```

各 revision 的实际修改包括：

1. R1：总结阶段主动退出残留徽章；
2. R2：修正错误的高亮对象；
3. R3：压缩并缩放总结行；
4. R4：移动总结面板，blocking 从 36 降到 19；
5. R5：调整参数轴阈值标签，已真实渲染，但没有得到下一次 BBox 结果。

因此该题的 `FAILED` 表示流程未完整收敛，不表示没有产生修改或改善。

## 6. 两批真正的分叉点

两批在第一次布局检查之前走相同架构。分叉发生在 `inspect_layout` 的返回值：

```text
17题成功样本：
inspect_layout → blocking=0
→ submit → StructuredOutput → 独立验收

BBox尾部样本：
inspect_layout → blocking>0
→ patch → render → inspect
→ 仍然>0
→ 在清零前耗尽某项预算
```

17 题的逻辑问题常能由一个共同根因修复，例如 fit 后重新绑定端点；该修改也可能
顺带消除漂移造成的重叠。Top20 是按历史 BBox 排名选择的尾部样本，问题通常分散
在多个阶段和对象上，不能由一个共同根因全部解决。

## 7. 必须固定的统计口径

不得再把以下两个指标直接并列：

```text
17题多轮累计最好结果：16/17
Top20单批完整协议结果：0/20
```

17 题冻结单轮复现实际为 `13/17 PROPOSED`；`16/17` 是经过多批 retry 和失败题
补跑后的累计最好结果。

Top20 的 `0/20` 是最终单批中完整走到 `PROPOSED` 的数量。19/20 至少生成过候选
revision，至少 12/20 的已记录 revision 序列出现 blocking 下降。

以后必须分别报告：

1. 单轮完整协议成功率；
2. 多轮累计最好成功率；
3. 进入修改率；
4. 可渲染候选率；
5. BBox 改善率；
6. BBox 清零率；
7. 人工逻辑/视频验收率；
8. 预算或协议失败率；
9. 成功和失败任务各自的 Token。

`PROPOSED` 只能证明候选通过渲染、Hash 和布局预验收，不能代替修复后的独立数学
正确性证明。

## 8. 后续执行防偏规则

1. 默认主线永远是原生父 Quality Agent + 两个前台 Reviewer + 七个受控工具。
2. `reproduction_inputs/MathPi_17/scripts/run_read_edit_batch.py` 只是辅助复现脚本，
   不是统一 Quality Agent 主入口。
3. no-tools、一次性 structured patches 等实验必须留在隔离分支，不得描述成
   原包主线。
4. 昨晚 `34e4e3c` 已经完成迁移和基线实测；没有新的 A/B 目标时，不再重复跑原包
   或重复复现 047。
5. 先读现有 `tool_calls.jsonl`、revision、render、layout 和 stderr，再决定是否
   需要新运行。
6. `FAILED` 必须拆分为完全未修改、已修改未清零、预算退出、schema 退出、
   StructuredOutput 退出和运行时错误。
7. 比较两批数据时必须使用相同的单轮/多轮口径、模型、预算、渲染配置和 detector
   版本。
8. 不新增质量拦截；现有检查只用于采证、诊断、修复反馈和回归。

## 9. Git 与分支边界

| 位置 | 用途 |
|---|---|
| `34e4e3c` | 昨晚迁移与实测基线 |
| `codex/manim-quality-agent-20260726-frozen-baseline` | 冻结基线引用 |
| `codex/manim-quality-agent-native-optimization-20260726` | 原生主线后续归档/优化 |
| `codex/manim-quality-agent-structured-batch-20260726` | 隔离的 structured-batch 实验，不是当前主线 |

## 10. 证据清单与 SHA-256

| 证据 | SHA-256 |
|---|---|
| 昨晚迁移与批量实测报告 | `cd0af850b491d9bfa221136449c70255ea2c96ea955d00b800d0e625175e2e36` |
| 17/20 统计差异审计报告 | `e6f09be117d34fbd50e9d24d47b93009fdd52a1cf5f4bfb8346f422121e46df9` |
| Top20 最终 `batch_summary.json` | `106d6096eb24370deaffae2186bb8363f2eda8ba2ed6cf28674518ab75ce6487` |
| 047 成功调用链 `tool_calls.jsonl` | `cfea5cfb9c2518fea842879154be5ff45f6959dbc22a9c9e1f9ebabc2a9694a5` |
| Top20 榜首失败 stderr | `4e755ec6cc3164920dc824bc83f54bfe1651e37f9934a6940ae19f8a9661a494` |

绝对路径：

- 原始交接包：

  `/home/ming/文档/xwechat_files/wxid_tosdt2o1gwpp22_3585/msg/file/2026-07/ManimQualityAgent_20260726`
- 昨晚实测报告：

  `/home/ming/data/Project/NodeProject/chap5/render-claude-agent-sdk-unified-quality-20260726/docs/experiments/2026-07-26-unified-quality-agent-migration-and-evaluation.md`
- 17/20 审计报告：

  `/home/ming/下载/ManimQualityAgent_17题与BBoxTop20结果差异审计报告_20260726.md`
- 047 工具日志：

  `/home/ming/下载/ManimQualityAgent_20260726-17题实测-retry3/047_12_春季班全等三角形综合（一）15_03_练习2/logs/tool_calls.jsonl`
- Top20 最终结果：

  `/home/ming/下载/ManimQualityAgent_20260726-BBox排行榜Top20最终结果`
