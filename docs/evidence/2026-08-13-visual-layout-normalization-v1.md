# 视觉版式 Reviewer 与 Coder 规范化修复 v1

> **状态：可部署候选（尚未部署）**  
> **仓库：`render-claude-agent-sdk`**  
> **分支：`stable/native-agent`**  
> **部署标签：`visual-layout-normalization-v1-20260813`**  
> **功能提交：`a421bf0`**  
> **修改前备份：`codex/visual-layout-normalization-baseline-20260813` → `172f303`**

## 一眼看懂

本版本增加第三路只读源码 Reviewer，专门检查最终可见版式，并把问题转成
Coder 可直接执行的 `normalization_contract`。Coder 仍使用原有程序、模型、
Read/Edit 工具和真实渲染/BBox 验证；本版本没有增加 AST/正则后处理，没有修改
Header、生成提示词或 BatchOps，也没有新增质量拦截。

目标链路：

```text
V0 最终源码
  → 数学 Reviewer
  → 动画生命周期 Reviewer
  → 视觉版式 Reviewer
  → 结构化问题合同
  → Quality Coder 整体规范化
  → 真实 Manim 渲染 + BBox
  → Final Assurance 对最终源码重新执行三路 Reviewer
```

## 本次到底改了什么

### Visual Layout Reviewer

只读取 `class Solution`，不看视频帧、不编辑代码、不判断数学。它检查：

- 同角色字号和跨页缩放是否一致；
- 每屏成员是否完整进入同一个页面组；
- 阅读顺序、左边缘、行距和等式锚点是否稳定；
- 是否过早分页、严重留白或无必要缩小；
- 是否使用 Header 的正式安全区；
- 是否存在逐对象固定缩放、魔法位移或跨页漂移。

每个页面问题必须输出：

- `page_members`
- `reading_order`
- `target_region`
- `arrangement`
- `fit_policy`
- `anchor_policy`
- `preserve`

### Quality Coder

只在确认视觉 Reviewer 的问题确实存在时执行版式规范化：

- 先完整收集页面成员，再按阅读顺序统一 `arrange`；
- 页面内等式使用局部 `make_aligned_relation_stack`，不把已做全局定位的
  `make_aligned_relation_panel` 嵌入页面；
- 使用 `GlobalConfig.RIGHT_X`、`RIGHT_W`、`STEP_MAX_TOP`、
  `STEP_MIN_BOTTOM`；
- `RIGHT_X` 按左边界解释，使用 `RIGHT_X + padding`；
- 根据完整页面边界计算缩放，同类页面使用共同缩放比例；
- 禁止用固定 `scale(0.35)`、魔法位移或自造 board anchor 替代拟合；
- 保留数学内容、图形语义、动画顺序和生命周期。

这部分是 Coder 的条件性操作合同，不是新的后处理器。Coder 的 Python 实现、
权限、工具注册和执行方式均未修改。

## Final Assurance 是否同步

**已同步。** Final Assurance 的 `_native_reviewers()` 复用
`operator.reviewers.run_reviewers()`，因此会对最终交付源码重新执行：

1. `math_geometry_reviewer`（必需）
2. `animation_lifecycle_reviewer`（必需）
3. `visual_layout_reviewer`（best-effort）

终审提示词和结构化 evidence ID 已登记
`reviewer:visual_layout_reviewer`。视觉 Reviewer 调用失败时只标记证据不可用，
不得阻断；源码推测若没有终审工具证据支持，也不得直接升级成 high/blocking。

## 验证证据

### 自动测试

```text
157 passed
```

覆盖 Reviewer 注册、重试、终审回执、Coder 规范化合同及统一 SDK 集成路径。

### 真实 V0 修复

样本：`fc2798f8-94c4-483d-a78d-59b61df7d36e` 的 V0 源码。

- 三路 Reviewer 均实际运行；
- Coder 未接收人工 V3 源码或截图；
- 修后源码使用局部 relation stack、完整页面组、共同缩放和 Header 安全区；
- 手工独立 Manim 渲染成功；
- 视频：1920×1080、H.264、AAC、86.47 秒；
- 独立 BBox：99 个状态，`blocking_count=0`，`raw_issue_count=0`。

本地证据：

- 修后源码：`/home/ming/下载/fc2798_v0_layout_normalization_exact_20260813/harness/agent_runtime/R2/candidate.py`
- 修后视频：`/home/ming/下载/fc2798_v0_layout_normalization_exact_20260813/r2_manual_media/videos/candidate/1080p15/Solution.mp4`
- BBox 报告：`/home/ming/下载/fc2798_v0_layout_normalization_exact_20260813/r2_manual_probe/layout_report.json`

第二次完整兼容入口在 acceptance 之前触发外层固定 case timeout；R2 的独立真实
渲染和布局探针随后单独完成。因此不得把该次外层超时描述成 R2 渲染失败，也不得
把本样本结论扩大成“所有任务首个候选必定一次命中”。

## 部署与回滚

部署时固定使用标签：

```bash
git fetch --tags
git checkout visual-layout-normalization-v1-20260813
```

部署前至少确认：

```bash
git rev-parse --short HEAD
python -m pytest -q tests/unit/operator \
  tests/unit/assurance/test_practical_delivery_policy.py \
  tests/integration/test_unified_operator_sdk.py
```

回滚只需切回修改前提交或备份分支：

```bash
git checkout 172f303
# 或
git checkout codex/visual-layout-normalization-baseline-20260813
```

## Blocking Policy

本版本不新增 hard gate、reject、跳过渲染或 fail-closed。视觉检查用于发现问题、
指导修复、终审采证和回归；视觉 Reviewer 自身失败保持 fail-open。

## 当前边界

- 已证明目标样本可在一个 Coder 会话内自动收敛，不等于所有样本首个 R1 必然命中；
- 本版本尚未部署到 BatchOps 或服务器；
- 部署后仍需用真实任务核对运行 release、三审回执、修订源码、最终视频和终审证据。
