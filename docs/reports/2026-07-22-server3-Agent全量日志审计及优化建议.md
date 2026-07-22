# server3 昨晚至今逻辑与重叠 Agent 全量日志审计及优化建议

> 审计窗口：2026-07-21 20:00 CST—2026-07-22 20:05 CST
>
> 取证环境：server3 测试服务器
>
> 读者：技术负责人、Render/Agent 平台维护者
>
> 证据范围：历史错误源码重放、专项补跑、最新线上任务、数据库质量事件、Reviewer/Coder/Verifier 日志、布局逐轮日志、MQ 与运行态
>
> 重要边界：本文统计的是机器检测与候选修复能力。除特别说明外，`candidate_ready`、BBox 清零均不等于已经完成人工数学或视觉验收。

## 配套技术落地材料

如果读者需要直接拆工单和开始开发，请优先阅读：

- [Agent 技术改造点对点功能审计](2026-07-22-Agent技术改造点对点功能审计.md)：13 个原子改造点，包含源码行号、测试入口、明确缺口、实施动作、工时、依赖和验收 Runbook；
- `/home/ming/仓库整理归档/shuxuepai-agent-audit-evidence-20260722.tar.gz`：精选并脱敏的 server3 真实日志、逐 case 证据、源码/测试快照和 SHA256 清单。

本文负责解释“发生了什么、数据说明什么”；点对点审计负责回答“具体改哪里、谁来做、怎样验收”。

## 一、先给结论

这套系统不是“Agent 没有运行”，也不是“AI 普遍不会修”。昨晚至今的详细日志证明：

1. **逻辑 Agent 能发现并修复真实数学问题。**修复日志合同后的 33 条历史 rejected 源码中，14 条真正进入修复，10 条形成机器验收通过的候选，候选采用率为 **71.4%**。剩余 4 条的主要损失不是统一的数学能力不足，而是 3 条被重复读取源码的硬规则终止，1 条被 Verifier 的机械证据行绑定误杀。
2. **最终定向重投的“100%”是真的，但分母只有 1。**最终补跑的 3 条里，只有 1 条被 Reviewer 明确判定需要修复，该条成功形成候选，所以是 `1/1=100%`；另外 1 条改判为通过，1 条转人工。它不能代表整个逻辑 Agent 已达到 100%。
3. **重叠 Agent 的新版合同提升非常明显。**同类 50 条困难源码在旧合同时，29 条触发 Agent，25 条改善、18 条清零、9 条 rejected，其中 5 条已经改善却被退回原代码；部署五轮和最佳候选保护后，29 条触发任务全部改善，26 条清零，3 条保留残留最佳候选，0 条 rejected。
4. **当前五轮合同已在运行态真实生效。**专项重放中真实出现第 4、5 轮；当前 server3 直接导入运行配置也确认 `max_rounds=5`。但数据库里昨晚至今的 102 条线上质量任务全部结束于 15:42，新合同在 17:24 才部署，所以这 102 条不能用于评价五轮新版线上稳定性。
5. **当前最大的工程问题已经从“有没有日志”收敛为“事实口径和少数证据缺口”。**历史重放的逐条日志很完整；但最新两条线上逻辑候选没有长期保存完整的 Reviewer/Coder/Verifier/diff，部分 fail-open 也缺 manifest；同一任务的重试事件还会重复进入报表。
6. **当前主要性能瓶颈是布局 Agent，不是逻辑 Reviewer，也不是静音预览本身。**旧线上数据中 Layout 中位耗时约 50.3 秒、P95 约 150.5 秒；五轮困难集里，触发 Agent 后的编排中位约 107.9 秒，极端复杂样本达到 901.4 秒和 786,917 Token。

建议技术路线不是继续盲目增加随机任务，而是依次完成：

- P0：消除逻辑工具协议误杀，补齐每次修复的原子证据；
- P0：建立唯一的 Agent attempt 事实口径，彻底解决重试重复统计；
- P1：把高密度布局问题按时间窗和区域拆小，细分每轮耗时；
- P1：部署后先跑 10—20 条线上冒烟，确认五轮合同在线上真实入口生效；
- P2：建立 50—100 条人工金标集，测真实召回率、误报率和人工确认修复率。

## 二、这次审计到底看了哪些数据

### 2.1 为什么不能只看一个成功率

昨晚到今天至少存在七组不同数据：

