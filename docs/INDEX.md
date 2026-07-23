# Claude Agent SDK V3 维护索引

这是独立仓库的持续维护入口。每次同步 V3 核心、MathPi 适配、运行合同或评估结论时，必须同时检查并更新本文、根 `README.md` 和 `SOURCE_SNAPSHOT.md`。

## 推荐阅读顺序

1. [`README.md`](../README.md)：系统用途、完整流程、角色边界和运行方法。
2. 本文：定位当前代码入口、Harness、验证和技术报告。
3. [`SOURCE_SNAPSHOT.md`](../SOURCE_SNAPSHOT.md)：当前快照来源、上游提交和完整性说明。
4. [`INTEGRATION_PATCHES.md`](../INTEGRATION_PATCHES.md)：独立仓库相对原始 V3 交接包的接入修正。
5. [`docs/engineering/HARNESS.md`](engineering/HARNESS.md)：Agent 权限、预算、工具与证据合同。
6. [`docs/architecture/QUALITY_PLATFORM.md`](architecture/QUALITY_PLATFORM.md)：质量平台总体架构与状态机。

## 当前核心代码地图

| 主题 | 入口 | 作用 |
|---|---|---|
| 总编排 | `src/manim_quality/orchestrator/` | 串联逻辑、布局、候选版本和交付证据 |
| Claude SDK 适配 | `src/manim_quality/agents/` | 角色权限、SDK 调用、工具控制、Token 和消息证据 |
| 逻辑审查与修复 | `src/manim_quality/logic/` | Reviewer、Coder、Verifier、确定性验证器和报告 |
| 逻辑历史最佳候选 | `src/manim_quality/logic/candidate_history.py` | 跨修复轮保存最佳候选，后续异常不再清空已有改善 |
| 聚焦 Reviewer 输入 | `src/manim_quality/logic/focused_review_input.py` | 将完整源码审查输入收敛为可读、可版本化合同 |
| 重叠检测与修复 | `src/manim_quality/layout/` | 问题分类、五轮策略、最佳候选、复检与耗时 |
| 几何事实 | `src/manim_quality/geometry/` | 静态索引、关系事实和几何证据 |
| 渲染与切片 | `src/manim_quality/rendering/` | 候选渲染、时间切片和产物绑定 |
| 版本与存储 | `src/manim_quality/revisions/`、`src/manim_quality/storage/` | checkpoint、候选版本、队列和数据库适配 |
| 外部布局探针 | `external/layout_probe/` | Agent 会话之外的 BBox/越界/重叠复检 |
| MathPi 接入快照 | `integrations/mathpi/` | fail-open 宿主桥接、归档前调用和三态证据 |
| 评估与重放 | `evals/`、`scripts/run_existing_code_e2e.py` | 已有源码重放、专项评估和结果汇总 |
| 测试 | `tests/` | 单元、集成、端到端、工程规范和故障注入 |

## 当前关键运行合同

- 逻辑顺序：Reviewer 发现可证问题，Coder 生成候选，Verifier 对冻结 Issue 逐项输出 `resolved / unresolved / unknown`。
- 逻辑修复始终保存历史最佳候选；后续 SDK、turn、Read、引用或结构化说明异常只增加风险，不得机械恢复原始错误源码。
- Coder/Verifier 的 turn 和工具调用是有界软预算；候选是否保留以实际 Edit、编译和逐项证据为准，不由最终 JSON 或行号格式单独决定。
- 布局顺序：外部探针采证，Overlap Coder 局部修复，最多 5 轮并始终保留历史最佳候选。
- `must_repair` 才推动下一轮；`conditional_repair` 和 `record_only` 只保留证据。
- Token 预算只观测，不得因平台与供应商统计口径不同而丢弃已验证候选。
- MathPi 宿主质量链路默认 fail-open：异常留证，不新增视频交付硬拦截。
- 三态证据为 A 原始态、B 逻辑态、C 布局态；每态保存代码、视频和 diff。
- 重叠轮数唯一事实源：`src/manim_quality/layout/runtime_policy.py`。

## 工程规范与验证

- 单个源代码文件建议不超过 300 行；超过 200 行后增加功能前必须评估拆分。
- 预计修改后超过 300 行时必须先拆分，不得继续堆叠。
- 工程检查：`.venv/bin/python scripts/check_engineering_standards.py`。
- 核心回归入口见根 `README.md` 的“运行测试与工程检查”。
- 当前文件 Hash 清单：[`CURRENT_SNAPSHOT_SHA256.txt`](../CURRENT_SNAPSHOT_SHA256.txt)。
- 不能用测试替身或旧报告冒充 server3 真实 SDK 运行证据。

## 当前技术报告

- [`2026-07-23 逻辑 Agent 软合同与错误样本重放报告`](reports/2026-07-23-逻辑Agent软合同与错误样本重放报告.md)
- [`2026-07-22 Agent 技术改造点对点功能审计`](reports/2026-07-22-Agent技术改造点对点功能审计.md)
- [`2026-07-22 server3 Agent 全量日志审计及优化建议`](reports/2026-07-22-server3-Agent全量日志审计及优化建议.md)
- [`独立仓库验证记录`](reports/2026-07-18-independent-repo-verification.md)

## 维护规则

发生以下任一变化时必须更新本文：

- 新增、删除或移动核心入口；
- Logic、Layout 或 Orchestrator 的执行顺序变化；
- 轮数、停止条件、候选采用或 fail-open 合同变化；
- MathPi 集成路径、三态证据或外部探针变化；
- 新增权威报告，或旧报告不再代表当前状态；
- 上游 MathPi 快照或独立仓库发布版本变化。

历史规划和历史报告可以保留，但当前事实以代码、测试、`SOURCE_SNAPSHOT.md` 和真实运行证据为准。
