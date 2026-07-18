# Quality Repair 探索式 Agent 方案交叉 Review

日期：2026-07-08

审查对象：

- `2026-07-08-quality-repair探索式AgentDiagnosticLoop执行方案.md`
- `2026-07-08-quality-repair探索式Agent方案-v2.md`

## 1. 总结论

建议以 `探索式Agent方案-v2` 作为主方案，以 `AgentDiagnosticLoop执行方案` 作为实施拆解和任务清单来源。

原因：

- v2 对“规则退到边界层、智能前移到诊断层、工具支撑探索、checker 负责裁判”的架构边界表达更准确。
- DiagnosticLoop 的数据协议、文件规划、任务拆分和并行 agent 分工更可执行。
- 两份文档目标一致，但各自不完整：v2 缺工程落地粒度，DiagnosticLoop 有几处实施动作过激，容易一次性改动过大。

最终应该合并成一份主线文档：

```text
v2 的架构判断
  + DiagnosticLoop 的文件/任务拆分
  + 更稳的阶段性开关和 shadow replay 验收
```

## 2. Findings

### F1. 主方案应采用 v2 的职责边界

v2 明确把程序和 Agent 分成事实层、工具层、诊断层、编辑层、checker 层、evidence 层。这比 DiagnosticLoop 更准确，因为它直接回答了“哪些规则该删，哪些规则不能删”。

推荐保留 v2 的表述：

```text
程序负责事实、工具、安全边界和验收；
Agent 负责判断问题真假、是否值得修、是否需要局部取证、如何定位源码并做局部 Edit。
```

DiagnosticLoop 也有同样方向，但更像实施计划，不适合作为第一性原则文档。

### F2. DiagnosticLoop 缺少独立 `agent_safety_contract.json`

DiagnosticLoop 把 `protected_boundaries` 放进 `layout_issue_digest.json`。这会让“事实输入”和“安全边界”混在一起。

v2 单独提出 `agent_safety_contract.json` 更好：

```text
layout_issue_digest.json      # 事实和索引
agent_safety_contract.json    # 安全边界和验收协议
```

建议合并时采用 v2 的文件拆分。digest 只表达 facts/signals/query index，不表达 forbidden/acceptance。

### F3. DiagnosticLoop 的 deterministic prepatch 降级动作过急

DiagnosticLoop Task 7 写了：

```text
不再在 Agent triage 前无条件执行 _try_deterministic_layout_prepatch()
```

这个方向最终可能是对的，但不应该第一轮就做。当前代码里 deterministic prepatch 已经是现有修复效果的一部分，直接下线会让 replay 指标波动，无法判断新 Agent loop 是变好还是变差。

更稳的顺序：

```text
Phase A: 保留当前 deterministic prepatch，新增 Agent decision 只做 shadow 记录
Phase B: Agent decision 可选择 deterministic candidate，但旧 prepatch 仍可用
Phase C: 真实样本证明 Agent triage 稳定后，再取消默认抢先修
```

也就是说，deterministic repair 要降级，但要通过 shadow replay 验收后再切换。

### F4. v2 缺少足够细的实施任务

v2 架构比 DiagnosticLoop 好，但执行层还不够细。比如它说新增 diagnostic JSON 解析器、evidence query materializer，但没有像 DiagnosticLoop 一样拆到测试文件和最小验证命令。

建议直接吸收 DiagnosticLoop 的 Task 1-6、Task 8-9：

- 捕获 `AgentRunReport.final_text`
- 新增 `diagnostic_protocol.py`
- 生成 `layout_issue_digest.json`
- 新增 `evidence_query.py`
- 改造 layout prompt
- controller 支持 `no_fix / need_more_evidence / fix`
- evidence 输出升级
- replay 报表升级

Task 7 需要按 F3 改为阶段性切换。

### F5. 两份文档都需要补“证据查询预算”

两份文档都说 Agent 可以请求局部 full bbox / lifecycle / source anchor，但还缺硬预算。

建议明确：

```text
每轮最多 3 个 evidence requests
每个 request 输出文件 <= 12KB
同一 issue_id/object_id/helper 一轮内只能请求一次
连续 2 轮 need_more_evidence 且无 Edit，则 stop_reason=agent_evidence_loop
默认不允许读 facts/layout_context.full.json
```

这个预算不是修复规则，而是工具协议，应该保留。

### F6. 两份文档都需要补“未知决策”的处理细节

v2 写了 invalid decision，但还不够工程化。需要明确。原建议里“JSON 解析失败不采纳 Edit”过严，容易丢掉真实有效 patch；更稳的口径是：先区分有没有实际 Edit，再决定重试或验收。

```text
JSON 解析失败且无 Edit：记录 agent_decision_parse_error，允许下一轮重试一次结构化输出
JSON 解析失败但已有 Edit：仍跑 checker + safety gates；若改善且安全通过，可采纳，但标记 accepted_unstructured_decision
action 缺失：视为 unknown
action=fix 但无 Edit：runner_error_fix_without_edit
action=no_fix 但已 Edit：忽略 no_fix，进入 checker 验收
action=need_more_evidence 但无合法 request：agent_invalid_evidence_request
```