| 数据组 | 用途 | 是否可直接评价当前新版 |
|---|---|---|
| 历史逻辑问题 50 条首轮重放 | 暴露旧日志合同与 Reviewer 口径漂移 | 只能作基线 |
| 历史 rejected 原始源码 33 条重放 | 评价日志合同修复后的逻辑候选能力 | 是当前主要逻辑证据 |
| 4 条异常补跑、3 条最终定向重投 | 验证鉴权/额度恢复和协议修复 | 只能评价定向样本 |
| 旧合同重叠困难 50 条 | 重叠修复改造前基线 | 只能作对照 |
| 五轮新合同重叠困难 50 条 | 验证五轮、最佳候选、Token 仅观测 | 是当前主要重叠证据 |
| 昨晚至今 102 个线上质量完成任务 | 观察真实入口、重试、Token、耗时 | 属于五轮部署前在线数据 |
| 17:24 后当前运行态 | 验证配置和服务健康 | 尚缺新线上批次样本 |

这些数据不能合并成一个“整套 Agent 总成功率”。逻辑和重叠是不同样本，历史重放和线上任务也不是同一总体。

### 2.2 数据去重规则

审计窗口内数据库存在：

- `pre_archive_quality_platform_completed` 原始事件 104 条；
- 去重后 102 个唯一 job；
- 100 个 job 只有一条完成事件；
- 2 个 job 各有两条完成事件。

正确统计方式是：

```text
按 job_id 分组
→ 按 created_at、id 排序
→ 每个 job 只取最后一条完成事件
```

不能直接累加事件行。MQ 重试、redelivery、同一任务多 attempt 都会制造重复状态、重复 Token 和重复错误。

### 2.3 主要证据位置

逻辑 Agent：

```text
/opt/mathpi/quality-replay/logic-needs-repair-latest50-20260721
/opt/mathpi/quality-replay/logic-original-rejected-latest50-fixed-20260721
/opt/mathpi/quality-replay/logic-original-rejected-final-retry-16973f1e5
```

重叠 Agent：

```text
/opt/mathpi/apps/render/manim_media/overlap-improved-failed-replay-50-20260722
/opt/mathpi/apps/render/manim_media/overlap-best-five-replay-r2-20260722
```

线上事实：

```text
MySQL mathpi_test.quality_events
MySQL mathpi_test.video_generation_jobs
systemd journal: mathpi-render
RabbitMQ Docker runtime / health
```

## 三、逻辑 Agent：从首轮 41.7% 到修正后 71.4%

### 3.1 第一批：历史逻辑问题 50 条首轮重放

证据：

```text
/opt/mathpi/quality-replay/logic-needs-repair-latest50-20260721/summary.json
```

完成时间：2026-07-21 23:47:50 CST。

| 状态 | 数量 | 正确理解 |
|---|---:|---|
| `review_pass` | 35 | 新 Reviewer 认为当前证据不足以证明需要修改，不是“修好了35条” |
| `candidate_ready` | 5 | Coder 修改并通过当前机器合同 |
| `rejected` | 7 | 已进入修复，但候选或工具合同未通过 |
| `human_review` | 2 | 证据不足，交人工 |
| `review_record_only` | 1 | 低风险观察，仅记录 |

真正进入修复的是 12 条：

```text
5 candidate_ready + 7 rejected = 12
候选采用率 = 5 / 12 = 41.7%
```

资源消耗：

| 指标 | Reviewer | Repair |
|---|---:|---:|
| 总 Token | 1,550,973 | 650,075 |
| 总耗时 | 1,122.220 秒 | 329.928 秒 |

整批总 Token 为 **2,201,048**，总墙钟约 **1,452.631 秒**。

### 3.2 第二批：日志合同修复后的 33 条历史 rejected 原始源码

证据：

```text
/opt/mathpi/quality-replay/logic-original-rejected-latest50-fixed-20260721/summary.json
```

完成时间：2026-07-22 00:12:19 CST。

| 状态 | 数量 | 占比 |
|---|---:|---:|
| `review_pass` | 18 | 54.5% |
| `candidate_ready` | 10 | 30.3% |
| `rejected` | 4 | 12.1% |
| `human_review` | 1 | 3.0% |

真正进入修复的是 14 条：

```text
10 candidate_ready + 4 rejected = 14
候选采用率 = 10 / 14 = 71.4%
```

