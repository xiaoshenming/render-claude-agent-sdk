# Linux 迁移记录

## 来源

- 交付包：`ManimQualityAgent_20260726`
- 来源提交：`8efca2a`
- 交付提交：`4f237dd`
- 新分支：`codex/manim-quality-agent-20260726`

## Linux 适配

交付包来自 Windows，原始 `PACKAGE_MANIFEST.sha256` 把部分路径大小写写成了
Windows 不敏感形式。迁移时原样保留为
`PACKAGE_MANIFEST.windows.sha256`，不改写交付源码来伪造校验通过。

Agent 使用 `uv` 管理 Python 3.11 环境。真实 Manim 渲染复用本机已有
`docker-manim-worker-1:latest`，通过 `scripts/docker_manim_python`
适配成 Operator 所需的 Python 可执行文件。运行时只挂载当前 worktree 和
静音 TTS stub，不把 API Key 写入仓库或日志。

## 已知冻结基线

- 聚焦 Agent/Operator 测试：177 passed。
- 全量测试：1457 passed，6 failed。
- 失败包括交付文档已声明的旧 SDK 测试、历史 holdout/vendor Hash，以及
  Windows `file:///` 路径语义导致的 3 个 artifact 测试。
- 这些失败已记录，不通过篡改冻结 Hash 消除。