这类不是修复配方，而是 controller 协议，必须写死。原则是：不要因为格式错误丢掉一个真实有效 patch，也不要因为 Agent 自述成功绕过 checker。

### F7. 两份文档都应强调“移除早退，不等于无条件进 SDK 消耗”

DiagnosticLoop 明确要移除 `sdk_actionable_blocking_count == 0` 早退，这是对的。但合并文档要补一句：

```text
旧 actionability 不再作为 gate，但可作为 digest 的 risk_hints / possible_signals 输入给 Agent。
```

否则会误解成旧规则全部删除。正确做法是：

- 不让程序替 Agent 做最终判断；
- 但保留已有统计特征作为 evidence hint；
- 由 Agent 输出 `no_fix` 或 `fix`。

### F8. v2 的 replay 验收指标比 DiagnosticLoop 更合理

DiagnosticLoop 写了部分硬指标，例如 risk-only edit 率、P0/P1 真问题进入 edit 比例。v2 更强调和当前版本比较：

```text
clean/improved 不低于当前版本
risk-only 样本 Edit 率下降
output_identical_to_input 可解释
token 不因 full context read 失控
```

推荐合并：

| 指标 | 来源 | 合并后口径 |
|---|---|---|
| `REPAIR_WORSE` 对外暴露 | 两份都有 | 必须 = 0 |
| clean/improved | v2 | 不低于当前版本 |
| risk-only edit 率 | 两份都有 | 下降，且人工样本校验 |
| output_identical_to_input | v2 | 必须能分解为 no_fix / evidence_loop / edit_rejected / checker_error |
| token | v2 | 平均不高于当前版本，full context read 事件单独计数 |
| false_no_fix | v2 风险表 | 人工标注样本估算 |

## 3. 推荐合并结构

建议最终保留一份主文档，结构如下：

```text
1. 核心判断                         # 采用 v2
2. 不变底线                         # 采用 v2
3. 程序和 Agent 职责边界             # 采用 v2
4. 新数据文件                       # v2 + DiagnosticLoop 细节
   4.1 layout_issue_digest.json
   4.2 agent_safety_contract.json
   4.3 evidence query files
5. Agent 决策协议                   # 两份合并
6. Controller 执行流                 # v2 + DiagnosticLoop Task 6
7. Evidence 升级                    # 两份合并
8. 分阶段实施                       # v2 phases + DiagnosticLoop tasks
9. 并行开发分工                     # DiagnosticLoop
10. Replay 验收指标                 # v2 为主
11. 风险和对策                      # v2 为主
12. 不做范围                        # DiagnosticLoop
```

## 4. 推荐实施顺序

### Phase 0: 基线冻结

- 跑当前 `libs/quality_repair/tests`。
- 选定当前 replay 样本池，记录当前 clean/improved/no_edit/token。
- 不改行为，只确定比较基准。

### Phase 1: 协议底座，不改修复行为

- 增加 `AgentRunReport.final_text`。
- 增加 `diagnostic_protocol.py`。
- 增加 `agent_decision.json` evidence。
- 旧 prompt 和旧 prepatch 暂时不动。

### Phase 2: digest / safety contract shadow

- 生成 `layout_issue_digest.json`。
- 生成 `agent_safety_contract.json`。
- prompt 仍可读旧 brief，但 evidence 同时保存 digest。
- 用 replay 检查 digest 是否足够表达真实问题。

### Phase 3: Agent Diagnostic Loop

- 新 prompt 读 digest + safety contract。
- 支持 `no_fix / need_more_evidence / fix`。
- 支持 evidence query materializer。
- 移除 `sdk_actionable_blocking_count == 0` 早退，但保留为 digest hint。

### Phase 4: deterministic prepatch 降级

- 先 shadow：记录 Agent 是否选择 deterministic candidate。
- 再灰度：部分样本由 Agent 决定是否执行 prepatch。
- 最后：如果 replay 指标稳定，再取消默认抢先修。

### Phase 5: 真实样本验收

- 对历史 25 个失败/部分修复样本跑对比。
- 对 top50/top100 高危样本跑对比。
- 人工标注 risk-only / must-fix 子集。
- 生成 HTML 报表。

## 5. 最终建议

采用 v2 作为主方案。

DiagnosticLoop 不废弃，作为执行附录迁入 v2，尤其保留：

- 文件改造清单；
- Task 1-6、Task 8-9；
- 并行 agent 分工；
- 验证命令；
- 不做范围。

必须修改 DiagnosticLoop 中最激进的一点：

```text
不要第一阶段就关闭 deterministic prepatch。
```

还必须修改 F6 的过严口径：

```text
JSON 解析失败但已有 Edit 时，不要直接丢弃；必须走 checker + safety gates。
改善且安全通过时可采纳，并记录 accepted_unstructured_decision。
```

最终合并后的方案应该满足：

```text
规则不再写修法；
规则保留安全边界；
Agent 判断 fix/no_fix/need_more_evidence；
工具提供局部证据；
checker 做唯一采纳裁判；
deterministic repair 从默认抢先修，逐步过渡为 Agent 可选候选。
```
