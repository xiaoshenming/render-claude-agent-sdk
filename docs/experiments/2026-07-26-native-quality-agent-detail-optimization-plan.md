# 原生统一 Quality Agent 细节优化方案

日期：2026-07-26

基线：`34e4e3c`

前置架构归档：
`docs/experiments/2026-07-26-native-quality-agent-correct-route-and-evidence.md`

## 1. 优化原则

当前主线架构已经成立，不更换为 no-tools、普通 LLM 编排器或辅助 Read/Edit 脚本。
优化目标是保留原生父 Agent 的自主修复闭环，只处理环境、日志、预算匹配、BBox
反馈、失败恢复和最终输出稳定性。

必须保留：

```text
一个持续的父 Quality Agent 会话
→ 两个原生前台 Reviewer
→ ToolResult 自动返回父上下文
→ 父 Agent 自己核对完整 Solution
→ findings 先冻结
→ 精确 patch 创建 revision
→ 真实渲染与 BBox 反馈
→ 父 Agent 自主决定继续修复或提交
→ 外层独立重渲染与复检
```

本方案不新增质量拦截。检查器用于采证、修复反馈和回归，不能代替修复能力。

## 2. 建议目标流程

```text
输入 candidate.py
        ↓
环境与输入预检
        ↓
宿主抽取 Solution，保存 R0
        ↓
宿主采集 R0 render/ffprobe/BBox 基线
        ↓
启动一次父 Quality Agent 会话
        ↓
两个 Reviewer 各完整读取一次 Solution
        ↓
ToolResult 自动进入父上下文
        ↓
父 Agent 完整读取一次 Solution
        ↓
按共同根因冻结 findings
        ↓
apply_patch 创建 revision
        ↓
真实 render + ffprobe
        ↓
BBox 返回 before/after/resolved/introduced/共享问题簇
        ↓
父 Agent 根据事实继续修复
        ↓
预算按 R0 难度动态匹配
        ↓
submit_revision
        ↓
StructuredOutput
        ↓
外层独立重渲染、ffprobe、BBox
        ↓
影子 Final Logic Verifier
        ↓
PROPOSED / HOLD / FAILED
        ↓
完整调用、Token、revision 和失败分类归档
```

## 3. P0：环境与运行稳定性

### 3.1 批前统一预检

每批开始前一次性检查：

- Anthropic 兼容网关可达；
- Key 已注入子进程；
- 指定模型能完成最小工具调用；
- Docker 镜像存在；
- Manim、FFmpeg、ffprobe、LaTeX 和字体可用；
- `BaseConfigScene` 与 runtime stubs 可导入；
- 输入目录可挂载；
- 输出目录和媒体目录可写；
- candidate 能 AST 解析和编译。

预检失败时不启动模型调用，避免环境缺口浪费 Token。该检查只判断链路是否可执行，
不根据视频质量拒绝渲染。

### 3.2 固化 runtime manifest

每批保存：

```json
{
  "agent_commit": "...",
  "model": "...",
  "effort": "...",
  "sdk_version": "...",
  "docker_image_id": "...",
  "python_version": "...",
  "manim_version": "...",
  "ffmpeg_version": "...",
  "detector_version": "...",
  "render_quality": "...",
  "fps": 15,
  "tts_mode": "silent",
  "runtime_python_path": "..."
}
```

后续只有 manifest 可比，才能宣称两批环境相同。

### 3.3 分离 Agent 与渲染并发

不要用一个 `concurrency` 同时控制 LLM 和 Docker。建议独立配置：

```text
agent_concurrency
render_concurrency
```

具体并发值由机器 CPU、内存和 Docker 实测决定，不在提示词中暴露。

## 4. P0：失败也必须完整落日志

无论成功、异常、ToolDenied、Token 超限还是 StructuredOutput 失败，都在 `finally`
落盘：

```text
logs/agent_call.partial.json
logs/parent-sdk-messages.jsonl
logs/subagent-results.json
logs/tool_calls.jsonl
logs/failure.json
```

最低记录：

- input/output/cache read/cache write Token；
- 父 Agent轮次；
- Reviewer 各自 Token、耗时和工具数；
- 每个工具的 caller、agent_id、agent_type、parent_tool_use_id；
- revision、代码 Hash、finding IDs；
- 每次 render/inspect 的耗时；
- 精确终止原因。

失败状态内部至少细分：

