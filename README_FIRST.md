# Manim Quality 完整交接包 V3

这不是只含核心源码的压缩包。本包包含真实跑过结果的 E2E Harness、Logic/Overlap vendor、layout probe、最小提示词库、真实生成代码样本、环境检查、运行脚本、测试依据和完整文档。

## 两种使用方式

### A. 已有可渲染代码，进行质量审查和修复

这是接入现有代码生成服务时应使用的模式：

```text
candidate.py + 题目 + 参考解
→ Logic Reviewer/Coder/Verifier
→ Manim 重渲染
→ Overlap Detect/Repair/Recheck
→ candidate_final.py + video_final.mp4 + result.json
```

入口：`scripts/run_existing_code_e2e.py`

### B. 从题目生成代码，再走完整质量链路

这是复现历史 Workbench E2E 实验时使用的模式：

```text
题目 → LLM 生成代码 → 渲染恢复 → Logic → Layout → 最终视频
```

入口：`scripts/run_handoff_batch.py`

## 首次执行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

$env:ANTHROPIC_BASE_URL='https://ai.onegodtoken.top'
$env:QUALITY_MODEL='gemini-3.5-flash-high'
$env:MANIM_QUALITY_API_KEY='<由部署环境注入>'

.\.venv\Scripts\python.exe scripts\handoff_doctor.py `
  --manim-python 'D:\path\to\manim-python.exe' `
  --require-api-key
```

Doctor 全部 PASS 后，再运行真实任务。密钥不会写入报告或打印到控制台。

完整命令、目录结构、结果读取和故障定位见 `docs/handoff/FULL_E2E_HANDOFF_RUNBOOK_ZH.md`。

## 重要边界

- `manim_quality` 是领域核心。
- `evals/workbench_e2e` 是当前真实跑通流程的 Harness，本次已完整随包交付。
- V3 允许部署方复现全流程，但当前 Harness 仍不是最终 `QualityEngine.repair()` 产品接口。
- 企业 API/Queue/Orchestrator 的生产 composition root 仍需按 `docs/plans/2026-07-15-production-pipeline-composition-root.md` 完成。
- 不需要 DEV-PB5、`manim_test_tool` 或本机其他仓库；所需 probe 和最小 prompt 数据已经收进包内。
