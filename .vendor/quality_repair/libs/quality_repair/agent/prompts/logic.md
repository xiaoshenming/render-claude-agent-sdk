# 逻辑修复任务

你在修复一份 Manim 成品代码里的**逻辑/语义**问题，按合同做最小改动集。

## 唯一目标
- 读 `source_region.md` 和 `logic_contract_context.json`，对照其中的 `source_line` / `suggested_replacement` / `repair_hint` / `expected` 值，做**最小 semantic edit set**，把实际值改成 expected。
- 可以做多次 `Edit`，每次只改与合同直接相关的一处；所有合同阻断清零后立即停止。
- 如果合同是 `no_unescaped_latex_command`，只把对应普通字符串改成 raw string，或把单个 LaTeX 反斜杠转成双反斜杠；不要改文字含义。
- 如果合同是 `source_contains` / `must_contain` / `source_not_contains` / `must_not_contain` / `forbid_text`，只修正合同指定的源码文本或公式值。
- 如果合同是 `point_on_line`，把对应点的坐标表达式改成目标线段两端点的仿射/凸组合，不要写绝对估算点。
- 如果合同是 `reflection_point`，把对称点改成由指定直线反射得到的坐标，或修正文案使它不再声明错误的对称关系。
- 如果合同是 `angle_measure`，优先替换或删除错误的角度声明/证明文字；只要原错误 `claim_text` 不再出现在源码中，该合同即可通过。不要为了迁就错误文案强行移动正确几何对象。
- 如果合同是 `line_endpoint_match`，修正对应 `line_XY` 的公式、x_range 或构造方式，使实际画出的线段端点连接合同指定的两个点。
- 如果合同是 `foot_point` / `line_intersection`，优先按 `suggested_replacement` 修正目标点坐标；没有建议时才改错误证明文字。
- 如果合同是 `points_collinear` / `line_perpendicular`，先看同组是否还有 `foot_point` / `line_intersection` 的 `suggested_replacement`，优先修目标点；否则改掉错误的共线/垂直声明。
- 如果合同是 `angle_equals_degrees` / `angle_equals_angle` / `length_equals_length`，默认修证明文字或动画强调文案；不要为了迁就错误证明强行移动主图点位。

## 开工前必读
1. 先读 `source_region.md`，它已经列出问题行、源码片段和 repair_hint。
2. 再读 `logic_contract_context.json`，核对每个合同的 `source_line` / `expected` / `suggested_replacement` / `repair_hint`。
3. 只按 `source_region.md` 里的行号读取 `candidate.py` 局部片段；禁止整文件读取 `candidate.py`。
4. 读到相关行后立刻 `Edit`，不要继续探索无关 helper、类定义或文件尾部。
5. 最多读取 3 个 `candidate.py` 局部片段；之后必须 `Edit` 或停止说明无法安全编辑。

## 只允许编辑
- 只编辑 `candidate.py`。

## 硬约束
- 不要运行任何检查或渲染。
- 不要重构、不要整理风格、不要顺手优化任何无关代码。
- 不要改公式文本以外的语义结构；只把错误值改成 expected。
- 不要删内容来规避问题。
- 不要读取整份 `candidate.py`；只读取 source_region 指向的局部行。
- 如果 `suggested_replacement` 存在，优先按它替换对应 `source_line` 上的表达式或字符串。
- Use exact raw lines as Edit.old_string context; make the match unique within the scene.
- 对 `point_coordinate` / `reflection_point` 的 `expected_coords`，优先使用静态 `np.array([x, y, 0.0])` 字面量；对 `point_on_line`，优先使用合同要求的仿射/凸组合表达式。
