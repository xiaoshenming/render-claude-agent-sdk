# render-claude-agent-sdk

这是一个专门检查和修复 **Manim 教学视频代码**的 Agent 质量系统。

它位于“代码已经生成”与“视频最终归档”之间：先保住一份能够播放的原始版本，再让不同职责的 Agent 分别检查数学逻辑和画面布局。每次修改都必须重新渲染、重新检测，并留下可以追溯的证据。

这个仓库保存的是 MathPi 当前完整的 Claude Agent SDK V3 模块，不是早期的单次 SDK 审查脚本，也不是生成 Manim 代码的 LLM 管线。

## 2026-07-23 当前快照

本仓库已同步 MathPi `dev-PB8` 当前 V3 源码、Harness、测试和 MathPi 接入快照。除既有五轮重叠修复外，本次新增并在 server3 使用真实逻辑错误源码验证：

- 重叠修复最多 5 轮的单一运行参数；
- 连续 2 轮无进展才停止；
- Token 只观测，不因平台预算估算差异丢弃候选；
- 每轮复检与 Agent 编排耗时证据；
- 逻辑修复历史最佳候选保护；
- Coder 临时 SDK/结构化输出错误自动重试；
- Coder 12 turn、Verifier 8 turn、总工具调用 64 的软预算；
- Verifier 直接验收完整候选源码；
- Verifier 对每个 Issue 分别输出 `resolved / unresolved / unknown`；
- 行号、引用和最终说明格式只作为风险证据，不再机械清空已生成候选；
- `SUCCESS_DEGRADED` 返回残留候选和风险；
- 语义等价字符串不再机械回滚；
- 拆分式布局探针加载；
- MathPi 三态代码、视频和 diff 接入快照；
- 逻辑 Reviewer、Coder、Verifier 的完整调试证据合同。

server3 同类困难源码重放结果：

| 模块 | 结果 | 边界 |
|---|---:|---|
| 逻辑 Agent（本次6条真实错误源码） | 4 条逐项确认，2 条保留风险候选，0 条恢复原错误代码 | 2 条复杂候选尚未完成最终视频人工验收 |
| 重叠 Agent | 29 条触发任务全部改善，26 条清零，3 条保留残留最佳候选 | BBox/代码复检结果，不是全部 MP4 人工验收 |

技术负责人应先阅读：

- [`docs/INDEX.md`](docs/INDEX.md)：持续维护的代码、Harness、合同、验证和报告总索引；
- [`docs/reports/2026-07-23-逻辑Agent软合同与错误样本重放报告.md`](docs/reports/2026-07-23-逻辑Agent软合同与错误样本重放报告.md)：本次实现、真实样本、Token、耗时和回滚点；
- [`docs/reports/2026-07-22-Agent技术改造点对点功能审计.md`](docs/reports/2026-07-22-Agent技术改造点对点功能审计.md)：13 个可直接建工单的技术改造点；
- [`docs/reports/2026-07-22-server3-Agent全量日志审计及优化建议.md`](docs/reports/2026-07-22-server3-Agent全量日志审计及优化建议.md)：真实批次、Token、耗时、失败根因和证据边界。

当前最明确的后续工作是建立更大的人工金标错误源码集，并对复杂 `candidate_risk` 候选补做真实渲染和三态人工验收。所有质量异常继续保留证据并 fail-open，不作为 MathPi 视频交付的新增硬拦截。

## 先用一分钟理解整个系统

普通的“让 AI 检查并修改代码”有三个隐患：

1. AI 可能判断错了，却非常肯定地说自己修好了。
2. 修复一个问题时，可能又制造新的逻辑错误或画面重叠。
3. 任务失败后，如果没有版本和证据，很难知道改了什么、为什么采用这个版本。

这个项目的解决办法是：**Agent 只负责理解问题和提出修改，Harness 负责限制、执行、复查、回滚和记录。**

