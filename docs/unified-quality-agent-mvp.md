# 统一 Quality Agent MVP 使用说明

## 1. 当前状态

该分支提供一个可运行的 Claude Agent SDK 原生双 Reviewer MVP：

```text
candidate.py
  -> QualitySession(R0)
  -> 提取唯一 class Solution(BaseConfigScene)
  -> Claude SDK 父 QualityOperatorAgent
     -> math_geometry_reviewer（前台、只读）
     -> animation_lifecycle_reviewer（前台、只读）
  -> 父 Agent 使用 7 个受控工具
     -> validate_revision 真实渲染并用 ffprobe 验证视频
     -> inspect_layout 复用渲染缓存执行多快照 BBox 探针
     -> detector 只把紧凑 blocking issues 返回 Agent
  -> R1 起的动态候选修改（预算按 R0 blocking 压力定为 5..7 个 Patch）
  -> submit_revision
  -> 独立 OuterAcceptanceGate
  -> PROPOSED 或 HOLD/回滚 R0
  -> 固定审计包
```

这是该 MVP 唯一支持的 Agent 路线。旧单 Agent、A/B fallback、独立
`Reviewer -> Coder` 编排不属于此入口。

模型只能看到 `Solution` 类，不读取文件头、框架 helper、合同函数或其他文件。
真实样本从 66,148 字符缩到 11,078 字符，模型输入源代码减少约 83.3%。

## 2. 原生 Reviewer 与七个工具

两个 Reviewer 都通过 SDK `AgentDefinition` 注册，必须显式
`run_in_background=false`。每个 Reviewer 最多 5 turns，只能使用
`read_solution` 和 `check_relation`，各自最多读取一次 Solution，不能编辑、
不能调用 Bash、文件工具、Web、Skill 或嵌套 Agent。

| 工具 | 作用 | 最大调用 |
| --- | --- | ---: |
| `read_solution` | 读取当前 revision 的完整 Solution 与 Hash | 父/每个 Reviewer 各 1 |
| `check_relation` | 确定性数值或几何关系检查 | 6 |
| `record_findings` | 分批冻结逻辑、布局问题 | 4 |
| `apply_patch` | 精确块级替换并创建 child revision | 动态 5..7 |
| `inspect_layout` | 检测当前 revision 的重叠事实 | Patch 预算 + 1（6..8） |
| `validate_revision` | 外部检查并把结果反馈给 Agent | 同 Patch 预算（5..7） |
| `submit_revision` | 提交候选给外层 Harness | 1 |

`apply_patch` 预算不是常量，由 Harness 在会话开始前按 R0 基线布局的
`blocking_count` 一次性确定：`<=2` 给 5，`3..8` 给 6，`>8` 给 7。该预算只能被抬
高，不能在会话中被下调。`validate_revision` 与之等值，`inspect_layout` 多一次，
用于提交前对最终 revision 再复检一遍。`patches_remaining` 和
`findings_batches_remaining` 会随工具返回值一起回给 Agent，让它据此决定是继续
修还是尽早提交。

CLI 全局默认限制为 24 turns、40 次工具调用。工具自己的上限不能突破全局上限。

会话另有 `max_elapsed_ms = 1_800_000`（30 分钟）的硬时限，但它**只计模型推理与
协议时间**：外部渲染和 BBox 探针的墙钟已从中剔除，工具执行期间会话 deadline 被
挂起，执行完再按同一段共享窗口平移恢复。因此一次长渲染不会吃掉 Agent 的思考预
算。验证类工具（`validate_revision`、`inspect_layout`）单次执行超时为 2700 秒，
覆盖「渲染 1200 秒 + 探针 1200 秒」这条链。

父 Agent 除两个命名 Reviewer 和上述 MCP 工具外，没有 Bash、Read、Edit、
Write、Glob、Grep、Web、Skill 或任意路径权限。所有文件写入都由 Harness 完成。

父 Agent 当前使用 `prompts/quality_operator_v2.md`，`prompt_version` 标记为
`quality-operator-v2`。相对 v1 增加三条收敛策略：

1. **共享根因协调修复**：`inspect_layout` 返回 `comparison_to_R0`。当
   `shared_roots` 非空时，`affected_issue_count` 最大的那一项代表一整簇碰撞背后
   的同一个缺陷，应设计一次协调修复（移动、重排或缩放共享父 VGroup，或改共享
   布局常量）让整簇一次清掉，而不是逐个碰撞消耗 Patch 预算。协调移动可能打回
   已修好的区域，因此每次复检都要比较 `resolved_count`、`persistent_count`、
   `introduced_count`；`introduced_count` 上升就把 Patch 收窄到具体子元素。
