# 可部署交接包修正说明

## 结论

`manim_quality_platform_handoff_20260714.zip` 是供技术审核的精简交接包，
不是可直接部署的运行时包。它保留了平台源码和实验依据，但遗漏了源码导入链
实际依赖的两个运行时目录，因此会出现导入失败。

新的 `manim_quality_platform_deployable_20260714_v2.zip` 才是部署包。

## V1 的三个问题

1. `src/manim_quality/logic/engine_adapter.py` 和 validator registry 会导入
   `tools.logic_engine_mvp`，但 V1 没有复制
   `vendor/logic_engine_mvp_baseline`。
2. overlap runtime 默认从 `.vendor/quality_repair` 加载经过 Hash 绑定的物化
   payload，但 V1 既没有该目录，也没有物化脚本和源归档。
3. `pyproject.toml` 最初保守声明为 `>=3.11,<3.12`。本地已在 Python 3.12.6
   下完成安装、核心导入和完整主测试集验证，因此修正为 `>=3.11,<3.13`。

## V2 必须包含的运行时

- `vendor/logic_engine_mvp_baseline`
- `vendor/source_archives`
- `.vendor/quality_repair`
- `.vendor/quality_repair/PAYLOAD_SHA256SUMS.txt`
- `scripts/materialize_quality_repair.py`
- `scripts/vendor_verification`
- `scripts/smoke_deploy_runtime.py`

物化 payload 随包提供，部署时不需要重新生成。源归档和物化脚本保留用于
重新验证和灾难恢复。

## 部署检查

在解压后的包根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe scripts\smoke_deploy_runtime.py
```

Linux：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/smoke_deploy_runtime.py
```

smoke check 会真实执行四项检查：平台导入、logic engine 调用、
quality_repair Hash 校验、quality_repair API 加载。任一依赖缺失都会以非零
状态退出。

## 测试边界

Python 3.12.6 主测试集结果为 `1368 passed, 2 failed, 4 skipped`。两个失败与
Python 3.12 无关：一个是 holdout 文件更新后冻结 Hash 未刷新，另一个是历史
`logic_self_audit_baseline` 中已有文件与旧 provenance manifest 不一致。
它们是当前脏工作树已有的发布治理问题，不能被描述为全部测试通过；部署 smoke
check 不会掩盖运行时依赖缺失。