```text
题目、参考答案、Manim 代码、渲染环境
                    │
                    ▼
            ① 渲染原始基线视频
                    │
                    ▼
          ② Logic Reviewer 检查逻辑
              │              │
           没问题          有明确问题
              │              ▼
              │       ③ Logic Coder 修复
              │              │
              │       重新渲染并独立验证
              └───────┬──────┘
                      ▼
             ④ 全量画面重叠检测
              │              │
           没问题          有可修问题
              │              ▼
              │       ⑤ Overlap Coder 修复
              │              │
              │       重新渲染并外部复查
              └───────┬──────┘
                      ▼
          ⑥ 选择最合适版本并保存全部证据
                      │
                      ▼
             返回最终代码、视频和报告
```

最重要的一点：**Agent 不能给自己的修改判定通过。** 它说“已修复”只能算一个候选结果，必须由 Agent 会话之外的渲染器、检测器和规则再次确认。

## 项目负责什么，不负责什么

### 本项目负责

- 理解题目、参考答案和 Manim 代码之间是否存在明显逻辑矛盾；
- 找出错误结论、公式关系、几何关系和教学表达风险；
- 在限定范围内生成逻辑修复候选；
- 检测文字、公式、图形、容器和画面边界之间的布局问题；
- 在不改变数学含义的前提下生成布局修复候选；
- 对每个候选重新渲染、复查、比较和回滚；
- 记录模型、Token、耗时、工具调用、代码差异和检测结果；
- 向 MathPi 或其他宿主系统返回最终版本和结构化证据。

### 本项目不负责

- 不负责从用户问题生成第一版 Manim 代码；
- 不替代 Manim、FFmpeg、TTS 或 Docker 渲染环境；
- 不负责消息队列、数据库、对象存储、积分和用户权限；
- 不负责内容安全审核；
- 不保证所有开放式数学问题都能被程序绝对证明；
- 不把“视频更华丽、节奏更好、口播更自然”混入逻辑或重叠修复职责；
- 不包含 STT 检测模块。MathPi 中的 STT 是视频完成后的独立旁路模块。

换句话说，它是一个可以被不同视频系统接入的**独立质量核心**，宿主系统负责业务和基础设施。

## 系统里有哪些角色

这个项目不是“一个无所不能的大 Agent”，而是多个职责隔离的角色，加上一套不依赖模型自觉的 Harness。

| 角色 | 类型 | 主要工作 | 明确不能做的事 |
|---|---|---|---|
| Logic Reviewer | 只读 Agent | 阅读题目、答案、代码和证据，发现数学与教学逻辑问题 | 不能改代码，不能决定最终采用哪个版本 |
| Logic Coder | 修改 Agent | 根据已经冻结的问题和修改范围修复代码 | 不能扩大修改范围，不能宣布自己通过 |
| Logic Verifier | 只读 Agent | 当程序规则不足时，定向复核某一处逻辑修改 | 不重新自由审查整份代码，不改代码 |
| Overlap Detector | 确定性工具 | 从渲染结果提取越界、遮挡、持续碰撞等事实 | 不调用模型，不修改代码 |
| Overlap Coder | 修改 Agent | 根据布局事实调整位置、间距、容器和排版 | 不能改变公式、答案或几何含义 |
| External Layout Probe | 外部检测器 | 在 Agent 会话之外重新检查修复后的画面 | 不相信 Agent 的自述，不负责修改 |
| Quality Orchestrator | 编排器 | 控制顺序、版本、预算、渲染、采用、拒绝和回滚 | 不做开放式数学推理，不自由改代码 |
| Evidence / Retention | 证据层 | 保存代码、视频、报告、Hash、Token 和每轮结果 | 不参与质量判断 |

### 为什么一定要分开

Reviewer 擅长发现问题，Coder 擅长修改，但“提出修改”和“验收修改”如果由同一个会话完成，就容易出现自我证明。角色隔离后，每个 Agent 只看到完成自己职责所需的信息，既降低上下文污染，也减少 Token 浪费。

## 一次任务从头到尾发生什么

下面是一条真实任务进入 V3 后的完整过程。

### 第 0 步：宿主系统准备输入

V3 至少需要：

- 用户题目或知识点；
- 当前 Manim 源代码；
- 可用的参考答案或预期解法；
- 能够运行该代码的 Manim Python；
- 当前任务标识和输出目录。