这说明修正原始源码入口和日志合同后，候选采用率从 41.7% 提升到 71.4%。但这仍是“机器合同接受率”，不是老师确认后的数学正确率。

资源消耗：

| 阶段 | 总 Token | 中位数 | 总耗时 |
|---|---:|---:|---:|
| Reviewer，33条 | 1,144,260 | 30,607 | 1,148.619 秒 |
| Repair，仅14条 | 778,499 | 48,451.5 | 560.204 秒 |
| 合计 | **1,922,759** | — | 1,708.913 秒墙钟 |

单条墙钟中位约 35.2 秒；Reviewer 中位约 28.4 秒；触发 Repair 后的修复中位约 34.8 秒。

### 3.3 最终定向重投：“1/1=100%”的准确含义

最终补跑目录：

```text
/opt/mathpi/quality-replay/logic-original-rejected-final-retry-16973f1e5
```

该目录有逐 case 结果，但没有统一批次 `summary.json`，因此本次按三个 `replay_result.json` 逐条复算。

| Job ID | Reviewer结论 | 最终状态 | Token | 耗时 |
|---|---|---|---:|---:|
| `01KXTBG0PN9XNTYRRDQTE6W5J0` | `needs_repair` | `candidate_ready` | Review 31,608；Repair 30,075 | 43.372 秒 |
| `01KXYV3Z14WVWMH84G9WMS72SJ` | `pass` | `review_pass` | Review 21,930 | 22.411 秒 |
| `01KXTBARWSRQ24KKGXJ1B5WPR1` | `human_review` | `human_review` | Review 94,299 | 60.227 秒 |

因此：

- 真正触发修复：1 条；
- 成功形成候选：1 条；
- 修复候选成功率：`1/1=100%`；
- 三条中自动给出明确 pass/repair 结论：`2/3=66.7%`；
- 协议错误、鉴权错误、修复失败：最终重投为 0 条。

技术报告中不能写“逻辑 Agent 总体 100%”，应写：

> 最终定向重投中，唯一被确认需要修复的样本成功形成候选；该小样本修复率为 100%，但不足以证明整体稳定率。

## 四、逻辑 Agent 到底修了什么

### 4.1 仿射变换公式错误：成功修复

Job：`01KY2ZMJP5QCEJ20QNJKVF6X3R`

Reviewer 明确定位：

- 原代码把一般仿射变换写成 `T(r0+tv)=T(r0)+tT(v)`；
- 这错误地把方向向量也当成仿射点直接变换；
- 同时声称“仿射保持线性组合”，表述不严谨；
- 日志给出代码行、原内容、正确内容、证据和验证规则。

Coder 改为：

```text
T(r0) + t·v'
```

其中 `v'` 是线性部分变换后的方向。Verifier 逐项 `verified`，最终 `candidate_ready`。

| 阶段 | Token | 耗时 |
|---|---:|---:|
| Reviewer | 36,454 | 40.795 秒 |
| Repair | 51,310 | 28.569 秒 |

### 4.2 圆内接四边形证明循环论证：成功修复

Job：`01KY2ZPTAGD2JNPERAC40S8EWF`

Reviewer 发现代码用“对应弦相等、对应圆心角相等”证明本应基于全等得到的对应关系，形成循环论证，并与口播“对应边、对应角”冲突。

Coder 最小修改为“对应边相等、对应角相等”，Verifier 逐行确认，最终 `candidate_ready`。

| 阶段 | Token | 耗时 |
|---|---:|---:|
| Reviewer | 17,975 | 16.201 秒 |
| Repair | 33,761 | 20.886 秒 |

这两例证明逻辑 Agent 不只是修改状态：它确实能形成“错误定位→局部代码修改→Verifier验证→候选采用”的完整链路。

## 五、逻辑修复失败的真实原因

33 条重放中 4 条 rejected 不能简单归纳为“AI不会修”。

### 5.1 三条被 DuplicateRead 硬规则终止

涉及任务：

- `01KXYV3Z14WVWMH84G9WMS72SJ`
- `01KXWDS2GNN3AAZBMJ4SQ5RRW5`
- `01KXTBG0PN9XNTYRRDQTE6W5J0`

典型错误：

```text
DuplicateRead: duplicate Read call: candidate.py
```

Agent 为确认上下文再次读取 `candidate.py`，平台把重复读取视为硬异常，直接终止修复。

