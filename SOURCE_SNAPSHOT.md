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
