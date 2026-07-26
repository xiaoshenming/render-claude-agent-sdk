# 原生 Quality Agent 细节优化与 37 题实测

日期：2026-07-26

分支：`codex/manim-quality-agent-native-optimization-20260726`

最终实测提交：`41621b5`（Reviewer 宽容规范提交为 `be98fcb`）

## 1. 结论

本轮完整实现并验证了优化方案中的第一版最小清单，但不能把结果描述成“37 题全部
修好”：

| 批次 | 样本 | PROPOSED | FAILED | Token | 墙钟时间 |
|---|---:|---:|---:|---:|---:|
| 逻辑 17 题 | 17 | 12 | 5 | 1,037,598 | 2,547 秒 |
| BBox Top20 | 20 | 0 | 20 | 648,220 | 2,692 秒 |
| 合计 | 37 | 12 | 25 | 1,685,818 | 两批并发 |

逻辑题完整协议成功率为 70.6%。BBox Top20 虽然没有题目达到“零阻断并成功提交”，
但 18/20 进入修改，12/20 的最后一次可读 BBox 比 R0 更少。这说明 Agent 有实际修复
能力，主要问题已经从“不能跑”转为“复杂布局在预算内不能完全收敛”。

## 2. 最终流程

```text
批前 preflight
├── Provider 最小 tool_use
├── Python/SDK/commit/image/runtime manifest
├── Docker/Manim/FFmpeg/ffprobe
├── runtime stubs import
└── 37 份源码 AST/compile
        ↓
宿主 R0 真实 render + ffprobe + BBox
        ↓
一个父 Quality Agent 会话
        ↓
两个原生前台 Reviewer
├── math_geometry_reviewer
└── animation_lifecycle_reviewer
        ↓
ToolResult 自动回父上下文
        ↓
父 Agent read_solution → record_findings
        ↓
R1...R5 精确 patch
        ↓
每个 revision 真实 validate + inspect
        ↓
submit_revision + StructuredOutput
        ↓
独立 acceptance runtime 重渲染、ffprobe、BBox
```

## 3. 已实现内容

### 3.1 稳定性与环境

- 固化 `runtime_manifest.json`；
- 批前验证 Provider 工具调用，不只检查 Key 是否存在；
- 使用项目锁定的 Python 3.11、Claude Agent SDK 0.2.128；
- 固化静音 runtime stubs；
- Agent 并发与 Docker 并发分离；
- 37 路 Agent、10 个全局渲染槽；
- 修复子进程缺少仓库 `src` 的 `PYTHONPATH`；
- API Key 存在时显式清空继承的旧 `ANTHROPIC_AUTH_TOKEN`，避免凭证污染；
- 清理 SDK 已不认识的 `LS` deny rule；
- 渲染、BBox、Agent、单题外层超时成套对齐。

### 3.2 证据与失败恢复

- R0 在模型启动前真实渲染、ffprobe、BBox；
- 失败时保存 `agent_call.partial.json`、工具记录、失败分类和最后 revision；
- 工具记录增加 `caller`、`agent_id`、`agent_type`；
- submit 已成功但终态摘要格式失败时，可从 session 权威状态恢复候选；
- Reviewer 多出的元数据由宿主规范化，不再因 `severity/notes` 等附加字段中断；
- BBox 返回相对 R0 的 before/after/resolved/persistent/introduced；
- BBox 问题按共享对象和 phase 聚类。

