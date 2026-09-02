# 六题 Helper 源码可达闭包 Reviewer A/B 验证

## 结论

本次修改在六题真实冻结数据上，将五个属于 Review1/Review2 职责的已知根因精确召回率从 **0/5 提升到 5/5**。`20-middle30` 的模板选择错误发生在 Reviewer 上游，不计入这五项，也没有通过 Reviewer 擅自改写模板。

该结果证明“把当前 `Solution` 可达的 Header/helper 实现一并提供给 Reviewer，并补充少量源码不变量”确实有用。它目前证明的是 **Reviewer 能看见并准确指出问题**，尚未证明 Coder 一定能把五项全部修好；完整 Coder→Render→终审闭环应作为下一阶段验证。

## 冻结输入

- Server9 证据目录：`/var/lib/mathpi/review/reviewer-ast-ab-six-20260902`
- Server9 归档：`/var/lib/mathpi/review/reviewer-ast-ab-six-20260902.tar.gz`
- 本地副本：`/tmp/reviewer-ast-ab-six-work/reviewer-ast-ab-six-20260902/cases`
- Manifest SHA256：`99446ce62caf906175a07d03b31854c977ff3417e70238cf7b9a990c12286432`
- 归档 SHA256：`dfe7c749924a110ed8a30f5d97d3b26617cd6dcab5eb8651bf21ec3a2d7fa067`
- 样本：`08-middle30`、`13-middle30`、`16-middle30`、`20-middle30`、`26-middle30`、`29-middle30`
- 模型：环境中配置的 `gpt-5.6-sol`
- A/B 边界：同一批最终源码、同一批题目/答案/五段式脚本、同一 Reviewer 调用方式；变量仅为是否提供可达 helper 源码和确定性源码事实。

## 已知问题与 A/B 结果

| 样本 | 人工确认根因 | 改动前 | 改动后 |
|---|---|---|---|
| 08 | 页面 helper 先完整退场，后开始下一页，产生教学页空闪 | 未定位根因 | Review1/2 均定位顺序退场空窗 |
| 13 | `panel_2_proof` 未重新显现却被第二次 `FadeOut`，可能闪回旧内容 | 只泛化描述重复弧，未定位根因 | Review1/2 均定位重复退场及首次/二次行号 |
| 16 | helper 对真实 AB 几何对象执行 `Indicate(scale_factor>1)` | 未定位根因 | Review1/2 均定位真实几何瞬时漂移 |
| 20 | 上游选错模板 | 不属于 Review1/2 | 仍由上游模板事实源负责；未被 AST 规则误判 |
| 26 | helper 对真实 OA/OC 几何对象执行缩放强调 | 未定位根因 | Review1/2 均定位真实几何瞬时漂移 |
| 29 | 用 `get_points()[...]` 作为语义点 B，索引不具备稳定语义 | 未定位根因 | Review1/2 均定位不透明几何锚点 |

精确根因召回：**0/5 → 5/5**。六题内确认的 AST 规则误报为 **0**。`20-middle30` 的 Review2 仍指出权威讲解与源码内容覆盖差异，那是原有内容审查结论，不是 AST 几何规则误报。

## 时间与 Token

| 指标 | 改动前 | 改动后 |
|---|---:|---:|
| 六题 Reviewer 并行墙钟合计 | 633.172 秒 | 562.524 秒 |
| 单题平均墙钟 | 105.529 秒 | 93.754 秒 |
| 单题 P50 | 62.839 秒 | 77.849 秒 |
| 单题最大值 | 314.577 秒 | 153.367 秒 |
| 12 次 Reviewer 总 Token | 286,972 | 416,255 |
| 单次 Reviewer 平均 Token | 23,914 | 34,688 |

Token 增加约 **45.1%**，这是注入 helper 源码的明确代价。墙钟受上游响应波动影响，不能据本轮宣称性能提升；P50 实际增加约 **23.9%**。后续应继续裁剪 helper 闭包，而不是删除诊断能力。

## 实现边界

- 只提取从 `Solution` 实际可达的父类方法、动态别名函数及其依赖，不注入整份 Header。
- 总量限制为 56 个 helper、52,000 字符，并优先保留 transition/highlight/anchor 等审查相关 helper。
- 确定性 AST 只提供证据，不新增质量拦截、不阻止渲染，Reviewer 仍需结合语义作判断。
- Review1 只接收数学锚点和真实几何缩放事实；页面生命周期事实只属于 Review2，避免职责串线。
- 普通 `Text/MathTex`、结果行、非几何有限列表索引不按几何漂移/锚点错误处理。

## 复现

基线输出：

- `/tmp/reviewer-ab-before-final/results.json`

最终 A/B 结果来自收敛后的逐样本结果：

- 08：`/tmp/reviewer-ab-after-v5-final/results.json`
- 13：`/tmp/reviewer-ab-after-v6-final/results.json`
- 16、26、29：`/tmp/reviewer-ab-after-v3-final/results.json`
- 20：`/tmp/reviewer-ab-after-v8-final/results.json`

运行入口：

```bash
.venv/bin/python scripts/run_source_reviewer_ab.py \
  --cases-root /tmp/reviewer-ast-ab-six-work/reviewer-ast-ab-six-20260902/cases \
  --source-name final_source.py \
  --reviewers math_geometry_reviewer,animation_lifecycle_reviewer \
  --output /tmp/reviewer-ab-results
```

验证结果：`tests/unit/operator` 与工程规范测试合计 **192 passed**。

## 上线前剩余验证

1. 增加一批人工确认正常的 transition/highlight 样本，量化误报率。
2. 在不改变题目、模型与源码的前提下，验证 Coder 是否能按精确反馈修复并通过真实 Manim 渲染。
3. 观察 Token；若成本过高，继续基于 call graph 压缩 helper 源码，不退回只看 `Solution` 的盲审方式。