这三条的 Reviewer 实际已经给出了明确问题：

- 数位术语和田字格笔画边界冲突；
- 双缝干涉中央亮暗条纹、缝间距与箭头含义错误；
- 使用 `get_start()` 导致退化三角形，应读取另一端点。

因此至少 3/4 rejected 首先是工具协议误杀，不是 Reviewer 没发现问题。

### 5.2 一条被 Verifier 证据绑定误杀

Job：`01KXTBARWSRQ24KKGXJ1B5WPR1`

Reviewer 判断点 P、D 不在目标圆上。Coder 已修改坐标，Verifier 两次语义判断均为 `verified`，但平台要求修复后的证据必须机械匹配原 issue 的 source hunk：

```text
resolved candidate evidence must match issue source hunk
```

随后触发：

```text
structured output correction limit exceeded
```

这类情况更准确的含义是：候选很可能已经改善，但引用格式未通过平台机械合同。正确做法是保留候选并标记人工风险，而不是把它等同于“AI修错”。

## 六、重叠 Agent：旧合同与五轮新版的同类对照

### 6.1 旧合同困难 50 条

证据：

```text
/opt/mathpi/apps/render/manim_media/overlap-improved-failed-replay-50-20260722
```

| 指标 | 结果 |
|---|---:|
| 总样本 | 50 |
| 新版检测 clean | 21 |
| 触发 Agent | 29 |
| 指标改善 | 25/29，86.2% |
| 完全清零 | 18/29，62.1% |
| 残留候选 | 2 |
| rejected | 9 |
| runner error | 0 |
| 总 Token | 4,406,288 |

9 条 rejected 中有 5 条其实已经改善，却因为旧的残留阈值、解析或复检合同退回原代码。

旧轮数分布：

| 轮数 | 任务数 |
|---:|---:|
| 1轮 | 15 |
| 2轮 | 10 |
| 3轮 | 4 |
| 4/5轮 | 0 |

### 6.2 部署五轮、最佳候选和 Token 仅观测后的 50 条

证据：

```text
/opt/mathpi/apps/render/manim_media/overlap-best-five-replay-r2-20260722
```

统计时必须合并：

```text
summary.json：49条
smoke_summary.json：1条
合计：50条
```

| 最终状态 | 数量 |
|---|---:|
| clean | 21 |
| 完全清零候选 | 26 |
| 残留最佳候选 | 3 |
| rejected | 0 |
| runner error | 0 |

29 条真正触发 Agent 的结果：

```text
改善：29/29 = 100%
清零：26/29 = 89.7%
残留最佳候选：3/29 = 10.3%
改善后回原代码：0
```

轮数分布：

| 使用轮数 | 任务数 |
|---:|---:|
| 1轮 | 12 |
| 2轮 | 7 |
| 3轮 | 5 |
| 4轮 | 3 |
| 5轮 | 2 |

这证明五轮不只是配置文件里的数字，第 4、5 轮已经在真实困难源码重放中运行。

### 6.3 三个历史失败案例的变化

| 历史旧结果 | 问题 | 五轮新版结果 |
|---|---|---|
| `42→19→20→退回42` | 后轮变差导致丢失历史最佳 | `42→0` |
| `36→19→14→解析失败→退回36` | 已改善候选被解析合同丢弃 | `36→7`，保留 best |
| `10→8→5→复检失败→退回10` | 当前轮复检失败拖垮历史最佳 | `10→4`，保留 best |

这正是“始终保存历史最佳候选”的价值：后续轮次失败，只放弃当前轮，不再把前面已验证的改善一起丢掉。

### 6.4 三条残留最佳候选

| Job ID | before→after | 轮数 | Token | 墙钟 |
|---|---:|---:|---:|---:|
| `01KXYHTQ4RMENF4XC674PM6FKX` | `2→1` | 3 | 161,115 | 191.132 秒 |
| `01KY0F51TA7HPR0AMMJVE5Y994` | `10→4` | 3 | 360,538 | 319.646 秒 |
| `01KXZSAMT17EA2JZBF6YJ1FKB0` | `36→7` | 4 | 786,917 | 901.445 秒 |

这些任务没有被虚假标记为“完全成功”，但平台正确返回了历史最佳代码并保留残留风险。

## 七、重叠 Agent 的 Token 与性能

