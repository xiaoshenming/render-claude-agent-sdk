# Manim 质量平台交接首页

- 交接日期：2026-07-14
- 平台主工作区：`D:\manim_quality_platform`
- 当前评测工作树：`D:\codex-worktrees\manim_quality_platform\workbench-e2e-45`
- 当前分支：`codex/workbench-e2e-45`
- 当前 HEAD：`18a94aed86047f2069eb1b9d277cbfdf2e1f8980`
- 交接重点：完整质量 Agent 架构、近几日测试证据、未接入的 Expected/Actual Relation 模块

## 1. 先说结论

当前系统已经形成完整的 Manim 代码质量平台，不再是单个 Prompt 或单个
Agent：

- 外部代码生成；
- 基线渲染和有界恢复；
- 强制 Logic Reviewer；
- 条件 Logic Coder；
- 条件 Directed Verifier；
- 强制布局检测；
- 条件重叠修复 Agent；
- 外层重渲染、复检、回滚和最终一致性门禁；
- Revision、证书、Tokens、耗时和日志留存。

当前最重要的真实结论：

1. 逻辑 Agent 路线已经证明可以发现并修复真实错误；
2. 10 条逻辑故障注入最终 10/10 可重渲染，9 条恢复原始正确逻辑，1 条为
   等价正确；
3. 最新 20 条自然生成任务全部可渲染，但严格自动交付只有 11/20；
4. 当前商业化主要瓶颈是布局检测误报、重叠修复采纳门禁和全局布局失败；
5. Expected/Actual Relation 模块已经实现并独立测试，但尚未接入正式 Reviewer
   链路。

## 2. 这份包解决什么问题

交接包用于让接手工程师或另一个 AI 能够：

- 理解整个质量平台，而不是只看到某个 Agent；
- 查看所有生产模块的当前源码快照；
- 查看 Logic Reviewer、Logic Coder、Verifier 和 Overlap Agent 的边界；
- 查看最近几轮端到端测试的机器报告；
- 独立审查 Expected/Actual Relation 模块；
- 按明确方案把该模块接入 Reviewer 证据层；
- 复跑相关单元测试和离线 Probe；
- 识别哪些结论已被证据支持，哪些仍属于待验证方向。

## 3. 这份包不包含什么

为控制体积并避免泄密，交接包不包含：

- API Key、Token、密码或任何 `.env`；
- `.venv`、Node Modules、Python Cache；
- `.tmp` 和临时布局探针副本；
- 完整 Vendor 二进制和可重新物化的冻结包；
- 大量 Manim Partial Movie Files；
- 所有原始视频。

包中保留机器报告、CSV、关键帧和本机证据路径。需要视频时，应从证据索引
中的原始运行目录单独复制。

## 4. 建议阅读顺序

1. `README_FIRST.md`
2. `docs/AGENT_ARCHITECTURE_AND_TEST_REPORT_ZH.md`
3. `docs/EXPECTED_RELATION_MODULE_AND_INTEGRATION_ZH.md`
4. `docs/EXPECTED_ACTUAL_RELATION_PROBE_V1.md`
5. `source/AGENTS.md`
6. `source/src/manim_quality/logic/expectations/`
7. `source/src/manim_quality/logic/evidence.py`
8. `source/src/manim_quality/logic/review_digest.py`
9. `source/evals/workbench_e2e/logic_stage.py`
10. `evidence/` 中的机器报告

## 5. 平台整体结构

```text
外部生成接口
  -> contracts/       提交和版本化输入
  -> orchestrator/    唯一状态和放行权
  -> logic/           Reviewer、Coder、Verifier、Validator
  -> geometry/        几何事实和确定性计算
  -> layout/          重叠检测、修复适配器和采纳策略
  -> rendering/       Manim 渲染和 Scene 影响分析
  -> delivery/        Warning Policy 和最终一致性门禁
  -> revisions/       不可变 Revision 和指纹
  -> storage/         运行记录、队列、Outbox、SQLite/PostgreSQL
  -> observability/   日志、Tokens、指标和告警
```

`evals/` 是评测 Harness，不是生产链路。

## 6. Agent 角色

| 角色 | 是否必经 | 工具 | 输出 |
|---|---|---|---|
| Logic Reviewer | 是 | Read | Pass、Repair、Record Only、Human Review |
| Logic Coder | 仅发现可修逻辑错误 | Read、Edit | Scene 范围内 Patch |
| Directed Verifier | 确定性验证不足时 | Read | 冻结问题是否解决 |
| Overlap Coder | 检测到阻断重叠时 | Read、Edit | 布局 Patch |

Agent 不具备 Bash、Web、任意 Write、发布、上传和自我验收权限。

## 7. 未接入模块是什么

未接入模块位于：

```text
source/src/manim_quality/logic/expectations/
```

核心文件：

- `extractor.py`：从题目、解答和规划提取预期数学关系；
- `symbolic_index.py`：从 `candidate.py` 静态提取点、线、坐标和端点；
- `comparison.py`：比较 Expected 与 Actual；
- `numeric_comparison.py`：执行平行、垂直、中点、共线等数值判断；
- `schemas.py`：严格的关系 Contract 和输出 Schema。

当前正式 Workbench 使用 `DIGEST_V2_1`，并没有把该模块的 Comparison 结果
交给 Reviewer。

## 8. 未接入模块已有数据

题目关系 SDK 提取：