```text
FAILED_REVIEWER_SCHEMA
FAILED_NO_PATCH
FAILED_RENDER
FAILED_PATCH_BUDGET
FAILED_LAYOUT_INSPECT_BUDGET
FAILED_TOKEN_BUDGET
FAILED_STRUCTURED_OUTPUT
FAILED_EXTERNAL_ACCEPTANCE
```

## 5. P0：工具预算必须成套匹配

现有实测出现了允许创建 R5、却不允许检查 R5 的不一致。原则应为：

```text
每个允许创建的 revision
→ 必须有对应的 validate 机会
→ 必须有对应的 inspect 机会
```

第一版可对齐为：

```text
R0基线 inspect：宿主执行，不占 Agent 工具次数
apply_patch：5
validate_revision：5
inspect_layout：5
record_findings：4批
submit_revision：1
```

数字不是最终结论，后续必须通过统一 A/B 调整。重点是预算之间不能互相矛盾。

可进一步根据 R0 复杂度动态分档：

| 难度 | R0 blocking 示例 | patch/validate/inspect 初始预算 |
|---|---:|---:|
| 简单 | 0～2 | 2 |
| 中等 | 3～10 | 5 |
| 复杂 | 11～20 | 7 |
| 极端 | 超过20或报告截断 | 8，并启用问题聚类 |

预算耗尽不能删除已生成证据；必须保留最后一个已验证 revision，并说明是未完成候选，
不能伪装成 PROPOSED。

## 6. P1：建立可比较的 R0 基线

目前部分逻辑题只有最终 revision 的 BBox，没有 R0 BBox，无法回答：

- 原来有多少重叠；
- 逻辑修复顺带解决多少重叠；
- 是否引入新问题；
- 两批 detector 是否可比。

宿主应在启动父 Agent 前采集：

```text
R0 compile
R0 render
R0 ffprobe
R0 BBox
```

R0 证据完整保存；给模型的返回仍保持紧凑。

## 7. P1：BBox 返回差异与共同根因

`inspect_layout` 不应只返回当前 `blocking_count` 和平铺问题列表，还应返回：

```json
{
  "before": 36,
  "after": 19,
  "resolved_count": 17,
  "persistent_count": 19,
  "introduced_count": 0,
  "shared_roots": [
    {
      "object": "summary_panel",
      "affected_issue_count": 12,
      "representative_issues": []
    }
  ]
}
```

按以下维度聚类：

- 共享 Mobject；
- 同一 owner VGroup；
- 同一动画 phase；
- 同一场景切换；
- 同一 frame overflow 根因。

返回最多若干问题簇，而不是截取前 20 条原始碰撞。这样既降低 Token，又帮助父 Agent
一次修复共同根因。

## 8. P1：StructuredOutput 不应抹掉已提交候选

权威边界应为：

```text
submit_revision 的 session 事实
= revision_id、code_hash、problem_hash 的权威来源

StructuredOutput
= SDK 最终结构化摘要
```

保留 StructuredOutput 和一次小型纠正。如果 submit 已成功但最终 JSON 仍有格式问题，
宿主可从 session 补齐三个权威 Hash/ID，模型只负责 summary。候选仍必须通过外层独立
验收，不能因为补齐 JSON 而跳过任何质量检查。

## 9. P1：Reviewer schema 自纠

Reviewer ToolResult 先做 schema 检查。若只是字段命名、枚举或缺少必填字段，在同一
Reviewer 会话内纠正一次；仍失败才记录 `FAILED_REVIEWER_SCHEMA`。

宿主只能规范字段，不能凭空增加问题或改变 Reviewer 的判断语义。

## 10. P2：渲染成本控制

保留每个 revision 的真实渲染，但可采用：

1. 内部反馈使用固定低成本、静音、15fps 配置；
2. 同一 code hash + runtime manifest 的内部证据可复用；
3. 最终外层验收必须在独立干净目录重新渲染，不能复用内部结果。

这样不牺牲最终真实性，同时减少重复内部工作。

## 11. P2：影子 Final Logic Verifier

当前外层独立证明渲染、视频流、Hash 和 BBox，但不能独立证明修复后的数学逻辑。
可增加只读影子 Verifier：

```text
原题
+ 最终 Solution
+ 初始 Reviewer findings
+ revision 修改摘要
        ↓
resolved / still_present / regression / uncertain
```

第一阶段只采证、不阻断、不拒绝；稳定后再评估是否进入正式质量决策。

## 12. 为什么 047 先修 logic-1，再修 logic-2..5

真实调用为：