如果没有参考答案，可以明确传空内容，但不能由系统悄悄伪造一个“标准答案”。

### 第 1 步：建立原始基线

Harness 首先渲染原始代码。只有真实渲染成功，后面的逻辑和布局检查才有可靠基准。

基线会绑定：

- 原始代码 Hash；
- Scene 和切片信息；
- 渲染配置及渲染器版本；
- 基线视频和相关证据。

后面的任何修复失败，都可以回到这份基线，不会把已经能播放的版本直接覆盖掉。

### 第 2 步：Logic Reviewer 全量逻辑审查

Logic Reviewer 是只读 Agent。它会结合题目、参考答案、代码结构、文本公式和可提取的几何事实进行检查。

它主要关注：

- 结论是否与题目冲突；
- 推导过程是否前后矛盾；
- 公式、数值、符号和单位是否一致；
- 点、线、角、坐标和几何构造是否表达了正确关系；
- 动画展示的内容是否与讲解文字一致；
- 是否存在高风险但无法可靠判断的地方。

Reviewer 输出结构化结果，而不是一句随意的“看起来没问题”：

- `PASS`：没有发现有直接证据支持的问题；
- `REPAIR`：问题明确、范围可控，可以尝试修复；
- `RECORD_ONLY`：低风险观察项，只记录；
- `HUMAN_REVIEW`：风险较高或证据冲突，需要人工或重新生成。

这里的 `PASS` 只代表“本次审查没有发现问题”，不等于数学上的绝对证明。

### 第 3 步：Logic Coder 条件修复

只有 Reviewer 给出明确问题时，Logic Coder 才会启动。它拿到的不是 Reviewer 的全部自由推理过程，而是一份已经冻结的问题合同：

- 错误在哪里；
- 为什么认为它有问题；
- 允许修改哪些 Scene 或代码区块；
- 哪些内容绝对不能动；
- 修复后应满足什么条件。

Coder 完成修改后，Harness 会在 Agent 外部依次检查：

1. 修改是否超出允许范围；
2. Python 是否能编译；
3. 受影响的 Scene 是否能重新渲染；
4. 可计算的公式、几何和数值关系是否通过；
5. 修改是否制造新的高风险内容。

如果确定性规则不足，才启动独立的 Logic Verifier，对这一个问题和这一个差异做定向复核。

修复不是无限循环。相同补丁、相同错误、没有改善、越权或预算耗尽都会停止继续调用 Agent。

### 第 4 步：全量重叠检测

逻辑阶段确定版本后，系统才进行完整布局检查。顺序不能颠倒，因为逻辑修复可能改变公式、文字或图形，从而产生新的重叠。

检测器检查的不只是“两个框碰到了”，还会结合：

- 对象在画面中的实际边界；
- 碰撞发生的时间长度；
- 对象是文字、公式、图形还是容器；
- 是否只是正常包含、刻意接触或短暂动画过渡；
- 是否超出安全画面；
- 是否真正影响阅读。

因此，检测结果可以区分需要修复的问题和正常视觉关系，避免盲目追求“所有重叠数字必须清零”。

### 第 5 步：Overlap Coder 条件修复

只有检测到值得处理的布局问题时，Overlap Coder 才启动。它通常会得到：

- 完整 Manim 代码；
- 精简后的布局问题列表；
- 对象、时间区间和画面位置；
- 当前逻辑证书摘要；
- 上一轮修改与复查结果。

它可以调整位置、间距、缩放、换行和容器布局，但不能为了消除重叠删除教学内容，也不能改变公式、答案、几何坐标关系或动画含义。

修改后由外部渲染器重新渲染，再由独立 Layout Probe 完整复查。Harness 会比较修复前后的问题数量、严重度和持续时间：

- 明显改善：保留为候选；
- 已清除：采用修复版本；
- 没有变化或变差：拒绝候选并回滚；
- 只剩低风险或疑似误判：按宿主策略记录 warning；
- 修改触碰数学语义：布局证据作废，重新回到逻辑检查。

### 第 6 步：选择最终版本

最终采用权属于 Harness 和宿主策略，不属于 Agent。