| 指标 | 结果 |
|---|---:|
| 成功提取 | 11/11 |
| 关系数 | 87 |
| 总 Tokens | 108,622 |
| 平均 Tokens | 9,875/题 |
| 平均模型轮数 | 2.0 |
| 平均耗时 | 13.46 秒 |

原始 11 条综合 Probe：

- 目标错误命中 3/11；
- 正确原代码误报 0/11；
- Unknown Claim 60.9%；
- 该 Pack 混有不可渲染变异和不支持的语义类型，不能作为正式 Benchmark。

筛选后的 5 个可渲染支持样本：

- 错误命中 5/5；
- 正确原代码误报 0/5；
- 只有 3 个独立题目，且经过事后筛选。

10 条生产几何错误，使用已有结构化 Contract：

- 10/10 被确定性比较发现；
- 19 条 Contradiction；
- 0 Unknown；
- 该实验没有测试 LLM 题目关系提取。

一个全新题目端到端 Probe：

- 错误代码命中；
- 原代码未误报；
- 原代码 2/2 关系满足；
- 6,565 Tokens；
- 2 个模型轮次；
- 14.42 秒。

## 9. 接入原则

该模块应作为 Reviewer 的前置事实提供器，不能直接成为放行器。

```text
题目/解答/规划
  -> 结构化关系输入优先
  -> 本地规则提取其次
  -> LLM Extractor 兜底

candidate.py
  -> 本地 AST Symbolic Index

Expected + Actual
  -> Python Comparator
  -> Relation Evidence
  -> Logic Reviewer
```

状态解释：

- `contradiction`：向 Reviewer 提供高价值错误证据；
- `satisfied`：只证明已支持的局部关系一致；
- `unknown`：工具无法证明，不能当作错误，也不能当作通过。

## 10. 不应如何接入

禁止以下做法：

- 把数学关系提取逻辑写进 Orchestrator；
- 让 Logic Coder 自己调用关系提取器后自行验收；
- 把 Comparator 的 `satisfied` 当成整题 PASS；
- 把 `unknown` 当成低风险；
- 每次 Revision 都重新调用题目提取 LLM；
- 根据样本 ID、题目标题、对象名或目录名添加分支；
- 直接启用不安全的最终状态 Runtime Coordinate Comparison。

## 11. 推荐接入位置

当前调用链：

```text
evals/workbench_e2e/logic_stage.py
  -> evals/_logic_shadow_case.py
  -> build_engine_review_evidence()
  -> build_logic_evidence()
  -> build_review_digest()
  -> build_review_prompt()
  -> LogicReviewer.review()
```

目标调用链：

```text
build_engine_review_evidence()
  + build_relation_evidence()
  -> build_logic_evidence()
  -> DIGEST_V2_3_RELATIONS
  -> LogicReviewer.review()
```

生产设计不修改 Orchestrator，只扩展 LogicReviewPort 背后的 Evidence Builder。

## 12. 快速验证命令

在完整平台仓库和已安装开发依赖的环境中运行：

```powershell
python -m pytest tests/unit/logic/expectations -q
python -m pytest tests/unit/geometry -q
python -m ruff check src tests evals scripts
```

生产 Contract 回放不调用模型：

```powershell
python -m evals.run_production_relation_probe `
  --dataset-root <prod_hard_logic_fixable_50_v1路径> `
  --output <输出report.json>
```

完整 Expected/Actual Probe 会调用模型，必须通过环境变量提供受控凭据：

```powershell
python -m evals.run_expected_relation_probe `
  --dataset-root <冻结数据集路径> `
  --selection evals/expected_relation_probe_v1/selection.json `
  --output <输出目录> `
  --model <模型名> `
  --workers 3
```

不要把 Key 写入命令历史、源码、Manifest 或交接文档。

## 13. 当前工程验证状态

- 完整测试：1368 passed，2 failed，4 skipped；
- 两项失败是冻结来源 Hash 不一致，属于 Fail-Closed 来源证明；
- Windows 的 4 个 Symlink 测试因系统权限跳过；
- Ruff 对 `src`、`tests`、`evals`、`scripts` 通过；
- 交接报告引用的本机证据路径均已验证。

## 14. 接手后的第一批任务

建议按以下顺序执行：

1. 冻结当前工作树并形成明确 Commit；
2. 解决两个来源 Hash 不一致的归属和更新流程；
3. 按 `EXPECTED_RELATION_MODULE_AND_INTEGRATION_ZH.md` 增加 Relation Evidence；
4. 新增 `DIGEST_V2_3_RELATIONS`，保留 `DIGEST_V2_1` 作为对照和回滚；
5. 先运行 Shadow A/B，不直接影响生产放行；
6. 建立至少 20 个全新可渲染关系错误和对应正确控制；
7. 检查 Recall、False Positive、Unknown、Tokens 和 Harness Failure；
8. 通过验收门槛后，再决定是否作为 Reviewer 默认输入。

## 15. 最终提醒

当前最容易犯的错误，是看到支持范围内的 10/10，就把该模块当成通用数学
验证器。它不是。

它最适合解决的是显式结构几何错误：

- 线段端点错；
- 点明显不在线上；
- 平行或垂直关系明显错误；
- 明确坐标关系错误。

证明方法、公式语义、角标含义、动态 Helper、Updater 和复杂运行期变换仍应
交给 Logic Reviewer 或后续更可靠的 Runtime Checkpoint 证据。

