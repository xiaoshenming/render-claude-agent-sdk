# Unified Manim Quality Agent 迁移与实测报告

日期：2026-07-26  
分支：`codex/manim-quality-agent-20260726`  
工作树：`/home/ming/data/Project/NodeProject/chap5/render-claude-agent-sdk-unified-quality-20260726`

## 1. 目标与结论

本次将 `ManimQualityAgent_20260726` 作为独立 Git 历史迁入新工作树，配置
Linux、Claude Agent SDK、Docker Manim 和静音 TTS 环境，然后运行：

1. MathPi 17 个历史逻辑错误样本；
2. BBox 排行榜前 20 个原始重叠样本。

最终结论：

- 17 题：16/17 得到 `PROPOSED`，说明该架构适合少量、深层、有关联的逻辑问题。
- BBox Top 20：0/20 得到 `PROPOSED`，说明逐次工具式精确替换不适合高密度布局问题。
- 当前最大成本不是重复 Read，而是每个 `apply_patch`、验证、布局检查都会触发新的
  Agent 推理轮次，复杂样本很快耗尽工具、轮次或缓存 Token。
- 推荐融合方案不是继续放大上限，而是保留双 Reviewer 和真实渲染验证，把父 Coder
  改为一次输出 `patches[]`，由宿主批量应用、编译和渲染。

## 2. 最终运行结构

```text
父 Quality Agent
├── math_geometry_reviewer
│   └── 完整 Solution 最多读取一次
├── animation_lifecycle_reviewer
│   └── 完整 Solution 最多读取一次
├── 父 Agent 完整读取当前 Solution 一次
├── record_findings：最多 3 批
├── apply_patch：最多 5 个精确块
├── validate_revision：最多 5 次
├── inspect_layout：最多 3 次
└── submit_revision + StructuredOutput

宿主
├── 仅允许修改 Solution
├── AST / compile
├── Docker Manim 480P 静音渲染
├── ffprobe
├── BBox probe
└── 最终独立验收
```

Reviewer 结果仍通过 Claude Agent SDK 前台 `Agent ToolResult` 回到父上下文，不使用
临时文件搬运结果。

## 3. 环境与输入适配

- Python：项目 `.venv`，Python 3.11。
- Claude Agent SDK：0.2.128。
- 模型：`gpt-5.6-sol`，effort 为 `low`。
- Manim：已有镜像 `docker-manim-worker-1:latest`。
- TTS：使用已有静音 runtime stubs，不请求外部语音服务。
- Provider 凭证：仅在子进程环境注入，没有写入仓库、报告或日志。
- BBox 输入：按 `BBox指标排行榜.csv` 取前 20。
- BBox 原码只有 `MainScene`，准备脚本仅将入口类名改为 `Solution`；没有改题目、
  动画内容或布局逻辑。
- BBox 样本没有独立题干元数据，流水线使用源码哈希作为问题身份，并以源码中的
  voiceover、公式、图形和真实渲染作为审查证据。

## 4. 最小迭代内容

本次没有加入新的质量拦截。改动均用于让 Agent 能完成既定流程：

1. Reviewer ToolResult 上限从过窄值放宽到可容纳完整问题列表。
2. patch、validation 和 session 的次数保持一致。
3. 外部工具调用失败后，将错误返回同一个 Agent 会话，让模型修正参数，不再直接终止。
4. 失败调用仍计入总工具预算，但返还该工具的成功调用配额。
5. StructuredOutput 允许第二次自纠。
6. Docker 包装器支持挂载下载目录中的外部审计源码。
7. 内外层超时统一，避免外层允许 900 秒、内层 600 秒提前终止。
8. 复杂样本最多 5 个精确补丁、3 批 findings；没有取消单次完整读取限制。

## 5. MathPi 17 题结果

### 5.1 汇总

| 指标 | 结果 |
|---|---:|
| 原始样本 | 17 |
| PROPOSED | 16 |
| 未通过 | 1 |
| 成功率 | 94.1% |
| 成功结果可核算 Token | 1,266,710 |

Token 口径只包含成功生成 `decision.json` 的调用。当前 CLI 在失败时没有落盘完整
`AgentCallRecord`，因此失败尝试的 Token 不能可靠计入；这也是后续需要补齐的可观测性缺口。

### 5.2 成功样本明细