```text
record_findings：一次记录5个问题
→ apply_patch #1：logic-1
→ R1
→ validate R1
→ apply_patch #2：logic-2、3、4、5
→ R2
→ validate R2
→ inspect R2
```

这不是提示词要求“必须先修一个”，也不是宿主把第一个 finding 单独派发。

主要原因是当前 `apply_patch` 的工具合同一次只能提交：

```json
{
  "old_text": "一个连续旧代码块",
  "new_text": "一个连续新代码块",
  "finding_ids": []
}
```

也就是一次 patch 只能替换一个连续区域。047 中：

- `logic-1` 位于第一幅图的基础坐标定义；
- `logic-2..5` 涉及第二幅图坐标、fit 后端点重绑、等长标记和讲解数值；
- 两组修改不在同一个紧邻代码块；
- 强行合并需要把中间大段无关代码一起放进 `old_text/new_text`，参数更大、匹配更
  脆弱，也更容易误改。

因此父 Agent选择：

```text
先修改独立、连续的第一幅图坐标块
→ 验证R1仍可渲染
→ 再修改后面能够共同覆盖4个finding的连续大块
```

这是模型基于代码位置、依赖关系和工具能力做出的合理原子化规划。

提示词本身已经要求：

```text
Prefer a coordinated root-cause repair over scattered shifts.
```

即优先共同根因修复；没有要求第一个 finding 必须单独修。

### 12.1 为什么每次 patch 中间都出现一次渲染

提示词和状态机明确要求：

```text
After every patch call validate_revision.
```

因此：

```text
patch #1 → R1 → validate R1
patch #2 → R2 → validate R2
```

这是有意的安全反馈环，不是模型忘记一次修完。

### 12.2 什么时候这种拆分是合理的

- 两组修改位于不同代码区域；
- 后一组依赖前一组建立的新坐标或对象；
- 每个补丁都覆盖一个完整共同根因；
- 中间验证能尽早发现编译或渲染回归。

### 12.3 什么时候说明父 Agent 拆得太碎

- 多个 finding 位于同一连续代码块；
- 多次 patch 只做相邻的微小位移；
- 每个 patch 只解决一个碰撞，却存在明显共享对象根因；
- 上一轮 BBox 已说明一个 owner/VGroup 影响多个问题，父 Agent仍逐条移动对象。

这时应依靠 BBox 共同根因聚类和日志指标判断，而不是看到“先修一个”就修改提示词。

### 12.4 当前是否需要修改提示词

暂时不需要。

047 的两次 patch 都有清晰的连续代码边界，R2 一次覆盖 4 个 finding，最终 BBox
为 0，属于合理分组。先完成日志归属、R0 基线和每个 revision 的
`finding_ids/resolved/introduced` 统计，再用至少 17+20 的统一数据判断是否普遍存在
过度拆分。

如果后续证据确认普遍过碎，最小提示词调整应只是增加一句：

```text
Before the first patch, group supported findings by contiguous source region
and shared root cause. Cover all findings in that region with one coherent
patch when safe.
```

不能因此取消父 Agent自主规划，也不能强制一次大 patch。

## 13. 推荐实施顺序

### 第一批：只补稳定性，不改变 Agent策略

1. runtime preflight 与 manifest；
2. 失败调用完整 usage/log 落盘；
3. 工具调用标注父子 Agent 归属；
4. patch/validate/inspect 预算成套对齐；
5. StructuredOutput 异常不抹掉已提交 revision；
6. 精确失败分类；
7. 始终保留最后一个已验证 revision。

### 第二批：提高 BBox 收敛

1. R0 基线 render/BBox；
2. before/after/resolved/introduced；
3. 共享对象和 phase 聚类；
4. 动态复杂度预算；
5. 统一单轮 A/B。

### 第三批：补最终逻辑证据

1. 影子 Final Logic Verifier；
2. 人工抽查视频和 diff；
3. 分析误报、漏报和修复回归；
4. 再决定是否微调父 Agent提示词。

## 14. 第一版最小实施清单

```text
1. 批前 preflight 和 runtime manifest
2. 宿主采集 R0 BBox 基线
3. patch=5、validate=5、inspect=5 成套对齐
4. BBox 返回 before/after 与共享问题簇
5. 失败时保存 partial AgentCallRecord
6. 日志标注 parent/reviewer 调用归属
7. submit 成功后 StructuredOutput 异常不丢候选
8. 保留最后一个已验证 revision
```

这些改动不改变正确主线，也不预设模型该怎样修代码。
