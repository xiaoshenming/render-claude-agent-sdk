# MathPi 接入说明

这个目录保存 MathPi 当前连接完整 V3 的“转换插头”。V3 核心仍然位于仓库根目录，不依赖 MathPi 的数据库、队列或 Docker 结构。

## 为什么单独放这里

独立 V3 使用本地 Manim Python；MathPi 测试服务器使用 Docker Manim 容器，并把结果写入自己的质量事件和留存目录。因此需要少量宿主适配，但这些适配不应该混进 V3 领域核心。

## 文件作用

| 文件 | 作用 |
|---|---|
| `app/quality_platform/v3_runner.py` | 启动完整 V3 existing-code E2E |
| `app/quality_platform/minimal_bridge.py` | 把 MathPi 最终代码、题目和参考内容交给 V3 |
| `app/quality_platform/manim_python_adapter.py` | 把 V3 的 Manim 调用转换为 MathPi Docker 渲染方式 |
| `app/quality_platform/retention*.py` | 留存最终代码、结果和布局证据 |
| `app/quality_platform/render_bridge.py` | 旧接入兼容桥 |
| `app/quality_platform/pre_archive.py`、`sdk_review.py` | 早期归档前 SDK 审查兼容面，不是完整 V3 主入口 |
| `tests/` | 宿主桥、V3 runner、留存和安全边界回归测试 |

## 当前真实主入口

MathPi 极简主管线使用：

```text
minimal_bridge.py
→ v3_runner.py
→ scripts/run_existing_code_e2e.py
→ V3 Logic
→ V3 Layout
→ retention.py
```

判断线上是否真的运行 V3，必须查看质量事件：

```text
event_type = pre_archive_quality_platform_completed
source_head = manim_quality_complete_handoff_20260715_v3
```

只看到 `sdk_review.py`、普通 render 日志或配置开关，不能证明完整 V3 已运行。

## 接入原则

- 逻辑审查先于重叠检测。
- 能修复则修复，无法确定则保留 warning。
- 普通质量问题 fail-open，不阻断最终视频。
- Docker、队列、数据库和对象存储由宿主项目负责。
- 不把 MathPi 私密环境文件复制到本仓库。