独立 V3 的平台设计支持严格认证、等待人工或重新生成；MathPi 当前接入为了不让普通质量判断拦截已有视频，使用 fail-open 集成策略：能确认的修复就采用，无法确认时保留最后一份可播放版本并记录 warning。安全合规、支付权限和不可执行的运行安全底线仍由宿主系统单独处理。

### 第 7 步：保存完整证据

一次运行不会只留下一个最终 `candidate.py`。系统还会保存：

- 输入题目、参考答案和原始代码；
- 每一轮候选代码及父版本；
- 每次代码差异和修改范围；
- 基线与修复后的渲染结果；
- 逻辑审查、逻辑修复和定向验证结果；
- 重叠检测前后问题及分类；
- Agent SDK 的结构化消息、工具调用和错误；
- 输入、输出、缓存 Token 与耗时；
- 最终采用或拒绝某个版本的原因；
- 代码、视频、配置和证据 Hash。

这让每个结果都能回答三个问题：**Agent 做了什么、系统为什么相信或拒绝它、最终视频到底来自哪份代码。**

## Harness 到底是什么

Claude Agent SDK 提供的是模型会话、工具和执行能力。Harness 是包在 SDK 外面的一整套工程控制层。

可以把它拆成六部分理解：

### 1. 输入合同

明确每个 Agent 能看到什么、必须输出什么。输出采用结构化 Schema，避免靠自然语言猜测状态。

### 2. 工具与路径权限

Reviewer 只能读；Coder 只能在当前任务工作区内读取和编辑允许的文件。默认不开放 Bash、网络、任意写入、仓库探索和上传能力。

### 3. 预算控制

统一限制最大轮数、工具调用、运行时间、上下文大小、Token 和修复次数。预算是代码策略，不是提示词里一句“请节约”。

### 4. 版本和检查点

原始基线、逻辑认证版、布局认证版和最终交付版分别保存。每次修改创建子版本，不原地覆盖已确认版本。

### 5. 外部验证和回滚

Agent 只能提出候选；编译、渲染、公式验证、重叠复查、语义范围检查都在会话外执行。失败候选直接拒绝，回到最近的可靠检查点。

### 6. 观测和评测

记录每个角色的成功率、修复率、误改率、Token、耗时和失败原因，并通过冻结测试集与真实批次判断新版本究竟改善还是退化。

## 为什么要保存 Revision 和 Hash

如果只保存“最终代码”和“最终视频”，很容易出现代码是新版、视频却来自旧版，或者检测报告检查的是另一个版本。

V3 为每次修改建立不可变 Revision，并把这些内容绑定在一起：

```text
revision_id
├── parent_revision_id
├── code_hash
├── semantic_fingerprint
├── Scene / slice hashes
├── render configuration
├── renderer version
├── logic evidence
├── layout evidence
└── video hash
```

普通文件 Hash 只能证明文件是否相同。`semantic_fingerprint` 还会关注公式、文字、坐标、对象关系、动画顺序和控制逻辑，用来判断一个“布局修改”是否偷偷改变了数学含义。

## 失败时系统怎么处理

| 情况 | 系统行为 |
|---|---|
| Agent 没返回有效结构 | 记录失败，不把它当作 PASS |
| 修改后无法编译或渲染 | 拒绝候选，回到上一个可播放版本 |
| 修改超出允许 Scene | 拒绝候选并记录越权原因 |
| 重叠修复改变数学语义 | 作废布局候选，重新进入逻辑检查或回滚 |
| 连续生成相同补丁 | 熔断，避免浪费 Token |
| 指标没有改善或变差 | 停止继续修复，保留可靠版本 |
| SDK、渲染器或探针异常 | 保存完整错误，由宿主策略决定重试或 fail-open |
| 旧任务晚于新任务返回 | 依靠 revision 和任务标识拒绝旧结果覆盖新结果 |

## Harness 如何防止“只对几个案例有效”

项目内置多层测试和评测：