五轮新 50 条中，21 条 clean 不调用 Agent；29 条触发任务：

| 指标 | 结果 |
|---|---:|
| 总 Token | 5,462,663 |
| 触发任务 Token 中位数 | 132,824 |
| 最大单条 | 786,917 |
| 整批墙钟中位数 | 55.3 秒 |
| 整批墙钟平均 | 128.5 秒 |
| 最大墙钟 | 901.4 秒 |

分阶段：

| 阶段 | 中位数 | 平均数 | 最大值 |
|---|---:|---:|---:|
| 初始静音探针 | 9.3 秒 | 11.5 秒 | 34.2 秒 |
| Agent复检累计 | 24.7 秒 | 39.5 秒 | 114.4 秒 |
| Agent编排估算 | 107.9 秒 | 162.2 秒 | 812.6 秒 |

结论：

> 静音探针通常只占十秒左右。复杂重叠任务慢，主要是多轮模型推理、读取源码、修改和反复复检，不是 Manim 静音预览本身。

## 八、昨晚至今线上真实入口数据

### 8.1 任务终态

审计窗口内新建任务 108 个：

| 终态 | 数量 |
|---|---:|
| SUCCESS | 102 |
| FAILED | 6 |

102 个 SUCCESS 均有去重后的质量平台完成事件。6 个 FAILED 没有完成 pre-archive Agent 平台，不能把它们归因成逻辑或重叠 Agent 修复失败。

### 8.2 线上逻辑 Agent

| 状态 | 数量 |
|---|---:|
| `review_pass` | 90 |
| `candidate_ready` | 4 |
| `review_record_only` | 3 |
| `rejected` | 1 |
| fail-open，无logic字段 | 4 |

真正触发逻辑修复的是 5 条：

```text
candidate_ready 4
rejected 1
机器合同候选接受率 = 4/5 = 80%
```

不能把 90 条 `review_pass` 算作“修复成功”；它们只是 Reviewer 没有确认需要修复。

线上逻辑 Token：

| 阶段 | Token |
|---|---:|
| Review | 1,841,827 |
| Repair | 221,906 |
| 合计 | 2,063,733 |

耗时：

| 阶段 | 中位数 | P95 | 最大值 |
|---|---:|---:|---:|
| Logic Review | 12.2 秒 | 27.2 秒 | 66.0 秒 |
| Logic Repair | 29.5 秒 | 样本不足 | 42.0 秒 |

### 8.3 线上重叠 Agent

| 状态 | 数量 |
|---|---:|
| clean | 37 |
| candidate | 36 |
| residual candidate | 13 |
| rejected | 8 |
| vendor clean | 4 |
| 无layout结果 | 4 |

61 条至少触发一轮布局修复：

- 57 条指标改善，改善率 93.4%；
- 40 条清零，清零率 65.6%；
- 49 条保留 candidate/residual；
- 8 条 rejected。

旧在线轮数分布：

| 轮数 | 数量 |
|---:|---:|
| 0轮 | 37 |
| 1轮 | 55 |
| 2轮 | 5 |
| 3轮 | 1 |
| 缺失 | 4 |

重要时间边界：

```text
数据库最后一条线上质量事件：15:42:22
五轮新版服务启动：17:24:25
```

所以这些线上任务仍属于五轮部署前的数据。数据库中没有第 5 轮，不能用于否定刚部署的新合同。

线上布局总 Token 为 3,658,823。触发任务平均约 59,981 Token，最大 209,411 Token。

布局耗时：

| 指标 | 时间 |
|---|---:|
| 中位数 | 50.3 秒 |
| P95 | 150.5 秒 |
| 最大值 | 224.8 秒 |

质量平台整体：

| 指标 | 时间 |
|---|---:|
| 中位数 | 106.4 秒 |
| 平均 | 114.9 秒 |
| P95 | 224.8 秒 |
| 最大值 | 369.0 秒 |

## 九、BBox 问题构成和旧线上 rejected

旧线上 102 条任务共汇总 392 个布局 issue：

### 9.1 影响等级

| 等级 | 数量 |
|---|---:|
| must_repair | 186 |
| conditional_repair | 87 |
| record_only | 119 |

### 9.2 类型

| 类型 | 数量 |
|---|---:|
| label/shape overlap | 182 |
| text/formula overlap | 130 |
| frame overflow | 68 |
| container overflow | 8 |
| border | 4 |

