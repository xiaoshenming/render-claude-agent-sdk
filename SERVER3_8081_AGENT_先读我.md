# Server3 8081 逻辑与重叠 Agent 交接包

这是 server3 管理后台 8081 发布任务后，经 API 8889、RabbitMQ，最终由 Render 8002 调用的 Logic Agent 与 Overlap/Layout Agent 冻结交接包。

## 拿到包后只做三步

### 1. 验证

```bash
python handoff/server3-logic-overlap-20260804/verify_snapshot.py
```

必须看到归档 SHA、947 个核心文件和无 `.env` 三项均为 `OK`。

### 2. 阅读

按顺序阅读：

1. `handoff/server3-logic-overlap-20260804/00_交接总览.md`
2. `handoff/server3-logic-overlap-20260804/04_完整搭建与使用流程.md`
3. `handoff/server3-logic-overlap-20260804/02_交接检查表.md`

需要交给 AI 协助时，复制：

`handoff/server3-logic-overlap-20260804/03_AI交接提示词.md`

### 3. 解压线上冻结源码

```bash
mkdir -p runtime_snapshot
tar -xzf vendor/source_archives/server3_render_logic_overlap_runtime_20260804.tar.gz \
  -C runtime_snapshot
```

重点入口：

- `runtime_snapshot/app/quality_platform/v3_runner.py`
- `runtime_snapshot/app/workers/validation/math_logic/`
- `runtime_snapshot/app/workers/validation/layout/`
- `runtime_snapshot/manim_quality_platform/v3/`

## 安全边界

包内没有密钥、`.env`、任务数据、数据库、视频和运行日志。接收方必须自行安全提供模型 Key。

本包用于审计、复现、移植和备份，不授权直接覆盖服务器或重启服务。部署前必须先比较当前版本、备份、运行测试和单题 canary。

来源分支：`codex/server3-logic-overlap-agent-backup-20260804`
