# 17 题完整 issues 一次性 Review + 修复结果

## 执行合同

```text
Reviewer：
  原题 + 完整原始 Solution 一次输入
  tools=[]
  一次输出完整 issues[] + coverage

Coder：
  完整原始 Solution + 完整 Review 一次输入
  tools=[]
  一次输出 structured patches
  必须声明覆盖全部 issue indexes

编排器：
  old_text 唯一匹配
  补丁范围限定 Solution
  应用全部 patches
  AST + py_compile

模型阶段：
  并发上限 20；本批 17 路同时启动

渲染：
  六路并发
  854×480 / 15 fps
  无 TTS / 0 音轨
```

## 结果

- 17/17 得到完整 Review 与 Coder 结果。
- 17/17 的真实调用记录中 Reviewer/Coder `tools=[]`。
- Reviewer 共输出 25 个 issues。
- Coder共输出并应用 30 个 structured patches。
- 17/17 通过唯一匹配、Solution 范围、AST 和 `py_compile`。
- 17/17 渲染成功并通过 ffprobe：854×480、15 fps、0 音轨。
- 首批 17 路中 4 路遇到上游协议错误；保持同一 Prompt/Schema 重发后成功。错误尝试没有返回 usage，因此 Token 总数不包含这部分无法取得的消耗。

## 与上一版视频的逐字节比较

发生变化：

- 042
- 054
- 078
- 099
- 117

完全相同：

- 017、022、030、035、045、047、057、058、076、080、100、108

035 和 047 虽然 Reviewer 各输出了两个 issues，但补丁与上一版在可见效果上等价，所以新旧 MP4 的 SHA-256 完全相同。

## 三个重点样本

### 035 腰上的高求底角

完整 Review 分别列出了图1、图2的坐标问题，并分别生成补丁，但依然没有识别出 `region_ABC1` 在 `geometry_all1` 创建之后才创建、切图时不会被 `FadeOut(geometry_all1)` 移除的生命周期错误。因此视频仍然存在第一幅图色块残留并叠到第二幅图的问题。

### 047 全等三角形综合（一）· 练习2

完整 Review 分别覆盖两幅图，重取了两组 fit 后坐标；其补丁与上一版等价，新旧视频完全相同。Reviewer没有再找到会改变画面的第二类错误。

### 054 全等三角形综合（一）· 练习4

本次除图1的旧坐标高亮外，还识别并修改了图2证明中的角度和加减关系。因此视频确实发生变化；第二阶段面板从 `120°` 改为 `60°`，证明关系也由加法改为减法。

## Token

- Reviewer：输入 104,729，输出 247,638。
- Coder：输入 111,416，输出 87,796。
- 可计量合计：551,579 tokens。

完整 issues 合同显著增加了 Reviewer输出，尤其 042、054、099。完整明细见 `token-details.csv`。

## Evidence

- 每题 `review-call.json`：完整 Reviewer 结构化输出、usage、`tools=[]`。
- 每题 `coder-call.json`：完整 Coder结构化补丁、usage、`tools=[]`。
- 每题 `result.json`：issues、resolved indexes、补丁和编译结果。
- 每题 `render.stdout.log` / `render.stderr.log`：真实 Manim 渲染证据。
- `render-status.csv`：17 个最终渲染状态。
- `overview-70pct.png`：17 个视频 70% 时间点总览。

## Durable Fix Map

- `failure_code`：`coordinate_space_divergence`、`object_lifecycle_error`、`dynamic_dependency_error`。
- Reviewer 合同已从单一 `root_issue` 改为完整 `issues[] + coverage`。
- Coder合同已增加 `resolved_issue_indexes`，要求一次覆盖全部 Review 项。
- 仍需后续补强：coverage 不能只列出 `FadeOut`，还必须验证“该阶段所有已入场对象是否实际属于被退出的 group”。035 证明仅输出 coverage 并不能保证语义审计正确。

## Blocking Policy

不新增拦截；全部检查仅用于修复、采证和回归。

## Legacy Prompt Impact

本次改的是独立实验 runner 的 Review/Coder 输入与输出合同，没有修改生产 legacy prompt 或线上路由。因此这是完整合同的实验证据，还不是生产闭环。