- 单元测试：检查合同、权限、预算、分类和状态转换；
- 集成测试：检查 SDK adapter、逻辑修复和重叠修复如何连接；
- 端到端测试：从已有代码一直跑到最终候选和证据；
- known-good 集：观察误报和不必要修改；
- known-bad 集：观察问题召回与修复成功率；
- overlap holdout：观察重叠检测和修复效果；
- failure injection：模拟超时、重复任务、旧 Worker、上传异常和回滚；
- 真实 server3 批次：确认代码不是只在测试替身中成立。

新增规则不能根据题目标题、案例编号或某段固定文本做特判。每条规则都应该有通用依据、反例、测试样本和冻结留出集结果。

## 在 MathPi 中的真实位置

MathPi 当前主管线可以简化成：

```text
用户提交题目
→ LLM 生成 Manim 代码
→ Render Agent / 运行时修复让代码可渲染
→ 生成一份可播放视频和最终候选代码
→ 完整 V3 Logic 检查与修复
→ 完整 V3 Layout 检查与修复
→ 保存质量事件和证据
→ STT 独立旁路检测口播风险
→ 上传、归档并在管理端展示
```

其中本仓库负责的是中间的 V3 质量模块。MathPi 的连接顺序是：

```text
minimal_bridge.py
→ v3_runner.py
→ scripts/run_existing_code_e2e.py
→ Logic 全流程
→ Layout 全流程
→ retention.py
```

适配层位于 `integrations/mathpi/`。它负责把 MathPi Docker Manim、任务信息和质量事件转换为 V3 能理解的输入输出，不会让 V3 核心反向依赖 MathPi 数据库或队列。

线上判断完整 V3 是否真的运行，必须查看：

```text
event_type = pre_archive_quality_platform_completed
source_head = manim_quality_complete_handoff_20260715_v3
```

只看到 `sdk_review.py`、普通渲染日志或某个配置开关，不能证明 Logic 与 Layout 全流程真的执行过。

## 仓库结构

| 路径 | 用途 |
|---|---|
| `src/manim_quality/agents/` | Claude Agent SDK 会话、角色、权限、预算和 Token 记录 |
| `src/manim_quality/logic/` | 逻辑审查、逻辑修复、定向验证和证据模型 |
| `src/manim_quality/layout/` | 重叠分类、修复适配、复查和残留风险策略 |
| `src/manim_quality/orchestrator/` | 状态机、阶段顺序、检查点、回滚和交付编排 |
| `src/manim_quality/rendering/` | 渲染接口、受影响 Scene 计算和渲染清单 |
| `src/manim_quality/revisions/` | Revision、Hash 和语义指纹 |
| `src/manim_quality/storage/` | 任务、证据、制品和状态持久化 |
| `src/manim_quality/observability/` | 审计、指标、告警和使用量记录 |
| `.vendor/quality_repair/` | 冻结的重叠修复实现及来源校验 |
| `external/layout_probe/` | Agent 外部的独立布局复查探针 |
| `evals/` | 逻辑、布局和完整工作台评测 Harness |
| `tests/` | 单元、集成、端到端和故障注入测试 |
| `handoff_data/` | 可直接运行的最小题目、答案和代码样例 |
| `integrations/mathpi/` | MathPi Docker、质量事件和留存适配层 |
| `docs/` | 架构、Harness、实验、交接和真实测试报告 |

## 这是不是完整 V3

是。独立核心固定来自 MathPi：

```text
apps/render/manim_quality_platform/v3
```

原始交接包标识：

```text
manim_quality_complete_handoff_20260715_v3
```

原始 `MANIFEST.json` 登记的 650 个文件全部保留，缺失数为 0。仓库同时包含 7 月 15 日以后已经在 server3 验证过的兼容和稳定性修正。

这里没有把以下内容误认为完整 V3：

- 早期单次 `sdk_review.py`；
- 归档桥 `pre_archive.py`；
- 普通 Manim 渲染器；
- 上游第一版代码生成流程；
- 独立的 STT 检测模块。

完整来源、原始 Hash 和当前快照差异见 [SOURCE_SNAPSHOT.md](SOURCE_SNAPSHOT.md)。

## 快速开始

### 1. 安装

