# 原生 Quality Agent 收敛率修复批次

日期：2026-07-26

分支：`claude/native-agent-convergence-fixes-20260726`（基于 `e453c35`，
原 `codex/manim-quality-agent-native-optimization-20260726` 分支未动，可整体回滚）

## 1. 本轮目标

针对 37 题实测暴露的六个卡点做架构级修复，不改变
「双 Reviewer + 真实渲染 + BBox 反馈 + revision + 外层独立验收」闭环，
不放宽任何验收红线。

## 2. 修复清单与提交

| 提交 | 卡点 | 内容 |
|---|---|---|
| `6e99096` | 卡点一 | 渲染墙钟拆出 1800 秒推理预算：`BudgetTracker.external_call()` 剔除受控工具执行时间；SDK 会话改用可延展 deadline 的 `CancelScope`；同步渲染移入 worker 线程使取消点可达；验证工具 timeout 从名义 30 秒对齐到真实渲染+探针链（2700 秒） |
| `b0d75b3` | 卡点四/五 | submit 成功后任何终态失败均从会话权威状态恢复候选（删除错误文本匹配）；失败归档保留 `best_validated.<Rn>.py` 与 `last_candidate.<Rn>.py`；新增 `FAILED_TIMEOUT` 分类 |
| `b9c3339` | — | 工程规范修复（preflight 拆分、_subagent_protocol 回到 300 行内） |
| `c8b6b68` | 并发前提 | 重叠计时改深度计数（并发工具共享墙钟窗口只计一次）；`RuntimeToolchain` 渲染/探针加可重入锁防双渲染；批前 provider smoke 与 SDK 单凭证语义对齐 |
| `4b732fa` | 卡点二/三/六 | 按 R0 blocking 动态 patch 预算（≤2→5、3..8→6、>8→7）；validate/inspect 回执携带 `patches_remaining`；工具配额随预算联动；提示词升级 `quality-operator-v2`：共享根因协调修复、apply_patch 后同轮批量 validate+inspect（省 1 轮/revision）、预算感知及时提交 |

另：`usage_complete` 与 `external_tool_ms` 进入 AgentCallRecord 与
failure.json，失败成本不再伪装为 0。

## 3. 关键设计约束（未突破）

- 「blocking 未清零不能提交」的 session 规则保持不变；改善但未清零的
  候选通过 `best_validated` 归档保留，不进入交付。
- 推理预算剔除渲染时间后，执行链仍全程有界：工具级 timeout（2700 秒）、
  渲染子进程 timeout（1200 秒）、批量层 case timeout 兜底。
- 外层 OuterAcceptanceGate 独立重渲染重复检逻辑未动；恢复出的候选
  仍必须通过独立验收。

## 4. 验证状态

- 全量测试：`1455 passed, 6 failed`；6 个失败均为迁入基线问题
  （storage Artifact `file:///` ×3、frozen holdout hash、vendor hash、
  旧 SDK 集成用例），本轮零新增失败。
- `scripts/check_engineering_standards.py`：PASS。
- 新增针对性单测：预算外部时间剔除、深度计时、deadline 顺延、
  submit 恢复、FAILED_TIMEOUT 分类、best_validated 选取、
  raise_patch_budget 守卫、blocking→预算映射、回执预算信号、
  工具配额联动。

## 5. 对抗性审查与二轮修复

独立审查 Agent 对全部切片做了对抗性审查（含实证探针），确认外层门禁
独立性、恢复路径 fail-closed、深度计时语义正确；同时发现并已修复：

| 级别 | 发现 | 修复 |
|---|---|---|
| P0 | `to_thread.run_sync` 未传 `abandon_on_cancel=True`，工具级 2700 秒超时实际不可触发；`process.py` 只杀直接子进程，docker 孙进程持有管道导致 `communicate()` 可无限挂死 | services 两处补 `abandon_on_cancel=True`；`process.py` 改 `Popen(start_new_session=True)` + 超时 `killpg` 整个进程组 |
| P1 | `_DeadlineExtender` 事后顺延，deadline 仍会在长工具执行中途开火（同轮批量验证放大） | 改为工具执行期间将 deadline 挂起为 `inf`、结束时按共享窗口恢复；单工具仍被自身 timeout 约束，链路有界 |
| P1 | 批量 SIGKILL 丢失全部失败证据；case_timeout 与工具配额不自洽 | 批量层改 SIGTERM + `--case-grace`（默认 120 秒）宽限后再 SIGKILL；CLI 安装 SIGTERM 处理器把终止转为可落盘异常 |
| P2 | `best_validated` 文件名易被误当交付物且缺 blocking 证据 | 改名 `best_render_passed.<Rn>.py`；failure.json 输出 `{revision_id, blocking_count, layout_inspected}` 完整证据 |
| P2 | 恢复路径丢失 SDK 消息轨迹；`FAILED_STRUCTURED_OUTPUT` 死分支 | `AgentRunFailed` 携带 `sdk_messages`/`subagent_results` 并写入失败归档；删除死分支 |

审查同时确认 6 个基线迁入测试失败均不涉及本次改动文件。

## 6. 待真实验证（需要网关凭证与 Docker 渲染环境）

1. 逻辑 5 个超时题（017/035/042/047/080）复跑：预期不再因渲染占用
   推理时限而 TimeoutError。
2. BBox 代表题 3 题：验证共享根因协调 patch 与动态预算下的清零率。
3. 全量 37 题对照批：与 12/17、0/20 基线同口径对比。

预算口径提醒：动态预算下单题最多 7 patch × (渲染+探针)，
批量并发时渲染槽位排队仍计入工具 timeout，`--render-concurrency`
与题量的配比需按 §3 的有界链复核。