这说明当前检测器不仅检查对象之间的重叠，也检查画面越界、容器溢出和边界风险。

旧线上 8 条 rejected 的主要形态：

- `10→1`：布局已显著改善，但机械字符串保护和后续轮次变差导致拒绝；
- `9→6`：无新增进展停止；
- `6→6`：代码相同或 runner error；
- `5→3`：改善但旧 degraded 门槛拒绝；
- `3→1`：改善但语义指纹合同拒绝；
- 其余多条 `3→3`、`2→2`：没有形成有效修改。

这些现象正是五轮、最佳候选保护和语义等价放宽需要解决的问题。

## 十、日志完整性审计

### 10.1 已经完整保存的内容

历史逻辑重放能够保存：

- Reviewer 输入和结构化结论；
- 原内容、正确内容、证据、代码位置、验证规则；
- Coder 工具调用；
- Verifier 输入、输出和引用；
- 修改前后代码与 diff；
- Token 和阶段耗时；
- 最终采用、拒绝或转人工原因。

历史与新版重叠重放能够保存：

- before 代码和初始 BBox；
- issue 影响等级、时间窗和对象；
- 每轮 prompt、SDK messages、diff；
- 每轮 compile/check 结果；
- 历史最佳候选；
- 最终候选路径；
- 轮次、Token、probe/recheck/总耗时。

### 10.2 当前仍存在的日志缺口

1. 最终三条逻辑定向重投有逐 case 结果，但缺统一批次 `summary.json`。
2. 最新两条线上 `candidate_ready` 的数据库摘要存在，但对应的完整 Reviewer/Coder/Verifier/diff 没有长期留存在本机目录，远端 debug artifacts 也为空。
3. 少数 `SIGTERM / V3 result missing` 只留下被截断的 SDK stdout。
4. 4 条 fail-open 中有 3 条是工作目录或产物路径 `FileNotFoundError`，没有完整 manifest。
5. 当前耗时主要记录大阶段，缺少每轮 SDK、compile、probe、静音 render、上传的统一拆分。
6. quality event 缺少明确统一的 `is_final_attempt`，报表必须自己按窗口函数去重。
7. 新版 50 条重叠专项重放证明了编译、BBox、diff 和最佳候选，但没有完成 50 条最终 MP4 的逐条人工视觉验收。

## 十一、平台运行与重试污染

### 11.1 当前运行态

取证时 server3：

- `mathpi-render`：active；
- 当前启动时间：2026-07-22 17:24:25；
- systemd `NRestarts=0`；
- health：healthy；
- RabbitMQ 实际运行于 Docker 容器 `mathpi-test-rabbitmq`；
- 两个队列 ready=0、unacked=0、consumers=4；
- consuming=true、inflight=0。

当前部署标记：

```text
deploy_head=2270964ba+93db536d6+server3-compatible-overlay
backup=/opt/mathpi/backups/v3_five_round_best_20260722_172422
```

运行态直接导入确认：

```text
max_rounds=5
no_progress_stop=2
same_signature_stop=2
token_hard_cap=9223372036854775807
```

即：最多五轮、连续两轮无进展才停、Token 只观测，不因平台估算预算拒绝候选。

### 11.2 MQ 重试情况

窗口内：

| 事件 | 原始行 | 涉及Job |
|---|---:|---:|
| retry published | 97 | 46 |
| redelivered | 21 | 10 |
| message received | 234 | 108 |
| processing started | 225 | — |
| processing finished | 205 | — |
| acked | 115 | — |

46 个发生重试的任务中：

| 重试事件数 | Job数 |
|---:|---:|
| 1 | 25 |
| 2 | 8 |
| 3 | 5 |
| 4 | 4 |
| 5 | 1 |
| 6 | 2 |
| 8 | 1 |

因此 raw event、raw traceback、raw timeout 都不能直接当任务数。

### 11.3 不能归因给逻辑/重叠 Agent 的错误

窗口内还存在：

- 任务超时 16 条，涉及 14 个 job；
- LLM request blocked 10 条，涉及约 4 个 job；
- 额度不足、无可用渠道等上游错误；
- 生成前段出现 `ease_out`、`ease_out_sine`、`decelerate` 未定义；
- journal 原始 `Traceback` 215 次。