### 3.3 成套预算

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
```

## 4. 调用统计

### 4.1 逻辑 17 题

- 成功 12 题平均 86,467 Token，平均 12.4 轮；
- 失败 5 题均走到 R3～R5，最终原因均为会话 `TimeoutError`；
- 工具尝试总数：
  - Reviewer Agent 34；
  - Reviewer/父 `read_solution` 51；
  - `check_relation` 40；
  - `record_findings` 20；
  - `apply_patch` 46；
  - `validate_revision` 45；
  - `inspect_layout` 15；
  - `submit_revision` 13；
  - `StructuredOutput` 12。

失败题：

| 样本 | 最后 revision | 原因 |
|---|---:|---|
| 017 等边三角形 | R5 | 会话超时 |
| 035 腰上的高求底角 | R5 | 会话超时 |
| 042 线段和差证明 | R3 | 会话超时 |
| 047 全等练习2 | R4 | 会话超时 |
| 080 倍长中线 | R4 | 会话超时 |

这 5 题不是“Reviewer 没运行”或“没有修改”，而是多轮真实渲染占用了 1800 秒 Agent
时限。最后 revision 已留存，适合从最后已验证候选继续，而不是从 R0 重跑。

### 4.2 BBox Top20

- 18/20 进入修改；
- 12/20 最后 BBox 低于 R0；
- 0/20 在本轮内降到零并完成提交；
- 平均 21.3 轮，说明 24 轮上限对复杂 BBox 已非常接近；
- 主要失败：
  - turn/StructuredOutput/SDK 终态：多数；
  - patch 预算耗尽：2；
  - cache-read Token 预算：1；
  - R0 未进入 patch：1。

典型改善：

| 样本 | R0 | 最后可读 BBox |
|---|---:|---:|
| `01KXZSEEV6ETVRDTS3PS21Y4P3` | 23 | 15 |
| `01KY0ETPX47JRMPSTCYWQ2NT1P` | 14 | 7 |
| `01KY0F38C8DJZ70A4KSBJTH4G4` | 5 | 5（中途到 1 后回归） |
| `01KY32Q47APQHC0XVMGZGYWZAC` | 9 | 3 |
| `01KXZSE3J65B70FSW0RB6617YN` | 36 | 23 |

## 5. 本轮发现并修复的环境问题

1. 新 worktree 缺 `.vendor/quality_repair`：从冻结归档物化。
2. 批量子进程不能 import `manim_quality`：为子进程注入仓库 `src`。
3. 生产 runtime 会加载真实 TTS 依赖：改用可导入的静音 runtime stubs。
4. 旧 `ANTHROPIC_AUTH_TOKEN` 污染新 API Key：SDK 环境强制单一凭证。
5. 只检查 Key 存在无法发现认证问题：增加真实最小 tool_use。
6. Reviewer 附加字段触发 schema 中断：改为只取 canonical 字段。
7. Docker 排队时间被算入 300 秒 render timeout：统一放宽并修正队列适配。
8. `TimeoutExpired.stdout/stderr` 可能为 bytes：落盘前安全解码。

## 6. 下一步

下一轮不应再次扩大通用限制后从 R0 重跑全部 37 题。建议：

1. 逻辑 5 个超时题从最后已验证 revision 继续；
2. BBox 按 R0 blocking 动态预算，而不是全部固定 5 个 patch；
3. 把“布局仍未归零”与“终态 JSON/turn 超限”分开重试；
4. 对 BBox 使用共享 root cluster 生成一个协调 patch，减少逐碰撞修改；
5. Token/usage 必须在 SDK 异常前持续增量落盘，当前部分失败记录仍显示 0；
6. 影子 Final Logic Verifier 仍应保持 evidence-only，不能成为新拦截。

## 7. 产物

- 正式结果：
  `/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726`
- 逻辑汇总：
  `/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726/logic17/batch_summary.json`
- BBox 汇总：
  `/home/ming/下载/ManimQualityAgent-native-optimized-37-final3-20260726/bbox20/batch_summary.json`
- 每题均包含 R0、revision、真实渲染/BBox、工具调用和 decision；失败题包含
  `failure.json` 与最后候选。

## 8. 收尾验证

- 本轮核心模块定向回归：`183 passed`；
- `git diff --check`：通过；
- 全量回归：`1462 passed, 7 failed`，因此本分支不能标记为全量测试全绿。

全量失败包括冻结 holdout/vendor 哈希、Artifact URI、旧 SDK 集成用例，以及
`scripts/batch_runtime.py` 的工程行数约束。它们不改变已落盘的 37 题真实执行结果，
但合并主分支前仍应单独处理，尤其是工程行数约束和旧工具名集成用例。