2. **同轮批量验证**：`validate_revision` 和 `inspect_layout` 都只需要当前
   revision id，必须在同一条 assistant 消息里一起发出、一起读回执，不要为了等
   验证结果单独花一个 turn。只有 `apply_patch` 必须单独发，因为新 revision id
   和 code Hash 在回执返回前未知。
3. **预算感知及时提交**：一旦当前 revision 同时拿到 `validate_revision` 的
   `passed` 和 `inspect_layout` 的 `blocking_count=0`，就立即提交，不再追加优化
   或润色轮次。因为只有当前 revision 可提交，多修一轮等于拿已证明的候选去赌。
   `patches_remaining` 降到 1 或 0 时停止探索。

## 3. 硬保护

- `R0` 永久不可变。
- 题目文本和 `problem_hash` 不可变。
- 没有冻结 finding 不能修改。
- `apply_patch` 必须绑定当前 revision ID 和 code Hash。
- 重复 code Hash、无改善重试、Patch 次数超出当前预算自动停止。
- logic 和 layout 不能混为一个 revision。
- logic Patch 之后才允许 layout Patch，layout 之后不能回头改 logic。
- layout Patch 改变语义指纹时立即拒绝。
- 验证失败、当前仍有 blocking overlap 时不能提交。
- Agent 必须实际调用 `submit_revision`，结构化输出不能伪造提交。
- 两个 Reviewer 的 Agent Tool ID、Hook `agent_id`、停止事件、ToolResult 和父
  Agent 后续消息必须形成同一条可验证身份链。
- Claude Code 自动附加的 `agentId` 和 `<usage>` trailer 必须被严格解析，并与
  Hook 身份一致；未知 trailer 失败关闭。
- Agent 内部 Validator 和最终验收 Validator 必须是不同实例。
- 最终门禁要求独立完整重渲染和独立完整布局复检；compile-only 永远不能交付。

## 4. Python 主入口

生产接入使用：

```python
from manim_quality.operator.harness import QualityHarness
```

需要注入五类对象：

1. `QualityOperatorAgent`
2. `RelationChecker`
3. Agent 内部 `LayoutInspector`
4. Agent 内部 `RevisionValidator`
5. 独立验收用 `LayoutInspector` 和 `RevisionValidator`

`RevisionValidator.validate()` 必须返回 `ValidationOutcome`，并原样绑定当前
`revision_id`、`code_hash`、`problem_hash`。MVP 预验收只有在
`details["rendered"] is True` 时才可能输出 `PROPOSED`。

`LayoutInspector.inspect()` 必须返回：

```json
{
  "revision_id": "R1",
  "code_hash": "sha256:...",
  "problem_hash": "sha256:...",
  "verified": true,
  "blocking_count": 0,
  "issues": []
}
```

最终验收使用的两个适配器必须重新运行真实渲染和 detector，不能复用 Agent
会话中的自报结果。

## 5. 真实运行 CLI

默认 CLI 运行完整渲染和布局闭环：

```powershell
$env:ANTHROPIC_BASE_URL = "https://your-anthropic-compatible-endpoint"
$env:ANTHROPIC_AUTH_TOKEN = "<runtime-secret>"

.\.venv\Scripts\python.exe -m manim_quality.operator `
  --candidate D:\task\candidate.py `
  --workspace D:\task `
  --output D:\runs\quality-smoke-001 `
  --model your-model `
  --manim-python D:\runtime\python.exe `
  --runtime-python-path D:\runtime\stubs `
  --assets-dir D:\task\assets
```

如果 `candidate.py` 没有模块 docstring 或顶部题目注释，增加：

```text
--problem D:\task\problem.txt
```

`--runtime-python-path` 可重复传入。它用于生成代码需要的受控运行依赖，
`--assets-dir` 用于背景和 Logo 等只读素材。Agent 不会获得这些路径。

仅诊断 SDK 协议时可增加 `--compile-only`。该模式最终必定 `HOLD`，原因包含
`full_render_not_verified` 和 `full_layout_not_verified`。

真实模式中，Agent 内部和外层验收分别使用独立 `RuntimeToolchain`，因此最终门禁
会重新渲染、重新导出 BBox、重新执行 detector。

## 6. 审计包

跑完一次（`PROPOSED` 或 `HOLD`）输出：

```text
run/
  input/
    problem.snapshot
    candidate.R0.py
  revisions/
    R0.baseline.py
    R1.logic.py          # 文件名为 R<n>.<scope>.py，n 随动态预算可到 R7
    R2.layout.py
  evidence/
    findings.json
    revisions.json
    layout.R0.baseline.json # 会话开始前的 R0 基线布局，同时决定 Patch 预算
    validation.R1.json      # 外层独立验证事实
    layout.R1.json          # 外层独立布局复检事实
  logs/
    agent_call.json
    parent-sdk-messages.jsonl
    subagent-results.json
    tool_calls.jsonl
    run_summary.json
  output/
    decision.json
    proposed_candidate.py # 仅 PROPOSED，仍不是交付成品
    rollback.R0.py        # HOLD 时