真实任务终态只有 6 个 FAILED。215 次 traceback 可能来自同一异常的多行、多进程或重试打印，不能回答成“215个任务失败”，更不能归因成 Agent 修不好。

窗口内服务启动/停止各 26 次，但 `Main process exited=0`、`Failed with result=0`，主要是频繁部署和人工重启，不是 systemd 自发崩溃。当前队列已经恢复健康。

## 十二、问题根因分类

### 12.1 检测问题

- 逻辑 Reviewer 对历史样本存在改判，说明历史标签与当前合同不一致；
- BBox 仍可能把正常点名、同一 MathTex 内部结构或正常几何标注记成风险；
- 没有固定人工真值，无法计算真正的误报率和漏报率。

### 12.2 修复问题

- DuplicateRead 把正常的二次读取变成硬失败；
- 高密度场景一次包含几十个 issue，Agent 上下文和修改范围过大；
- 动态场景需要同时验证初态、过程和终态；
- 极端布局任务仍可能消耗数十万 Token 和十几分钟。

### 12.3 验收问题

- Verifier 过度绑定旧 source hunk，不能接受修复后的合理新行；
- 旧 degraded 阈值曾把明显改善候选退回原代码；
- 机械字符串保护曾把语义等价改写误判成删除；
- `candidate_ready` 和 BBox 清零尚未与人工真值统一校准。

### 12.4 数据与运行问题

- attempt 没有统一事实表，重试事件污染报表；
- 部分 SIGTERM、工作目录缺失导致证据链断裂；
- 部署期间频繁重启造成 retry consumer 暂时为零和 redelivery；
- 专项重放与线上事件没有统一 `source_batch/is_replay` 标识。

## 十三、建议的优化路线

### P0：把逻辑协议误杀清零

#### 方案

1. DuplicateRead 从硬异常改为告警，并直接返回第一次读取的缓存内容；
2. 保留重复读取次数，作为 Token/效率指标，不作为拒绝理由；
3. Verifier 证据允许引用实际 diff 新行、邻近替代行或结构化新值；
4. 证据绑定失败时转 `human_review/risk`，不得丢弃已编译候选；
5. 继续保持 fail-open，不把逻辑质量异常变成视频交付阻断。

#### 验收

- 重放已知 4 条 rejected；
- DuplicateRead 导致 rejected：0；
- Verifier 引用绑定导致候选丢失：0；
- 每条仍保留 Reviewer→Coder→Verifier→decision 完整日志；
- 人工确认候选没有引入新数学错误。

### P0：建立唯一 Agent attempt 事实层

建议建立事实表或统一物化视图，最小主键：

```text
job_id + attempt_id + stage + round
```

至少补充：

```text
is_final_attempt
is_replay
source_batch
source_code_hash
selected_candidate_hash
best_candidate_hash
before_issue_count
after_issue_count
decision_reason
```

每轮原子保存：

- issue 合同；
- Agent 原始输出；
- 代码 diff；
- compile/probe/verifier 结果；
- 当前候选和历史最佳 hash；
- 采用、保留风险或回退原因；
- Token 与阶段耗时。

#### 验收

- 100% 触发修复的任务可还原“问题→修改→验证→最终选择”；
- 100% fail-open 也有 manifest；
- 任意报表无需猜测哪个 attempt 是最终态；
- 重试不会重复计算 Token、成功率和失败数。

### P1：降低重叠 Agent 的成本和长尾

#### 方案

1. 当 must_repair 大于 10 时，按时间窗、画面区域和对象组拆成局部任务；
2. 一轮优先解决 1—3 组真实问题，修后立即局部复检；
3. 只剩 record_only/conditional 时允许停止并附风险；
4. 仍有 must_repair 且轮数未用尽时继续；
5. 继续保留历史最佳候选，后轮失败只放弃当前轮；
6. 细分记录 SDK、Read/Edit、compile、probe、render、upload；
7. 统计 Tex、场景、探针缓存命中率。

#### 性能目标

| 指标 | 目标 |
|---|---:|
| Layout P50 | <30 秒 |
| Layout P95 | <90 秒 |
| 整个平台 P50 | <75 秒 |
| Redelivery job率 | <1% |
| 每Job重试 P95 | ≤1 |

### P1：进一步降低正常几何关系误报

优先降为 record_only：