| 样本 | 轮次 | 工具调用 | Token | 最终 revision |
|---|---:|---:|---:|---:|
| 017 角内等腰线段计算 | 12 | 15 | 77,327 | R2 |
| 022 外角平分线结论探究 | 10 | 15 | 49,655 | R1 |
| 030 角平分线双垂直综合题 | 13 | 17 | 95,107 | R2 |
| 042 线段和差证明 | 14 | 15 | 109,653 | R2 |
| 045 全等三角形练习1 | 12 | 15 | 84,965 | R2 |
| 047 全等三角形练习2 | 12 | 16 | 100,052 | R2 |
| 054 全等三角形练习4 | 12 | 15 | 93,232 | R2 |
| 057 全等三角形练习2 | 10 | 11 | 50,564 | R1 |
| 058 全等三角形练习3 | 10 | 11 | 63,691 | R1 |
| 076 加油站第二讲练习2 | 10 | 11 | 57,692 | R1 |
| 078 加油站第二讲练习4 | 12 | 17 | 85,208 | R2 |
| 080 倍长中线模型 | 12 | 13 | 89,861 | R2 |
| 099 加油站第四讲练习1 | 12 | 17 | 75,937 | R2 |
| 100 加油站第四讲练习2 | 14 | 18 | 95,690 | R3 |
| 108 全等三角形练习2 | 10 | 11 | 49,666 | R1 |
| 117 全等三角形第56题 | 12 | 13 | 88,410 | R2 |

### 5.3 唯一未通过：035 腰上的高求底角

Agent 已生成并真实渲染到 R5，但最终 BBox 检查仍有 3 个 blocking：

- 末段 `40°` 标签与多边形重叠；
- 同一标签与线段重叠；
- 早段文本与公式重叠。

因此不能把 R5 标记为修好。R5 视频和证据保留在：

`/home/ming/下载/ManimQualityAgent_20260726-17题失败4项最终重跑/035_16_平行班第五讲_04_练习1第(4)题腰上的高求底角/agent_runtime/R5`

## 6. BBox 排行榜 Top 20

### 6.1 最终汇总

| 指标 | 结果 |
|---|---:|
| 样本 | 20 |
| PROPOSED | 0 |
| 未通过 | 20 |
| 成功率 | 0% |
| 最终批次耗时 | 2,010.796 秒 |

最终结果目录：

`/home/ming/下载/ManimQualityAgent_20260726-BBox排行榜Top20最终结果`

### 6.2 失败分类

| 原因 | 数量 |
|---|---:|
| 总工具预算耗尽 | 6 |
| 布局检查次数耗尽 | 6 |
| StructuredOutput 纠正耗尽 | 3 |
| 缓存读取 Token 耗尽 | 2 |
| 补丁次数耗尽 | 1 |
| findings 批次耗尽 | 1 |
| Reviewer 字段协议不兼容 | 1 |

### 6.3 逐样本结果

| 排名 | case_id | 原始 BBox | 历史残留 | 已生成 revision 数 | 最终卡点 |
|---:|---|---:|---:|---:|---|
| 1 | 01KXZSE3J65B70FSW0RB6617YN | 42 | 0 | 5 | 布局检查次数耗尽 |
| 2 | 01KXZSAMT17EA2JZBF6YJ1FKB0 | 36 | 7 | 4 | 布局检查次数耗尽 |
| 3 | 01KY0F1Z41VAJBESRC7GCTMGCE | 23 | 0 | 4 | findings 批次耗尽 |
| 4 | 01KY0F51TA7HPR0AMMJVE5Y994 | 10 | 4 | 2 | StructuredOutput 纠正耗尽 |
| 5 | 01KXZSA9SR5PAP1HW36MBWCZF8 | 10 | 0 | 4 | 缓存读取 Token 耗尽 |
| 6 | 01KY32Q47APQHC0XVMGZGYWZAC | 9 | 0 | 4 | 总工具预算耗尽 |
| 7 | 01KY0ETPX47JRMPSTCYWQ2NT1P | 8 | 0 | 4 | 布局检查次数耗尽 |
| 8 | 01KY0F4HGGHDSHR73B7NWE3DFC | 8 | 0 | 4 | 总工具预算耗尽 |
| 9 | 01KY0EMFT2W3QJZRA2JNBSM7RJ | 7 | 0 | 3 | 总工具预算耗尽 |
| 10 | 01KY32JSA9EKEEC6NVWRS5B8FE | 7 | 0 | 4 | 布局检查次数耗尽 |
| 11 | 01KXZS9KKKHN1REHFZMWF8DF54 | 6 | 0 | 5 | 布局检查次数耗尽 |
| 12 | 01KY0EQK2WHDBABGJTN4XC0BPQ | 6 | 0 | 3 | 总工具预算耗尽 |
| 13 | 01KY0F2FN94A3JQ7N3AWE62PZY | 6 | 0 | 5 | 总工具预算耗尽 |
| 14 | 01KY0F38C8DJZ70A4KSBJTH4G4 | 6 | 0 | 4 | 布局检查次数耗尽 |
| 15 | 01KY0EJP3ZH03N34FRZSXY8RTB | 4 | 0 | 4 | 总工具预算耗尽 |
| 16 | 01KY0F49B6V8WQXNYZW48GNZDK | 4 | 0 | 0 | Reviewer 字段协议不兼容 |
| 17 | 01KXZJB56SS2M0WQ255GSCDWJV | 3 | 0 | 5 | 补丁次数耗尽 |
| 18 | 01KXZSEEV6ETVRDTS3PS21Y4P3 | 3 | 0 | 5 | 缓存读取 Token 耗尽 |
| 19 | 01KY0F0DWMB1D4RWWHVGPXXSE7 | 3 | 0 | 2 | StructuredOutput 纠正耗尽 |
| 20 | 01KY2M2PBKM2AZMEK48M3ZRQG1 | 3 | 0 | 1 | StructuredOutput 纠正耗尽 |

