# render-claude-agent-sdk

这是 MathPi 当前使用的**完整 Claude Agent SDK V3 视频质量模块**的独立仓库。

它不是视频生成器，也不是另一套渲染服务。它接收一份已经能够交给 Manim 的代码，依次做数学逻辑检查、逻辑修复、画面重叠检查、重叠修复和结果留存，然后把最合适的代码交还给宿主系统。

## 一句话理解

```text
已有 Manim 代码
→ 先渲染出基线
→ Claude 检查数学逻辑并按需修复
→ 检查文字、公式和图形重叠并按需修复
→ 再次渲染确认
→ 输出最终代码、视频和完整证据
```

普通质量问题默认只修复、记录或提示，不应该因为一次模型判断就丢掉原本可播放的视频。支付、权限、安全合规和宿主系统的运行安全仍由宿主系统负责。

## 这是不是完整 V3

是。本仓库的核心来源固定为：

```text
apps/render/manim_quality_platform/v3
```

原始交接包标识为：

```text
manim_quality_complete_handoff_20260715_v3
```

仓库没有把 MathPi 中较早的 `sdk_review.py`、`pre_archive.py`，也没有把普通渲染器误当成完整 V3。原始 `MANIFEST.json` 登记的 650 个文件全部保留，缺失数为 0；同时包含 7 月 15 日之后已经在 server3 实跑验证过的兼容和稳定性修正。详细来源见 [SOURCE_SNAPSHOT.md](SOURCE_SNAPSHOT.md)。

## 它具体会做什么

1. **基线渲染**：先确认输入代码能否真实运行，保留原始可播放版本。
2. **数学逻辑检查**：结合题目、参考答案、代码和渲染证据检查数学表达是否合理。
3. **数学逻辑修复**：只有发现值得修复的问题时才生成候选代码，并重新验证。
4. **画面重叠检查**：检查文字、公式、图形、边界和容器之间的持续性遮挡。
5. **画面重叠修复**：自动调整布局，再用独立探针复查，不只相信模型自述。
6. **确定性收尾**：比较原版和修复版，保存最终代码、视频、JSON 报告和运行日志。

## 目录怎么读

| 目录 | 内容 |
|---|---|
| `src/manim_quality/` | V3 核心领域代码和编排逻辑 |
| `.vendor/quality_repair/` | 冻结的重叠修复能力及来源校验 |
| `external/layout_probe/` | 独立布局探针，用于复核重叠问题 |
| `evals/` | 逻辑、重叠和全流程评测 Harness |
| `scripts/run_existing_code_e2e.py` | 最重要的“已有代码全流程”入口 |
| `handoff_data/` | 可以直接运行的最小样例和负载数据 |
| `tests/` | 单元、集成、端到端和安全边界测试 |
| `integrations/mathpi/` | MathPi 当前 Docker/事件/留存适配层，不属于 V3 核心 |
| `docs/reports/` | server3 真实批量测试统计 |

## 快速开始

建议使用 Python 3.11：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config.env.example config.env
```

在 `config.env` 中填写自己的 Claude Agent SDK 配置。不要提交真实 API Key。

先做环境检查：

```bash
python scripts/handoff_doctor.py --help
python scripts/check_engineering_standards.py
python scripts/verify_vendor_sources.py
```

运行自带的已有代码样例：

```bash
python scripts/run_existing_code_e2e.py \
  --sample-dir handoff_data/existing_code_real \
  --output-dir runs/existing-code-sample \
  --manim-python /path/to/manim/python
```

`--manim-python` 必须指向已经安装 Manim、`manim_voiceover` 和项目所需自定义服务的 Python。完整参数以 `--help` 为准。

## 如何判断一次运行成功

不要只看进程退出码。一次完整运行至少应该留下：

- 原始代码和基线渲染结果；
- 逻辑审查结果，以及是否生成、采用或拒绝逻辑修复候选；
- 重叠检测前后问题数量和分类；
- 每轮修复代码、渲染结果及外部复查证据；
- 最终采用的代码、视频和完整 JSON 报告。

如果接入 MathPi，还应看到质量事件：

```text
event_type = pre_archive_quality_platform_completed
source_head = manim_quality_complete_handoff_20260715_v3
```

## MathPi 如何接入

当前适配代码放在 [integrations/mathpi/README.md](integrations/mathpi/README.md)，真实顺序是：

```text
minimal_bridge.py
→ v3_runner.py
→ run_existing_code_e2e.py
→ Logic 检查与修复
→ Layout 检查与修复
→ retention.py 留存证据
```

独立 V3 不依赖 MathPi 数据库、RabbitMQ、COS 或 Docker；这些由宿主适配层提供。

## 今晚 V1 测试报告

今晚的 110 个 server3 任务已经冻结为 V1：

- 108 个成功，2 个失败，总体成功率 98.2%；
- 108 个成功视频全部完成 STT；
- 几何批次重叠问题从 113 降到 49；
- 多主题批次重叠问题从 212 降到 62；
- 报告明确区分生成/运行时失败、V3 修复效果和 STT 人工复核线索。

完整报告见 [docs/reports/2026-07-18-server3-v1.md](docs/reports/2026-07-18-server3-v1.md)。下次测试新增 V2，不覆盖 V1。

## 开发与验证

```bash
python -m pytest -q
python scripts/check_engineering_standards.py
python scripts/verify_vendor_sources.py
```

独立发布时的真实验证结果为 `1371 passed, 10 failed`。剩余失败来自当前 V3 已存在的旧断言、旧 Hash 基线和测试路径问题；本次没有为了制造“全绿”而回退已经在 server3 验证过的修复。分类和复现结论见 [独立仓库验证记录](docs/reports/2026-07-18-independent-repo-verification.md)。

修改前请先阅读 [AGENTS.md](AGENTS.md)。原始 V3 README 保存在 [docs/original/README_V3_ORIGINAL.md](docs/original/README_V3_ORIGINAL.md)，便于核对最初交接语义。

## 安全边界

- 不提交 API Key、数据库密码、Cookie、Token 或真实 `.env`。
- 不把模型输出直接当作最终事实，修复代码必须重新渲染和复查。
- 不把普通质量检查升级成宿主系统的硬拦截。
- 不用测试替身冒充真实 SDK、真实 Manim 或真实 server3 运行证据。
