# 来源与完整性说明

## 固定来源

本仓库的独立核心来自 MathPi `dev-PB8`：

```text
apps/render/manim_quality_platform/v3
```

原始交接包名称：

```text
manim_quality_complete_handoff_20260715_v3
```

恢复完整 V3 的主提交：

```text
9e377eb3a 修复：恢复完整V3智能修复模块
```

之后继续包含 2026-07-18 前已经通过真实 server3 批量任务验证的重叠误判、严重度、持续性和稳定性修正。

## 为什么不能只复制主仓 Git 跟踪文件

V3 原始 `MANIFEST.json` 登记 650 个文件。MathPi 主仓只跟踪其中一部分，部分冻结 vendor、Harness 数据和精简证据受原目录忽略规则影响。

本仓库发布时以 V3 真实目录和 `MANIFEST.json` 为完整性依据：

- manifest 登记文件：650；
- 缺失文件：0；
- 同时保留 V3 接入 MathPi 后的兼容修正；
- 不包含 `.pytest_cache`、`__pycache__`、虚拟环境、真实运行密钥或批量视频。

## 原始 Hash 与当前快照

`MANIFEST.json` 和 `SHA256SUMS.txt` 保存 2026-07-15 原始交接包基线。当前快照在该基线上包含后续真实接入修正，因此以下 14 个文件与原始 Hash 不同，这是预期行为。其中 `README.md` 和 `.gitignore` 是独立仓库发布所需调整，其余是后续真实接入修正：

- `.gitattributes`
- `.gitignore`
- `evals/_logic_shadow_case.py`
- `evals/workbench_e2e/layout_stage.py`
- `external/layout_probe/probe_runner.py`
- `README.md`
- `scripts/handoff_doctor.py`
- `scripts/run_existing_code_e2e.py`
- `src/manim_quality/agents/guards.py`
- `src/manim_quality/layout/classification.py`
- `src/manim_quality/logic/expectations/comparison.py`
- `tests/integration/test_overlap_safety.py`
- `tests/unit/layout/test_overlap_classification.py`
- `tests/unit/logic/test_eval_runtime_policy.py`

仓库根目录的 `CURRENT_SNAPSHOT_SHA256.txt` 是本次发布内容的当前 Hash 清单，应该用于检查本仓库是否被意外修改。

## MathPi 适配来源

`integrations/mathpi/` 来自同一提交点下的：

```text
apps/render/app/quality_platform
apps/render/tests/test_quality_platform_*.py
```

这些文件只用于解释和复用当前接入方式，不属于 V3 独立领域核心。

## 2026-07-22 同步记录

本次从 MathPi `dev-PB8` 的以下目录重新同步：

```text
apps/render/manim_quality_platform/v3
apps/render/app/quality_platform
apps/render/tests/test_quality_platform_*.py
apps/render/tests/test_v3_three_state.py
```

同步时 MathPi 仓库头部包含：

```text
796b74481 补充Agent技术实施审计与证据入口
9831139b5 汇总Agent全量日志审计与优化建议
93db536d6 兼容拆分式布局探针加载
2270964ba 保持重叠Agent令牌仅观测合同
9c1d8cd5d 修复重叠Agent五轮与最佳候选合同
```

独立仓库没有复制 MathPi 用户、积分、数据库、MQ、COS、TTS、STT 或生成主管线，只保留 V3 独立核心、Harness、测试、评估工具和宿主适配快照。