建议使用 Python 3.11：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config.env.example config.env
```

在本地 `config.env` 中填写自己的 Claude Agent SDK 配置。不要把真实 API Key 提交到 Git。

### 2. 检查命令参数

```bash
python scripts/handoff_doctor.py --help
python scripts/run_existing_code_e2e.py --help
```

### 3. 运行自带样例

```bash
python scripts/run_existing_code_e2e.py \
  --code handoff_data/existing_code_real/candidate.py \
  --problem handoff_data/existing_code_real/problem.txt \
  --expected-solution handoff_data/existing_code_real/expected_solution.txt \
  --output runs/existing-code-sample \
  --manim-python /path/to/manim/python
```

`--manim-python` 必须指向已经具备目标代码依赖的环境，例如 Manim、`manim_voiceover` 和需要的自定义 TTS 服务。

### 4. 运行测试与工程检查

```bash
python -m pytest -q
python scripts/check_engineering_standards.py
python scripts/verify_vendor_sources.py
```

2026-07-23 逻辑软合同核心切片为 `43 passed`，工程行数检查通过。旧的 `test_eval_runtime_policy.py` 仍调用已删除的私有 `_geometry_snapshot`，属于历史测试兼容问题，不计入本次功能通过数。2026-07-22 全量历史套件记录仍为 `1424 passed, 34 failed, 12 errors`；未通过项集中在旧测试拆分包装、冻结来源 Hash 和历史存储测试基线，不应被包装成“全绿”，也不应据此回退已经在 server3 验证的 V3 修复。详细历史分类见 [独立仓库验证记录](docs/reports/2026-07-18-independent-repo-verification.md)。

## 如何判断一次运行真的完整

不能只看命令是否退出，也不能只看 Agent 最后说了什么。至少应确认：

- 原始代码真实渲染成功；
- Logic Reviewer 有独立运行记录；
- 命中逻辑问题时，存在修复候选和修复后验证；
- 最终逻辑版本执行了重叠检测；
- 命中布局问题时，存在修复前后代码、视频和外部复查；
- 最终采用的代码、视频和报告绑定同一 Revision；
- Token、耗时、工具调用和失败原因都有记录；
- MathPi 质量事件包含正确的 `source_head`。

如果缺少其中任何一段，只能说明某个局部组件运行过，不能称为完整 V3 全流程。

## 当前真实批量结果

2026-07-18 的 server3 V1 批次共 110 个任务：

- 108 个成功，2 个失败，总成功率 98.2%；
- 108 个成功视频全部完成后续 STT；
- 几何批次重叠问题从 113 降到 49；
- 多主题批次重叠问题从 212 降到 62；
- 失败原因、Logic 结果、Layout 修复和 STT 线索已分别统计，没有混成一个成功率。

完整数据见 [server3 V3 与 STT 测试统计 V1](docs/reports/2026-07-18-server3-v1.md)。后续测试新增 V2，不覆盖 V1。

## 继续开发前先读什么

建议顺序：

1. [AGENTS.md](AGENTS.md)：不可破坏的 Agent 与 Harness 工程规则；
2. [质量平台架构](docs/architecture/QUALITY_PLATFORM.md)：完整状态机和角色设计；
3. [Harness 工程规范](docs/engineering/HARNESS.md)：权限、预算、证据和验收边界；
4. [MathPi 接入说明](integrations/mathpi/README.md)：当前宿主适配方式；
5. [原始 V3 README](docs/original/README_V3_ORIGINAL.md)：最初交接语义。

## 安全与质量底线

- 不提交 API Key、Token、数据库密码、Cookie、真实 `.env` 或用户数据；
- 不允许 Agent 访问任务工作区之外的文件；
- 不把 Agent 的“已修复”当成通过证据；
- 不让失败候选覆盖已经能播放的版本；
- 不用删除内容、隐藏对象或样本特判换取检测数字变好；
- 不把普通逻辑或重叠风险直接升级成 MathPi 主管线硬拦截；
- 不用测试替身冒充真实 SDK、真实 Manim 或真实 server3 证据。

这个系统追求的不是让 Agent 看起来聪明，而是让每一次自动检查和修改都**可限制、可复查、可回滚、可解释、可量化**。
