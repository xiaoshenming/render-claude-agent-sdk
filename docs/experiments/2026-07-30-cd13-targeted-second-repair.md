# C/D 13 题终审回投二轮修复归档

## 版本边界

- 稳定基线：`f63aa10`（TTS-aware Final Assurance）
- 回投实现：`4c9a1a5`（终审问题作为只读证据回投 Coder）
- 模型：`gpt-5.6-sol`
- 协议：Anthropic
- TTS 合同：`silent`，静音和缺少 TTS 不计为质量问题
- 输入：60 题最终批次中等级为 C/D 的 13 题
- 输入源码：每题第一轮 Coder 已完成后的最终 `proposed_candidate.py`
- 回投问题：21 条非 TTS Final Assurance issue

## 实际执行结果

### Coder 二轮

| 指标 | 结果 |
|---|---:|
| 题数 | 13 |
| PROPOSED | 13 |
| HOLD / FAILED | 0 / 0 |
| tokens | 2,113,736 |
| turns | 269 |
| tool calls | 230 |
| 墙钟时间 | 1,258.031 秒（20 分 58 秒） |

Coder 仍只开放原生 `Read`、`Edit` 与受控质量工具。每个输入上下文绑定第一轮最终源码 SHA、终审 issue ID、severity、category 和 evidence IDs。

### 最新 Final Assurance

| 指标 | 结果 |
|---|---:|
| 完成 | 13/13 |
| PASS / REVIEW | 8 / 5 |
| Agent error | 0 |
| tokens | 499,473 |
| turns | 195 |
| tool calls | 156 |
| 墙钟时间 | 约 7 分 33 秒 |

从 Coder 正式启动，到终审结果写完总计 29 分 55 秒；其中约 1 分 18 秒用于冻结源码、视频及生成 manifest。

## 评级迁移

| 阶段 | A | B | C | D | E |
|---|---:|---:|---:|---:|---:|
| 二轮前 | 0 | 0 | 10 | 3 | 0 |
| 二轮后 | 8 | 2 | 2 | 1 | 0 |

- 有效 issue：21 → 6，减少 71.4%。
- 11/13 题评级提升，1 题不变，1 题退化。
- 8 题终审完全通过。
- GEO-038、LIN-008 只剩可读性或节奏类中低风险。

仍有 high issue：

1. `22_GEO-016`：O/M 锚点混淆及 E 点直角标记方向错误，C → D。
2. `39_LIN-031`：B/C/D 选项的 `k*b` 派生斜率错误仍未修复，C → C。
3. `60_GEO-037`：四个问题降至一个，仍错误强调 `∠CPQ`，D → C。

## 可恢复产物

server8 根目录：

`/data/mathpi/agent-quant/experiments/cd13-r2-20260730`

关键路径：

- 回投输入及 SHA：`package/manifest.json`、`package/SHA256SUMS`
- Coder 输出：`outputs/coder-r2/`
- 二轮冻结数据集：`dataset-r2-13/manifest.json`
- 终审结果：`outputs/final-assurance-r2-13/results.json`
- 终审报告：`outputs/final-assurance-r2-13/report.md`
- 对照数据：`/data/mathpi/agent-quant/native-read-edit-20260730-r1/reports/cd13-r2-comparison/data.json`
- 对照页面：<http://120.92.208.132:8898/reports/cd13-r2-comparison/index.html>

对照页面已验证 HTML 200；MP4 已验证真实 Range 206 和 1,024 字节分段读取。

归档不得包含 `provider.env`、API Key、令牌或其他密钥。恢复时由目标环境重新注入凭据。

## 结论

终审问题回投 Coder 的二轮路线有效，尤其适合确定范围的 C/D 尾部样本。它不应无限循环：建议最多自动回投两轮，超限后保留最佳可播放 revision 并进入人工复核。派生数值和几何锚点问题应继续增加确定性验证，不能只依赖 Coder 自报已修复。
