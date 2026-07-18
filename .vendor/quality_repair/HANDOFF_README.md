# quality_repair 独立测试交接包

## 版本信息

- 源仓库：`shuxuepai`
- 源提交：`ae371aecd9cd258344c94ecdfa6a6cdd36417f5c`
- 兼容版本：`quality-platform.1`
- 打包日期：`2026-07-11`
- 公共入口：`libs.quality_repair.repair(bundle, toolbox)`
- 当前重点：layout 重叠检测后的 Claude Agent SDK 修复
- 运行策略：fail-open；检测、修复或 SDK 失败不会升级为视频交付硬拦截

## 包内内容

```text
libs/quality_repair/              模块完整源码与测试
quality_repair/                   `python -m quality_repair` 兼容入口
tools/quality_repair_checkers/    layout/logic checker
tools/quality_repair_m0/          配置、合同生成与辅助工具
docs/03-新需求与规划/             当前方案和参数归档（仅 3 份相关文档）
requirements-handoff.txt          交接开发环境的最小 Python 依赖
verify_handoff.sh                 无真实 SDK 消耗的本地验证脚本
SOURCE_MANIFEST.txt               交接包文件清单
SHA256SUMS.txt                    归档校验和
```

不包含历史视频、运行报告、bbox 样本库、SDK transcript、缓存、密钥和本机 `.env`。

## 环境准备

要求 Python 3.11。建议在解压目录创建虚拟环境：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-handoff.txt
```

`claude-agent-sdk` 仅在真实 Agent 修复时使用。单元测试通过 fake SDK 覆盖核心边界，不会调用线上模型，也不会产生 token。

交接包固定 SDK 版本为 `0.2.115`。该兼容版本将 `Budget.token_hard_cap`
传入 SDK `task_budget`，并通过公开 `RepairBundle.candidate_mode` 提供
`core`（默认）和 `full` 两种候选视图。升级 SDK 前必须重新运行完整测试
和一个真实高重叠样本。

## 第一步：验证源码包

在解压后的目录执行：

```bash
bash verify_handoff.sh
```

脚本执行完整模块测试、Python 编译检查、敏感文件名扫描和超大源码文件检查。超过 300 行的文件默认作为维护警告输出；设置 `STRICT_SOURCE_SIZE=1` 可把它升级为本地开发检查失败，但不得把它接成视频交付 hard gate。

## 第二步：配置真实 SDK

不要把密钥写入本目录。运行：

```bash
bash tools/quality_repair_m0/configure_sdk_env.sh
```

配置默认写入：

```text
~/.config/mathpi/quality_repair_sdk.env
```

权限为 `600`。运行时识别：

```text
ANTHROPIC_BASE_URL
ANTHROPIC_API_KEY
QUALITY_REPAIR_SDK_MODEL
```

模型可通过环境变量设置；不要把真实值提交或发回交接包。

## 第三步：准备真实 layout bundle

最小目录结构：

```text
case_001/
├── candidate.py
├── layout_context.json
├── bundle.json
└── tool_config.json
```

`bundle.json` 示例：

```json
{
  "job_id": "case_001",
  "profile": "layout",
  "code_path": "candidate.py",
  "layout_context": "layout_context.json",
  "evidence_root": "evidence"
}
```

`tool_config.json` 必须由测试环境提供真实 checker 命令。模块不会内置 MathPi Docker 路径，也不会替接收方猜测 Manim 镜像。请参考 `tools/quality_repair_m0/gen_tool_config.py` 生成配置。

`check_cmd`、`render_cmd`、`frame_cmd` 是 argv 数组，不经过 shell；不要在其中写管道或重定向。交接环境优先使用绝对脚本路径，避免因为当前工作目录不同而出现找不到 checker。

运行：

```bash
python -m quality_repair --bundle /absolute/path/to/case_001
```

CLI 始终输出 JSON。重点字段：

- `status`：`SUCCESS_CLEAN`、`SUCCESS_DEGRADED`、`REPAIR_UNCHANGED` 或 `REVIEW_ERROR`
- `before` / `after`：修复前后 checker 结果
- `rounds_used`：外层 SDK 修复轮数
- `tokens_used`：本次 SDK token 总量
- `evidence_dir`：完整诊断、diff、SDK transcript 和验收证据

## 当前运行逻辑

layout 链路默认把客观 issue 数据和候选源码交给 Agent。Agent 可多次使用 `Edit`；控制器根据 checker 反馈决定是否进入下一轮。若已经显著改善且只剩少量低风险残留，可停止昂贵的第二轮；最终是否采纳仍由 checker 与 acceptance 决定。

当前关键参数在 `libs/quality_repair/schemas.py`：

```text
accept_degraded_max_blocking = 2
accept_degraded_min_reduction_ratio = 0.5
accept_risk_only_max_blocking = 6
```

当前读取保护允许 Edit 后最多两次重新读取当前可编辑源码，用于处理 `old_string` 过期，同时抑制无效 Read 循环。

## 接收方建议先读

1. `libs/quality_repair/ENGINEERING.md`
2. `libs/quality_repair/api.py`
3. `libs/quality_repair/agent/controller.py`
4. `libs/quality_repair/agent/runner.py`
5. `libs/quality_repair/pipeline_io.py`
6. `docs/03-新需求与规划/2026-07-09-quality-repair-SDK条件二轮策略归档.md`

## 边界与注意事项

- 这是仓库结构下可独立测试和开发的源码包，不是 PyPI wheel。
- 真实 layout checker 通常依赖 Manim/Docker/FFmpeg；纯测试不依赖这些运行时。
- 默认 CLI 只注入 checker 和 solver，不注入 renderer；因此 CLI 能验证 blocking 是否下降，但不会自动产出前后对比视频。完整视频验收应由上层测试 harness 注入 renderer。
- `candidate.py` 自身可能依赖 Manim、`manim_voiceover` 和项目自定义服务，接收方的渲染镜像必须与候选代码 ABI 匹配。
- 不要把 checker 改成质量 hard gate；该模块维持 evidence-only / fail-open。
- 不要重新启用 deterministic layout 前修复；当前归档方案由 Agent 直接处理 issue 与源码。
- 任何批量真实 SDK 测试都应保留每题 token、轮数、before/after blocking 和未采纳 diff。
- 当前仍有部分源码和测试文件超过 `ENGINEERING.md` 的 300 行目标，最大的是已禁用但保留用于回归的 `deterministic_layout.py`。这是维护债务，不影响本次 `242` 项测试通过；接收方不应把“拆文件”与行为修改混在同一提交中。

## 校验归档

收到压缩包后执行：

```bash
sha256sum -c SHA256SUMS.txt
```

该命令用于确认传输后的归档文件未损坏。