## 7. 为什么 BBox 结果差

问题不在 Reviewer 是否读到了完整源码，而在父 Agent 的修改合同：

```text
一个问题簇
→ apply_patch
→ validate_revision
→ inspect_layout
→ 新一轮模型推理
```

大量 BBox 样本包含多个独立问题簇。即使完整源码只读一次，5 个 patch 仍会产生多轮累计
上下文、渲染和布局检查。结果是：

- Read 次数少，但 Token 不低；
- 每个小 Edit 都重复携带累计上下文；
- 修复越多，cache read Token 越高；
- 最后还可能在 StructuredOutput 阶段失败，浪费已完成的修改。

## 8. 推荐融合方案

保留本项目最有价值的部分：

- 两个专业 Reviewer；
- 完整 Solution 一次读取；
- 生命周期、坐标和数学关系审查；
- AST、编译、真实 Manim 渲染和 BBox 证据；
- 只允许修改 `Solution`。

替换父 Coder 的逐工具修改环：

```text
两个 Reviewer ToolResult
        ↓
父 Coder 完整 Solution 一次输入
        ↓
一次输出
{
  "findings": [...],
  "patches": [
    {"old_text": "...", "new_text": "...", "finding_ids": [...]}
  ]
}
        ↓
宿主批量校验唯一匹配并应用
        ↓
AST / compile / render / BBox
        ↓
仅在真实验证仍失败时发起一次定向修复
```

这样可以同时解决：

1. 多个 `Edit` 造成的模型往返和 cache read Token；
2. 单个 patch 次数上限不适合高密度 BBox；
3. Agent 在最后 StructuredOutput 失败导致整轮产物丢失；
4. 工具参数 stale revision 等可恢复错误；
5. 失败调用没有完整 Token 归档。

## 9. 验证与已知基线

本轮相关测试全部通过，包括：

- Operator session / toolset；
- Claude SDK hooks；
- ToolGuard；
- 工程文件 300 行上限；
- Docker 外部源码挂载。

全量测试结果为 1459 passed、6 failed。6 个失败均来自迁入包的既有基线：

- 1 个旧 SDK 集成脚本仍使用已删除工具名；
- 2 个冻结 vendor / holdout 哈希不一致；
- 3 个 Windows `file:///` 路径测试在 Linux 下失败。

本轮没有新增全量测试失败。

## 10. 版本记录

核心提交按时间顺序包括：

- 迁入统一 Agent 基线；
- 配置 Linux Docker Manim；
- 支持外部审计目录；
- 放宽完整 Reviewer 输出；
- 同步 patch / validate 预算；
- 工具失败返回 Agent 自纠；
- 失败调用返还单工具成功配额；
- StructuredOutput 二次自纠；
- 复杂样本五次收敛修复；
- 第三批关联 findings；
- 维持 300 行工程约束。

所有改动均保存在 `codex/manim-quality-agent-20260726`，未推送远端。
