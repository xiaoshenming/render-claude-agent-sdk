# MathPi 集成补丁

本目录主体来自 `manim_quality_complete_handoff_20260715_v3`。接入 MathPi
极简主管线时只保留以下运行时兼容补丁：

- `scripts/run_existing_code_e2e.py`：保留 venv 入口路径，不解析成系统 Python。
- `scripts/handoff_doctor.py`：Doctor 使用相同的 venv 入口语义。
- `src/manim_quality/agents/guards.py`：兼容 Claude Agent SDK 重复工作区前缀。
- `src/manim_quality/logic/expectations/comparison.py`：恢复 7 月 15 日点名归一化修复。

Docker Manim 适配器位于宿主项目
`app/quality_platform/manim_python_adapter.py`，未混入 V3 领域模块。
