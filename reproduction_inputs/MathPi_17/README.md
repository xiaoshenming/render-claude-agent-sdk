# MathPi 17题原始错误代码 Read/Edit 修复交接包

## 1. 交接目标

这是一份可独立复制给同事的离线回归包，用于让同一模型或其他模型在
17份真实错误 Manim 源码上运行单 Agent `Read + Edit` 修复，并生成
480P/15fps静音预览。

包内 `cases/*/source/main.py` 全部是 GPT-5.6 修复前的原始错误代码，
不是修复后候选。原件只读保留；运行脚本会把它们复制到 `runs/RUN_ID/`
后再交给 Agent 编辑。

## 2. 目录

```text
.
├── README.md
├── .env.example
├── requirements.txt
├── manifest.source.json
├── manifest.source.csv
├── MANIFEST.sha256
├── source-provenance.json
├── cases/
│   └── <17个题目目录>/
│       ├── source/
│       │   ├── main.py
│       │   ├── record.json
│       │   ├── message1.txt
│       │   ├── message2.txt
│       │   ├── llm_raw.txt
│       │   └── original_render.log
│       └── assets/
│           ├── reference_bg_02.png
│           └── logo_text_trim.png
├── shared/assets/
├── reference/
│   ├── 17题完整issues基准报告.md
│   ├── 四题生命周期人工诊断.md
│   ├── GPT5.6本轮修复点对点审计.md
│   └── PROVENANCE-NOTE.md
├── scripts/
│   ├── run_read_edit_batch.py
│   ├── preview_entry_480p.py
│   ├── render_480p_silent.sh
│   └── verify_package.sh
└── runs/
```

## 3. 原始性与安全边界

- 17份原始 `main.py` 均来自
  `8797几何量化问题代码_17题_20260724`。
- `MANIFEST.sha256`覆盖包内固定输入和脚本，不覆盖运行后产生的`runs/`。
- 旧`record.json.code_sha256`与当前实际`main.py`均不一致；原因与双哈希
  明细见`source-provenance.json`及`reference/PROVENANCE-NOTE.md`。
- 包内没有API Key、Token、`.env`真实值或服务端凭据。
- Agent只允许`Read/Edit`，明确禁用`Agent/Task/Bash/Write/Web`。
- 每题使用独立工作目录。
- 运行后检查修改只能发生在`class Solution`。
- 不包含阻断生产任务的质量gate；这是离线修复与证据包。

验证交接包：

```bash
bash scripts/verify_package.sh
```

## 4. 环境

已验证环境：

- Python 3.11/3.13
- `claude-agent-sdk 0.2.110`
- Docker
- `docker-manim-worker-tts:font-ready`
- FFmpeg / ffprobe

安装SDK：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果项目仓库已经固定`claude-agent-sdk >=0.2.115,<0.3`，优先使用项目锁定版本，
但要把SDK版本写入最终报告。

## 5. 配置模型

不要把真实Key写进脚本、README、Git或压缩包。

```bash
export ANTHROPIC_BASE_URL='https://your-gateway.example'
export ANTHROPIC_API_KEY='your-own-key'
export QUALITY_MODEL='gpt-5.6-sol'
export REPAIR_WORKERS='8'
```

`ANTHROPIC_BASE_URL`必须是Claude Agent SDK可调用的Anthropic Messages兼容网关。
模型名必须通过`QUALITY_MODEL`传入SDK的`model=`。

## 6. 运行17题Read/Edit修复

```bash
python scripts/run_read_edit_batch.py \
  --run-id colleague-gpt56-run1 \
  --model gpt-5.6-sol \
  --workers 8
```

每题输出：

- `candidate.py`：模型修改后的完整源码；
- `record.json`：题目元数据；
- `assets/`：背景和Logo；
- `changes.diff`：原始代码与候选代码差异；
- `result.json`：模型、Token、成本、轮次、Read/Edit完整时间线和错误。

根输出：

```text
runs/colleague-gpt56-run1/summary.json
```

## 7. 生成480P静音预览

```bash
chmod +x scripts/render_480p_silent.sh
bash scripts/render_480p_silent.sh colleague-gpt56-run1 6
```

渲染规格：

- 854×480；
- 15fps；
- CosyVoice不可用时允许生成静音MP3；
- 仅用于快速检查动画与几何，不冒充真实TTS验收。

每题输出：

- `preview_480p/**/Solution.mp4`
- `render_480p.log`
- `ffprobe.json`

## 8. 验收口径

至少分五层，不能只看退出码：

1. Agent调用成功，只有Read/Edit。
2. 修改范围只在`class Solution`。
3. AST和`py_compile`通过。
4. Manim完整渲染，ffprobe确认为854×480、15fps。
5. 按基准问题逐条核对关键帧和源码因果链。

已有29个基准问题的最新核对结果：

- 24项在上一轮GPT-5.6候选中得到修复；
- 1项部分修复；
- 4项未修复。

重点回归：

- `035`：阶段后建边/填充必须加入owner group；
- `042`：`edge_AF`及临时AF对象必须有入场与退出归属；
- `047`：动画参数中的内联`Line(...)`不能成为孤儿对象；
- `054`：BP/CD临时强调线必须归属第一阶段owner；
- `099`：核对`arc_BAD/arc_CAD`射线顺序；
- `117`：AE/AD必须分别归属两个阶段owner。

详细证据见`reference/`。

## 9. 报告要求

同事每次运行至少提交：

- 模型、网关类型、SDK版本、并发数；
- 17题成功/失败数；
- 每题Input/Cache/Output Token、成本、耗时、模型轮次；
- 每题Read/Edit次数和完整工具调用序列；
- 每题diff、编译结果、渲染日志和视频SHA256；
- 29个基准问题逐项：已修复/部分修复/未修复/新问题；
- 035/047/054/117后半段关键帧。

SDK若只提供任务聚合Token，应明确说明，禁止伪造每个工具调用的Token。

## 10. Evidence

- 输入样本：17份真实错误代码及原始生成/渲染记录。
- 背景：`reference_bg_02.png`。
- Logo：`logo_text_trim.png`。
- failure_code：
  - `coordinate_space_divergence`
  - `other_logic_error`
  - `object_lifecycle_error`
  - `transient_mobject_lifecycle_leak`

## 11. Durable Fix Map

- Reviewer：检查fit前后坐标事实源、数学构造、Scene驻留对象和阶段owner。
- Coder：修共享坐标源；临时对象具名化、入owner并复用。
- Checker：可用fail-open AST检查提供证据，不阻断渲染。
- 回归：必须保留035/047/054/117生命周期样本。

## 12. Blocking Policy / Legacy Prompt Impact

- 不新增质量拦截，checker仅采证/回归。
- 本包是离线Read/Edit实验入口，不修改生产legacy prompt、数据库或部署配置。
