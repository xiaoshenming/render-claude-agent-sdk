# 独立仓库验证记录

> 日期：2026-07-18  
> Python：3.11  
> 目的：记录独立发布时的真实状态，不用“全绿”掩盖原始 V3 已存在的基线漂移。

## 完整性

- 原始 `MANIFEST.json` 登记：650 个文件。
- 当前目录缺失：0 个。
- Claude Agent SDK、逻辑模块、重叠修复 vendor、独立布局探针、E2E Harness、测试和最小数据集均已包含。
- `.venv`、Python 缓存、运行产物和真实密钥不进入 Git。

## 测试

执行：

```text
python -m pytest -q
```

结果：

```text
1371 passed, 10 failed
```

10 个失败均可在复制前的当前 V3 内容中复现，不是独立仓库漏文件造成：

- 1 个工程规则：`run_existing_code_e2e.py` 的原始 `main` 为 105 行，超过项目自设 60 行函数限制；
- 4 个重叠 adapter 旧断言与后来加入的重叠误判过滤策略不一致；
- 3 个 artifact URI 测试把 `file:///tmp/...` 错误去成相对路径；
- 1 个冻结 holdout Hash 未随后续回归数据更新；
- 1 个 vendor 来源验证失败，原因是冻结来源后来被修正但原始 Hash 基线未重签。

本次发布没有为了让测试变绿而回退 server3 已验证的修复，也没有擅自重签历史冻结证据。后续应单独开维护版本：先确认新行为，再更新对应断言与来源基线。

## 其他检查

- Python 编译检查通过。
- 敏感信息扫描未发现真实 API Key、私钥或云密钥。
- 测试中的 `sk-malicious-secret-value` 和 `sk-reviewer-echo-secret` 是专门验证脱敏逻辑的假字符串。
