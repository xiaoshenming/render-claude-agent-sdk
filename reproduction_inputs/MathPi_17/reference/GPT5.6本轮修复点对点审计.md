# GPT-5.6 17题 Read/Edit 修复点对点审计

## 1. 头部元信息

- 日期：2026-07-25
- 审计对象：
  - [17题完整 issues 基准报告](</home/ming/下载/8797几何量化问题代码_17题_20260724/complete-issues-20c-results/RESULTS.md#L1>)
  - [四题生命周期人工诊断](</home/ming/下载/8797几何量化问题代码_17题_20260724/manual-four-lifecycle-fixes/REPORT.md#L1>)
  - [GPT-5.6 Read/Edit 运行总报告](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/17题_GPT5.6_ReadEdit_480P最详细报告.md#L1>)
- 审计口径：以此前完整 Reviewer 的 25 个 issues，加人工视频检查新增的 4 个生命周期问题，共 29 个已知问题为基准；逐项核对 GPT-5.6 的 `changes.diff`、修改后 `candidate.py`、Agent调用记录、编译和 480P 渲染日志。
- 使用说明：本报告判断“已知问题是否被这轮修复”，不把“渲染退出码为0”当作画面正确，也不声称29项之外不存在未知问题。

## 2. 状态图例

- 🟢 已上线：已进入生产、测试通过并有可见入口。本轮为离线实验，因此没有项目达到此状态。
- 🟡 灰度中 / 仓库就绪：隔离候选已修改，源码证据闭合，AST/编译和480P渲染通过，但未进入生产。
- 🟠 进行中：只修复了问题的一部分，仍有同一因果链的对象未纳入修复。
- 🔴 未开工：修改后源码仍保留基准问题模式。
- ⚪ 已确认延后：本轮明确不做的真实TTS、生产部署和人工全片终审。

## 3. 一页总览看板

| 主线 | 🟢 | 🟡 | 🟠 | 🔴 | ⚪ | 原子点 |
|---|---:|---:|---:|---:|---:|---:|
| A 坐标空间一致性 | 0 | 21 | 0 | 0 | 0 | 21 |
| B 数学/题设正确性 | 0 | 3 | 0 | 1 | 0 | 4 |
| C 对象入场与强调执行 | 0 | 0 | 1 | 0 | 0 | 1 |
| D 阶段生命周期清理 | 0 | 1 | 0 | 3 | 0 | 4 |
| 总计 | 0 | 25 | 1 | 4 | 0 | 30 |

说明：基准共有29个问题；`042` 的同一个 object_lifecycle_error 被拆成“已入组边”与“未入组 edge_AF”两个可观测原子点，因此看板为30个原子点。按问题口径统计为：24项修复、1项部分修复、4项未修复。

## 4. 反馈主线分章

### A. 坐标空间一致性

21项坐标漂移问题均在修改后源码中找到对应修复：要么在最终 `fit_geometry_group` 后重新读取真实端点，要么将后续强调对象加入最终适配组。17题全部完成 AST、`py_compile` 和480P渲染。

### B. 数学/题设正确性

`054` 的第二图角度/加减关系、`078` 的 E/F 构造、`099` 的点位关系得到修改；但 `099` 的 `arc_BAD/arc_CAD` 射线顺序仍保持基准 Reviewer指出的错误顺序。

### C. 对象入场与强调执行

`042` 将 `edge_AD/edge_CD/edge_BE` 纳入 `geometry_all`，但运行期新建的 `edge_AF` 及多个 `edge_AF_temp/final` 仍未加入 owner group或显式入场，属于部分修复。

### D. 阶段生命周期清理

`117` 已把两阶段的 `edge_AE/edge_AD` 加入对应 owner group。`035`、`047`、`054` 仍保留人工报告中确认的临时对象不属于阶段 owner 的模式，渲染成功不能证明残影消失。

### E. 速度与稳定性

17/17 Agent成功，17/17编译成功，17/17生成854×480、15fps预览。模型共54次Read、53次Edit；无Agent/Task调用。渲染日志中的 ERROR 均来自缺少TTS密钥后进入允许的静音回退，不是代码运行异常。

### F. 质量中间层与观测

SDK 0.2.110只返回每题聚合Token，没有每个Read/Edit调用的独立Token。现有报告完整保存工具顺序、参数、整题Token、成本、diff、日志和视频SHA256，但不能伪造单工具Token。

## 5. 原子点逐项审计

| ID | 状态 | 代码证据 | 测试 / 入口 | 状态描述 | 缺口 | 下一步 |
|---|---|---|---|---|---|---|
| A-017-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/017_平行班第六讲_04_练习2_等边三角形基础计算与证明_第3题_角内等腰线段计算/changes.diff#L1>) | 480P渲染通过 | 最终fit后重取O/P/M/N/H坐标。 | 缺人工画面对照。 | 抽取辅助线出现前后帧核对贴合。 |
| A-022-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/022_16_平行班第五讲_12_练习4第(3)题外角平分线的结论探究_纠错版/changes.diff#L1>) | 480P渲染通过 | 最终fit后重取A/B/C/D/E，后建强调边使用最终坐标。 | 缺人工画面对照。 | 抽帧核对7条强调边。 |
| A-030-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/030_平行班第三讲_练习4_角平分线双垂直综合题_综合题/changes.diff#L1>) | 480P渲染通过 | 重新构造F并在fit后刷新区域填充锚点。 | 缺原题几何人工复算。 | 复算反射射线与AC交点。 |
| A-035-01 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/035_16_平行班第五讲_04_练习1第(4)题腰上的高求底角/candidate.py#L1351>) | 480P渲染通过 | 图1在fit后重取三角形顶点并重建边/填充。 | 缺阶段清理，见D-035-01。 | 先补owner再做后半段抽帧。 |
| A-035-02 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/035_16_平行班第五讲_04_练习1第(4)题腰上的高求底角/candidate.py#L1400>) | 480P渲染通过 | 图2在fit后重取顶点并重建边/填充。 | 缺阶段清理，见D-035-01。 | 先补owner再做后半段抽帧。 |
| A-042-01 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/042_16_平行班第五讲_11_练习4第(2)题线段和差证明/candidate.py#L1391>) | 480P渲染通过 | fit后刷新A-F坐标，区域和AF使用最终坐标。 | 缺临时AF生命周期闭环。 | 合并C-042-01修复。 |
| A-045-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/045_12_春季班全等三角形综合（一）15_01_练习1/changes.diff#L1>) | 480P渲染通过 | AM/BK/BN/AK纳入统一适配。 | 缺人工画面对照。 | 抽帧核对四条强调边。 |
| A-047-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/047_12_春季班全等三角形综合（一）15_03_练习2/changes.diff#L1>) | 480P渲染通过 | 图1刷新最终锚点。 | 内联Line仍有生命周期泄漏。 | 合并D-047-01修复。 |
| A-047-02 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/047_12_春季班全等三角形综合（一）15_03_练习2/changes.diff#L1>) | 480P渲染通过 | 图2刷新最终锚点并精确构造点位。 | 内联Line仍有生命周期泄漏。 | 合并D-047-01修复。 |
| A-054-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/054_11_春季班全等三角形综合（一）14_05_练习4/changes.diff#L1>) | 480P渲染通过 | 强调线改用最终Mobject坐标。 | 内联临时线仍无owner。 | 合并D-054-01修复。 |
| A-057-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/057_10_春季班全等三角形综合13_03_练习2/changes.diff#L1>) | 480P渲染通过 | BF/AE加入最终适配组。 | 缺人工画面对照。 | 抽帧核对两条边。 |
| A-058-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/058_10_春季班全等三角形综合13_04_练习3/changes.diff#L1>) | 480P渲染通过 | 区域纳入适配并刷新BD/CD坐标。 | 缺人工画面对照。 | 抽帧核对四区域与两强调线。 |
| A-076-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/076_07_平行班加油站第二讲_02_练习2/changes.diff#L1>) | 480P渲染通过 | AE/EC/DE统一入组并复用显示对象。 | 缺人工画面对照。 | 抽帧核对刻痕与强调。 |
| A-078-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/078_07_平行班加油站第二讲_04_练习4/changes.diff#L1>) | 480P渲染通过 | DF纳入最终适配。 | 缺人工画面对照。 | 抽帧核对DF刻痕。 |
| A-080-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/080_06_平行班加油站第一讲_02_练习2微课脚本_三角形中线经典倍长中线模型/changes.diff#L1>) | 480P渲染通过 | 图1最终fit后刷新A-E。 | 缺人工画面对照。 | 抽帧核对图1强调线。 |
| A-080-02 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/080_06_平行班加油站第一讲_02_练习2微课脚本_三角形中线经典倍长中线模型/changes.diff#L1>) | 480P渲染通过 | 图2重算E/F并在fit后刷新锚点。 | 缺人工画面对照。 | 抽帧核对图2交点和高亮。 |
| A-099-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/099_09_平行班加油站第四讲_04_练习1第4题/changes.diff#L1>) | 480P渲染通过 | 重建点位并使用适配后端点。 | 角弧顺序未修，见B-099-02。 | 合并角弧修复后抽帧。 |
| A-100-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/100_09_平行班加油站第四讲_05_练习2第1题/changes.diff#L1>) | 480P渲染通过 | 精确计算D并在fit后刷新共享坐标。 | 缺人工画面对照。 | 抽帧核对垂直平分线。 |
| A-108-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/108_10_春季班全等三角形综合13_03_练习2/changes.diff#L1>) | 480P渲染通过 | AC/BC加入最终适配。 | 缺人工画面对照。 | 抽帧核对等边强调。 |
| A-117-01 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/117_12_春季班全等三角形综合（一）15_02_第56题/candidate.py#L1357>) | 480P渲染通过 | 图1 AE/AD加入geometry_all1。 | 缺人工后半段确认。 | 抽帧核对第一阶段退出。 |
| A-117-02 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/117_12_春季班全等三角形综合（一）15_02_第56题/candidate.py#L1420>) | 480P渲染通过 | 图2 AE/AD加入geometry_all2。 | 缺人工后半段确认。 | 抽帧核对第二阶段强调。 |
| B-054-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/054_11_春季班全等三角形综合（一）14_05_练习4/changes.diff#L1>) | 480P渲染通过 | 修改第二图外角、点位和证明关系。 | 缺原题人工复算。 | 对照题干逐式复算。 |
| B-078-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/078_07_平行班加油站第二讲_04_练习4/changes.diff#L1>) | 480P渲染通过 | 重新构造F/G/E满足题设关系。 | 缺数值独立验证。 | 写几何断言验证BE+FD=EF。 |
| B-099-01 | 🟡 | [diff](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/099_09_平行班加油站第四讲_04_练习1第4题/changes.diff#L1>) | 480P渲染通过 | 重建D/E/F并保持题设角度关系。 | 缺数值独立验证。 | 写角度/中点/垂直断言。 |
| B-099-02 | 🔴 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/099_09_平行班加油站第四讲_04_练习1第4题/candidate.py#L1366>) | 480P渲染通过但不证明正确 | `arc_BAD(pt_A, pt_D, pt_B)`与`arc_CAD(pt_A, pt_C, pt_D)`仍保持基准Reviewer判定的错误射线顺序。 | 缺交换端点修复。 | 改为`(pt_A,pt_B,pt_D)`与`(pt_A,pt_D,pt_C)`并重渲染。 |
| C-042-01 | 🟠 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/042_16_平行班第五讲_11_练习4第(2)题线段和差证明/candidate.py#L1526>) | 480P渲染通过 | AD/CD/BE已入组，但edge_AF、edge_AF_temp/final仍在运行期新建并直接动画。 | 缺owner归属或显式入场/退出。 | 建具名AF对象并加入geometry_all，后续统一复用。 |
| D-035-01 | 🔴 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/035_16_平行班第五讲_04_练习1第(4)题腰上的高求底角/candidate.py#L1406>) | 480P渲染通过但不证明无残影 | region_ABC1/2与edge_AB/AC在owner组建立后创建，未加入geometry_all1/2。 | 第一阶段退出覆盖不到后建对象。 | 将六个对象加入各自owner并检查切场帧。 |
| D-047-01 | 🔴 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/047_12_春季班全等三角形综合（一）15_03_练习2/candidate.py#L1477>) | 480P渲染通过但不证明无残影 | 高亮继续内联创建多条`Line(...)`，没有阶段owner。 | 切场后可能保留橙色L形线。 | 改成具名helper并加入geometry_all1/2。 |
| D-054-01 | 🔴 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/054_11_春季班全等三角形综合（一）14_05_练习4/candidate.py#L1362>) | 480P渲染通过但不证明无残影 | BP/CD强调线仍以临时Line构造，未加入第一阶段owner。 | 缺阶段统一清理。 | 建helper_BP1/helper_CD1并加入geometry_all1。 |
| D-117-01 | 🟡 | [candidate.py](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/117_12_春季班全等三角形综合（一）15_02_第56题/candidate.py#L1361>) | 480P渲染通过 | 两阶段AE/AD均已进入对应owner组，可随阶段退出。 | 缺人工切场帧确认。 | 抽帧确认水平残留边消失。 |

## 6. 反馈逐条 → 原子点对应表

| 反馈 / 基准来源 | 原子点 |
|---|---|
| 完整 Reviewer：17题25项 issues | A-017-01 至 A-117-02、B-054-01、B-078-01、B-099-01、B-099-02、C-042-01 |
| 人工报告：035阶段残留 | D-035-01 |
| 人工报告：047内联高亮线残留 | D-047-01 |
| 人工报告：054临时重强调线残留 | D-054-01 |
| 人工报告：117后建边残留 | D-117-01 |
| 用户要求：逐任务Read/Edit/Token明细 | [429行运行报告](</home/ming/下载/8797几何量化问题代码_17题_20260724/gpt56-repeated-read-edit-results/17题_GPT5.6_ReadEdit_480P最详细报告.md#L1>) |

## 7. 周排期建议

| 周期 | 工单 | 工时 | 依赖 |
|---|---|---:|---|
| W31-1 | 修复B-099-02角弧射线顺序并重渲染 | 0.5d | 无 |
| W31-1 | 修复C-042-01 AF对象owner和复用 | 0.5d | 无 |
| W31-1 | 修复D-035-01、D-047-01、D-054-01生命周期 | 1d | 人工报告既有方案 |
| W31-2 | 对17题按20%/40%/60%/80%抽帧并逐问题验收 | 1d | 上述修复 |
| W31-2 | 将`transient_mobject_lifecycle_leak`加入Reviewer/Coder repair合同与回归 | 1d | 四题验收 |

## 8. 升级判定标准

- 🔴→🟠：目标源码已发生对应修改，但仍存在同一问题链的未覆盖对象。
- 🟠→🟡：所有目标对象有统一owner/坐标事实源，AST、编译、480P渲染通过，且问题时间点抽帧不再复现。
- 🟡→🟢：修复进入正式Agent仓库，定向回归通过，真实测试任务可见并连续观察无回归。
- 任意状态回退：出现新残影、数学关系错误、渲染异常或修改越出`Solution`即退回🟠/🔴。

## 9. 团队本周必须确认的5件事

1. 是否由Logic Agent负责人在本周修复B-099-02与C-042-01？
2. 是否直接复用人工报告方案修复035/047/054，而不再让模型盲试？
3. 谁负责17题关键帧人工终审并签字？
4. 是否把生命周期问题加入正式Reviewer/Coder合同，而不是只留在实验runner？
5. 谁负责在server3测试任务上做同类问题的真实回归？

## 10. 不在本期范围

- ⚪ 真实CosyVoice音频：本轮明确交付480P静音加速预览。
- ⚪ 生产部署和DB同步：用户只要求离线回归与报告。
- ⚪ 29项之外未知问题的“零缺陷”保证：没有独立全片人工终审前不能承诺。

## 11. Evidence

- Agent：17/17成功；54次Read、53次Edit、0次其他工具。
- 编译：17/17 AST与`py_compile`通过。
- 渲染：17/17为854×480、15fps；视频总时长2140.397秒。
- Token：input 2,122,687；cache-read 1,619,968；output 59,859；记录成本13.120749美元。
- 日志中的TTS ERROR均随后进入`fallback_silent_mp3`，最终Manim退出码为0；未发现Python Traceback或Scene运行异常。
- 第一真实未闭环点：问题发现合同没有给当前Agent提供结构化issues清单，且Reviewer提示仍缺“动画使用对象→Scene驻留→owner覆盖→阶段退出”的完整生命周期审计。

## 12. Durable Fix Map / Blocking Policy / Legacy Prompt Impact

| 项 | 结论 |
|---|---|
| failure_code | `coordinate_space_divergence`、`other_logic_error`、`object_lifecycle_error`、`transient_mobject_lifecycle_leak` |
| block_packs | 需要补“阶段owner与临时Mobject生命周期”正反例 |
| metadata | 每题已有模型、工具序列、Token、diff、渲染日志、视频hash；缺单工具Token和逐问题ID回写 |
| registry/router | 本轮未改正式registry/router |
| repair/input contract | 当前单Agent自审自修；应改为冻结issues输入或独立Reviewer，明确owner检查 |
| evidence checker | 可增加fail-open AST提示：内联Line进入动画、owner建立后新建Mobject未`.add()` |
| tests | 需新增035/047/054/117四类生命周期回归 |
| server3 verification | 本轮未执行，仍需真实测试任务验证 |
| Blocking Policy | 不新增拦截；checker仅采证和回归 |
| Legacy Prompt Impact | 本轮只运行隔离Read/Edit实验，没有修改生产legacy prompt或正式Skill OS |
