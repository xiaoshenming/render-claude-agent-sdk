# Quality Repair SDK Core Candidate 视图拆分方案

日期：2026-07-09

## 结论

`quality_repair` 的 Claude Agent SDK 修复链路应该新增一个 **SDK-only 的 core candidate 视图**，让 Agent 只读取和编辑题目核心代码，最终仍合成完整 `candidate.py` 给 checker、layout probe、Manim render 和证据归档使用。

不建议第一版把最终运行代码改成真实 `import` 包。更稳的路线是：

```text
完整 candidate.py
  -> 拆分出固定 prelude + 可编辑 core_candidate.py
  -> SDK 只读 layout_issue_digest.json + core_candidate.py
  -> SDK 只编辑 core_candidate.py
  -> composer 合成完整 candidate.py
  -> checker/layout_probe/render 仍只使用完整 candidate.py
```

## 背景问题

当前 issue-only 路线已经把布局输入压缩到 `layout_issue_digest.json`，但 SDK 仍然需要读取完整 `candidate.py`。实际样本里，`candidate.py` 的大部分内容是稳定前置代码：

- imports、Manim config、颜色常量。
- `GlobalConfig`。
- `BaseConfigScene`。
- 布局 helper、TTS helper、panel helper、兼容别名。

这些内容通常不需要 Agent 修改，但会反复进入 SDK 上下文。

## 数据依据

抽样结论：

```text
06 样本：
candidate.py 约 52KB / 1131 行
prelude 约 880 行
Scene 核心约 251 行
```

最近 200 个 layout workdir 抽样：

```text
candidate.py 平均约 56.8KB / 1239 行
prelude 平均约 949 行，占 76.6%
Scene 核心平均约 291 行
```

高危样本池 round_02 的 44 个样本：

```text
candidate.py 合计：2,631,159 bytes
前置 helper 合计：1,926,647 bytes，占 73.2%
业务 Solution 部分：704,512 bytes
layout_issue_digest 合计：101,578 bytes
```

因此，拆出 core 视图后，candidate 代码侧输入有机会减少约 70%。考虑 SDK 多轮工具调用、hidden thinking、Edit payload 和 digest 大小，实际总输入 token 更现实的目标是下降 15% 到 25%。

## 不直接做 import 包的原因

第一版不建议把最终 `candidate.py` 改成：

```python
from xxx import BaseConfigScene, GlobalConfig
```

原因：

- Docker layout probe 当前主要准备 `/work/candidate.py`，不保证带上仓库包。
- demo render 容器也主要拷贝当前脚本、assets、custom services，不保证同步 prelude 包。
- `compile(candidate.py)` 无法发现运行时 import 缺失，问题会拖到 probe/render 阶段暴露。
- 历史产物会失去单文件可复现性。
- prelude 包版本变化可能影响旧 core 的渲染结果，审计难度会上升。

所以第一版应保持最终产物单文件自包含。

## 推荐架构

### 1. Workdir 保留完整 ABI

`workdir/candidate.py` 继续作为完整 Manim 文件存在，供以下环节使用：

- checker。
- layout probe。
- render。
- acceptance。
- evidence diff。
- 最终 `RepairResult.code_path`。

### 2. 新增 SDK 可编辑视图

在 layout profile 的 workdir 中新增：

```text
core_candidate.py
candidate_prelude.txt
candidate_core_map.json
```

含义：

- `core_candidate.py`：只包含需要 Agent 阅读和修改的 Scene 类或 `construct()` 核心代码。
- `candidate_prelude.txt`：冻结的完整前置文本，默认不给 SDK 读取。
- `candidate_core_map.json`：记录拆分边界、Scene 类名、起止行号、合成方式、hash。

### 3. SDK 只读写 core

SDK runner 的 layout 模式只允许：

```text
Read layout_issue_digest.json
Read core_candidate.py
Edit core_candidate.py
```

不允许读：

```text
candidate.py
candidate_prelude.txt
layout_context.json
facts/*
```

如果拆分失败，降级回当前完整 `candidate.py` 路线，保持 fail-open。