- 单字符点名与所属点/顶点；
- 圆周点名与所属圆；
- 点名与相邻短边；
- 同一 MathTex 内部结构；
- 同一几何对象内部的正常标注；
- 背景容器与其内部内容。

仍保持 must_repair：

- 文字与文字明显遮挡；
- 公式与说明文字互相遮挡；
- 内容真正超出画面；
- 非父子对象之间的大面积可见遮挡；
- 动态终态重新出现的遮挡。

### P1：五轮新版线上冒烟

当前缺口不是专项重放，而是部署后线上真实入口证据。

建议先发 10—20 条横屏真实任务，要求：

- 至少覆盖文字密集、几何动态、公式密集和边界风险；
- 每条确认 `source_head/deploy_head`；
- quality event 能看到真实轮数；
- candidate/residual 都有三态和逐轮 manifest；
- 不追求全部触发第5轮，只要求需要时能继续到第4/5轮；
- 不新增任何质量 hard gate。

### P2：建立固定人工金标集

建议固定 50—100 条样本，不再每轮随机换题。人工标注：

- 原代码是否真的有逻辑错误；
- 每个 BBox issue 是真问题还是正常关系；
- Agent 修改是否正确；
- 修复后是否引入新逻辑/布局问题；
- 三态视频哪一态最好；
- 人工最终应采用哪个候选。

逻辑指标：

- 真问题召回率；
- Reviewer 误报率；
- needs_repair 后候选形成率；
- 候选人工正确率；
- 新错误引入率；
- 单个有效修复 Token/时间。

重叠指标：

- 真重叠召回率；
- 正常关系误报率；
- BBox 改善率；
- 人工视觉改善率；
- 最佳候选采用率；
- 动态初态/过程/终态覆盖率；
- 单个有效修复 Token/时间。

## 十四、建议技术负责人现在做的决定

### 决定一：是否批准逻辑协议的最小修正

建议批准：DuplicateRead 改告警/缓存返回，Verifier 引用绑定失败转人工风险。这两个改动直接针对 33 条重放里 4 个 rejected 的主要根因，不需要改 Agent 主体能力。

### 决定二：是否先补事实层，再继续扩大随机批量

建议批准。当前继续增加随机任务会继续产生数据，但不会自然解决 attempt 重复、debug artifact 缺失和人工真值缺口。

### 决定三：是否把五轮新版定为“部署后冒烟阶段”

建议这样定义。专项困难集结果非常好，但部署后的线上随机样本仍为空；完成 10—20 条新线上冒烟和人工抽检后，再决定是否扩大批量。

## 十五、最终评价

### 逻辑 Agent

当前等级：**真实可用，但协议仍会误伤，尚不能宣称无人监督稳定率。**

- 能定位并修改真实数学错误；
- 修正日志合同后的历史困难集候选采用率为 71.4%；
- 最新旧线上入口 needs_repair 候选接受率为 80%；
- 最终定向补跑唯一 needs_repair 样本 1/1 成功；
- 当前最大问题是 DuplicateRead、Verifier 证据绑定和人工真值缺失。

### 重叠 Agent

当前等级：**新版专项重放已经达到部署后线上冒烟条件。**

- 29/29 触发样本改善；
- 26/29 清零；
- 3 条保留残留最佳候选；
- 0 条改善后回原代码；
- 第4、5轮真实生效；
- 仍缺逐条最终 MP4 人工验收和部署后线上任务验证。

### 整个平台

当前等级：**能力已被证明，下一步应优化事实层、协议和长尾成本，而不是继续用单一通过率评价。**

可以确认：

- V3 真正在运行；
- fail-open 生效，质量异常不会阻断可播放结果；
- 五轮和 Token 仅观测合同已在当前运行态生效；
- 逻辑和重叠 Agent 都能产生真实有效候选；
- 当前服务和 RabbitMQ 队列健康。

不能宣称：

- 逻辑 Agent 已达到整体 90% 或 100% 修复率；
- BBox 清零等于视频视觉绝对正确；
- `candidate_ready` 等于老师确认数学正确；
- 102 个 SUCCESS 等于 Agent 成功修复 102 次；
- 五轮新版已经通过部署后随机线上任务长期验证。

最值得优先做的不是更换模型，而是：

> 先去掉确定的协议误杀，保证每次修复证据完整、报表口径唯一；再用固定人工金标集衡量真实效果；最后针对高密度布局场景优化 Token 和长尾耗时。