```

`run_summary.json` 包含 turns、工具调用数、输入/输出/cache Tokens、总 Tokens、
Agent 耗时、`external_tool_ms`、`usage_complete`、提交 revision、最终 revision、
回滚 revision 和门禁原因。`external_tool_ms` 是被排除在推理时限之外的外部工具墙
钟，`usage_complete` 表示 SDK 用量是否已完整对账。

跑挂（Agent、工具、运行时或预算异常）时改为写失败归档，同样保留可追溯证据：

```text
run/
  evidence/
    layout.R0.baseline.json
  logs/
    agent_call.partial.json
    parent-sdk-messages.jsonl # 中断时仍有真实内容
    subagent-results.json     # 中断时仍有真实内容
    tool_calls.jsonl
    failure.json
  output/
    decision.json                # {"decision": "FAILED", ...}
    last_candidate.<Rn>.py       # 中断时的当前 revision
    best_render_passed.<Rn>.py   # 可选：过程中渲染通过的最好候选
```

`failure.json` 含 `status`（`FAILED_TIMEOUT` / `FAILED_PATCH_BUDGET` /
`FAILED_RENDER` / `FAILED_REVIEWER_SCHEMA` 等）、`error_type`、`error`、
`last_revision_id`、`last_revision_code_hash`、`best_render_passed`
（`{revision_id, blocking_count, layout_inspected}`）、`tokens`、`usage_complete`、
`external_tool_ms`、`turns`、`tool_calls`。

`best_render_passed.<Rn>.py` 是**证据不是交付物**：它只表示该 revision 当时渲染
通过，可能仍带 blocking 布局问题，也可能根本没做过布局复检（此时
`layout_inspected` 为 `false`）。不要把它当成可直接使用的成品。

`subagent-results.json` 保存两个 Reviewer 的结构化正文、真实 `agent_id`、
生命周期时间、父消息消费绑定以及 SDK 报告的独立 Tokens/工具次数。

`PROPOSED` 只表示该候选通过了统一 Agent MVP 的独立预验收。生产平台仍须将其
写入正式 Revision Repository，再经过现有 `FinalConsistencyGate`、状态转换和
交付证书流程，才能成为 `ACCEPTED` 成品。

## 7. 已验证真实 Smoke

2026-07-25 使用一份真实 70,973 字符 `main.py` 完成协议 smoke：

- 两个 Reviewer 均前台启动、各调用一次 `read_solution` 并返回结构化结果。
- 父 Agent 再读取一次 Solution，合并重复问题为一个 finding。
- 创建一个精确逻辑 Patch，只把 `edge_BF`、`edge_AE` 纳入已有最终变换组。
- 共 10 turns、11 次工具调用、79.8 秒。
- 总计 50,068 Tokens：输入 19,466、输出 906、cache read 29,696。
- 输出 `HOLD`，原因是 compile-only CLI 没有绑定真实渲染和布局 detector。

该结果证明 Agent 协议、权限、Solution-only 上下文、Revision 和审计链可运行，
不证明视频已经通过真实渲染或布局验收。

## 8. 真实工具链状态

已完成薄适配器：

- `RevisionWorkspace`：按 revision 隔离代码和身份清单，不修改 R0。
- `ManimRenderer`：argv 调用真实 Manim，完整日志落盘，用 ffprobe 验证 MP4。
- `BBoxProbe`：复用同一 revision 的 Manim/TeX 缓存，覆盖 37 个教学阶段快照。
- `LayoutIssueDetector`：复用冻结的 quality_repair checker。
- `compact_layout_report`：只返回最多 20 个 issue，不返回帧数组、点集、日志或视频。

组件 smoke 已对 Agent 产生的真实 R1 完成 68.288 秒视频渲染，BBox 探针导出
37 个快照、2 个原始风险；既有 detector 将两项判定为非阻塞，因此 Agent 收到
`blocking_count=0`。完整原始 BBox 和 detector 结果仍保存在审计目录。

下一阶段是用真实 API 完整跑一次父 Agent闭环，再批量跑留出集。任何调优都不得
按样本 ID、题目文本或对象名增加分支。