### 4. 每轮 Edit 后立即合成

controller 不能等到最终 acceptance 才合成。正确顺序是：

```text
SDK 编辑 core_candidate.py
  -> composer 合成完整 candidate.py
  -> checker.run_check(candidate.py)
  -> blocking 下降则采纳
  -> 不下降或变差则回滚 best snapshot
```

原因是 controller 每轮都要依赖 checker 判断是否进步。

### 5. 证据归档

每轮至少保留：

```text
core_candidate.before.py
core_candidate.after.py
core_diff.patch
candidate.full.before.py
candidate.full.after.py
full_diff.patch
compose_report.json
```

最终对外仍以完整 `candidate.py` diff 为主，core diff 作为调试证据。

## 拆分策略

第一版使用 AST 保守拆分：

1. 解析完整 `candidate.py`。
2. 找到第一个包含 `construct()` 方法的 Scene 类。
3. 将该类之前的内容作为 prelude。
4. 将 Scene 类到文件结尾作为 core。
5. 如果文件尾部还有 `if __name__ == "__main__"` 或辅助入口，一并归到 core 或保留在合成尾部。
6. 如果 AST 解析失败，或找不到 Scene 类，直接回退完整 `candidate.py` 路线。

第一版不抽取 Scene 内部局部 helper，避免过度拆分导致 Agent 缺上下文。

## Prompt 变化

layout prompt 应从：

```text
Read layout_issue_digest.json first.
Read candidate.py once.
Edit candidate.py.
```

改为：

```text
Read layout_issue_digest.json first.
Read core_candidate.py once.
Edit only core_candidate.py.
Do not read candidate.py or candidate_prelude.txt.
The full candidate.py will be composed and checked automatically.
```

重点是让 Agent 清楚：

- 它看到的是核心可编辑视图。
- 不需要读前置 helper。
- 不需要自己处理合成。
- 修复目标仍是布局重叠，不是重写框架。

## 验收指标

第一批实验建议使用 06 样本和高危样本池 `blocking_count > 10` 的样本。

核心指标：

```text
1. 修复成功率不能低于当前 issue-only 完整 candidate.py 路线。
2. 变差样本数量必须为 0。
3. active 修复样本平均 input tokens 下降 15% 到 25%。
4. candidate.py Read 次数应降为 0。
5. core_candidate.py Read 次数通常为 1。
6. 合成后的 candidate.py 必须可被 checker/layout_probe/render 使用。
```

失败时的判断：

- 如果修复率下降明显，说明 core 过窄或 prompt 不清晰。
- 如果 token 没降，优先查工具循环、Edit 次数、hidden thinking 和 digest 大小。
- 如果 render/probe 失败，优先查 composer 合成边界。

## 回滚策略

该方案必须保持 fail-open：

- 拆分失败：回退完整 `candidate.py` SDK 路线。
- 合成失败：不采纳本轮修改，保留原始 `candidate.py`。
- checker 变差：回滚到 best snapshot。
- SDK 未改动：记录 `output_identical_to_input`，不影响最终可播放视频。

不得因为 core 拆分失败新增质量类 hard gate。

## 推荐落地顺序

1. 新增 `core_candidate_view` 拆分与合成模块。
2. 在 `build_workdir` 中生成 core 视图文件。
3. 修改 layout runner 的 allowed files、prompt 和 edit hook。
4. 修改 controller：SDK Edit 后先合成完整 `candidate.py`，再 checker。
5. 增加 evidence 输出 core/full 双 diff。
6. 用 06 样本单例验证。
7. 用高危样本池跑 A/B：完整 candidate 路线 vs core 视图路线。
8. 再接入 `tools/solve_pre_stream_demo` 长跑批次。

## 最终决策

采用 **SDK-only core candidate 视图 + 完整 candidate.py 合成验收**。

不采用第一版真实 import 包。

这个方案的目标不是改变 Manim 代码生成格式，而是减少 Claude Agent SDK 的无效上下文，让它更集中地读取和修改真正可能产生布局重叠的 Scene 核心代码。
