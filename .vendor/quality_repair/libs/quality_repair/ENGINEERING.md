# quality_repair 工程规范（开发本模块的人与 agent 必读，违反即 review 打回）

> 为什么存在：雏形实验证明 Claude SDK 效果好的很大原因是 harness 本身设计干净——
> 工具面小、边界硬、每步可观测。本模块自己也要达到同样的 harness 品质，
> 并为后期把整条管线封装成对外 SDK 预留结构。
> 反面教材就在本仓库：`deterministic_guard.py` 4517 行巨型分支堆、
> 旧 `video_worker.py` 2781 行、`task_data` 万能可变字典穿全链。禁止再造。

## 一、结构铁律

1. **分层单向依赖**，箭头只能向下，禁止横向 import 兄弟层的实现：

   ```
   api.py / cli.py
      │
   contract/ route/ tools/ agent/ acceptance/   ← 互相不 import
      │
   interfaces.py（Protocol 边界）
      │
   schemas.py（数据结构）→ statuses.py（常量）
   ```

2. **一个文件一个职责**：目标 ≤200 行，硬上限 300 行（严于项目 500 行红线）。
   逼近上限先拆文件，不是压缩代码。
3. **禁止 `apps.*` import**；外部能力（checker/renderer/solver）
   一律经 `interfaces.py` 的 Protocol 注入。业务层不读环境变量、不读配置中心、
   不知道 RabbitMQ/MySQL/COS——配置由调用方组装进 Bundle/ToolBox（SDK 化前提）。
   唯一例外是 `agent/runner.py` 作为 SDK 边界层，可读取进程环境变量或权限为
   `600` 的本机私密 SDK 凭据文件；凭据不得进入 bundle、证据、命令行或 git。
   LLM 执行路径只有 `ClaudeSDKRunner`，不开放自定义 runner 入口。
4. **纯逻辑与副作用分离**：数学/判定/装配是纯函数；IO、subprocess、SDK 调用
   集中在明确标注的边界函数里。纯函数部分的单测不允许出现 mock。

## 二、函数设计铁律

1. **单一职责，软上限 40 行**；出现第二层嵌套的 if/for 时先考虑提取函数。
   禁止"一个函数处理 N 种错误模式"的分支堆（deterministic_guard 病）。
2. **签名显式**：全量类型标注；≥3 个参数用 keyword-only（`*,`）；
   禁止布尔开关参数链（`f(x, True, False, True)`）。
3. **禁止万能字典**：跨函数传递的数据必须是 `schemas.py` 里的 dataclass；
   禁止 `task_data.setdefault(...)` 式的可变 dict 穿层（旧链最大的排障黑洞）。
4. **错误即数据**：内部失败返回结构化结果（`CheckResult.failure(...)`、
   `AgentRunReport(error=...)`、`REVIEW_ERROR`），不抛异常穿层；
   `except Exception` 只允许出现在层边界，且必须把异常内容写进返回值/证据。
5. **确定性**：同输入同输出。禁止在库代码里取当前时间、随机数、全局单例；
   需要时间戳由调用方传入或只写进证据文件。

## 三、可排障性（harness 品质）

1. 每个决策点（分类、断言、门禁、止损）返回值里必须带 `reasons: list[str]`，
   机器可读，不靠日志字符串拼接。
2. 每层可独立驱动：tools/ 每个工具都是"库函数 + CLI"双形态；
   contract/acceptance 可以单独对一个 workdir 跑。
3. 证据先行：任何一轮执行无论成败都落 `evidence_dir`（见设计方案 §九）；
   排障的第一入口永远是证据目录，不是加 print。
4. 测试分两层：纯逻辑单测（无 mock、毫秒级）+ 边界集成测（Stub 注入，
   见 `testing.py`）。新增公共函数必须带对应测试。

## 四、SDK 化预留（后期整管线封装的前提）

1. **公开 API 表面最小**：对外只有 `__init__.py` 显式导出的名字；
   内部模块不承诺稳定，导出即承诺。
2. **schema 演进**：所有落盘 JSON 带 `schema_version`；改字段只加不删，
   删除走版本号升级。
3. **零环境假设**：模块可以在任何有 Python 3.11 的地方 import 并用 Stub 跑通
   （`python -m pytest libs/quality_repair/tests` 不需要 Docker/DB/网络）。
4. **依赖最小**：运行时依赖只允许标准库 + numpy；claude_agent_sdk 惰性导入，
   缺失时优雅降级（`AgentRunReport(error="claude_agent_sdk_unavailable")`）。
5. 未来对外 SDK 的形态即今天的调用方式：`repair(bundle, toolbox)` 一个入口，
   Bundle 进、Result 出、证据落盘。不要为"方便"增加第二入口。

## 五、review 检查单（每个任务的 reviewer 逐条过）

- [ ] 文件 ≤300 行、函数 ≤40 行（软）/无巨型分支堆
- [ ] 无 `apps.*` import、业务层无环境变量读取、无万能 dict 穿层
- [ ] 层依赖方向正确，兄弟层无横向 import
- [ ] 内部失败全部结构化返回，无异常穿层，`except` 只在边界
- [ ] 决策返回值带 reasons；新公共函数有测试；纯逻辑测试无 mock
- [ ] 落盘 JSON 带 schema_version；无 key/token 明文
